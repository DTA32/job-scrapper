// Thin client for the job-scraper MCP server: one connection, JSON tool results.

const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StreamableHTTPClientTransport } = require('@modelcontextprotocol/sdk/client/streamableHttp.js');
const { Agent, fetch } = require('undici');

const DEFAULT_TIMEOUT_MS = 30 * 60 * 1000;

/**
 * Connect to the MCP server at `url`. Resolves {callTool(name, args, {timeout}), close()}.
 *
 * Node's built-in fetch abandons a response after 300 s without headers or body
 * bytes. FastMCP runs sync tools such as scrape_jobs on its event loop, so the
 * server sends nothing at all until the scrape finishes: a scrape longer than five
 * minutes would be cut off and surface only as an SDK "Request timed out". This
 * dispatcher turns those socket timeouts off, which leaves the per-call `timeout`
 * as the single cap on how long a tool may run.
 */
async function connect(url, { timeoutMs = DEFAULT_TIMEOUT_MS, clientName = 'job-scraper-bot' } = {}) {
  const dispatcher = new Agent({ headersTimeout: 0, bodyTimeout: 0 });
  const transport = new StreamableHTTPClientTransport(new URL(url), {
    fetch: (input, init) => fetch(input, { ...init, dispatcher }),
  });
  const client = new Client({ name: clientName, version: process.env.BOT_VERSION || 'dev' });

  try {
    await client.connect(transport);
  } catch (err) {
    await dispatcher.close().catch(() => {});
    throw new Error(`cannot reach MCP server at ${url}: ${err.message}`);
  }

  return {
    async callTool(name, args = {}, { timeout = timeoutMs } = {}) {
      const result = await client.callTool({ name, arguments: args }, undefined, { timeout });
      return parseToolResult(name, result);
    },
    async close() {
      await client.close().catch(() => {});
      await dispatcher.close().catch(() => {});
    },
  };
}

/**
 * The tool's JSON value. FastMCP serializes a dict return into a text content
 * block; structuredContent is only a fallback for servers that send just that.
 */
function parseToolResult(name, result) {
  const text = (result.content || [])
    .filter((block) => block.type === 'text')
    .map((block) => block.text)
    .join('');
  if (result.isError) throw new Error(`${name} failed: ${text || 'no detail'}`);
  if (text) {
    try {
      return JSON.parse(text);
    } catch {
      // Not JSON: fall through to structuredContent.
    }
  }
  if (result.structuredContent && typeof result.structuredContent === 'object') {
    return result.structuredContent;
  }
  throw new Error(`${name} returned no JSON result`);
}

module.exports = { connect, parseToolResult, DEFAULT_TIMEOUT_MS };
