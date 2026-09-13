// A real streamable-HTTP MCP server for tests, built from the SDK: stateless, and
// with JSON responses, so like FastMCP's sync tools it sends nothing until the
// tool returns.

const http = require('node:http');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StreamableHTTPServerTransport } = require('@modelcontextprotocol/sdk/server/streamableHttp.js');
const { CallToolRequestSchema, ListToolsRequestSchema } = require('@modelcontextprotocol/sdk/types.js');

/** `tools` maps a tool name to `async (args) => value`. Resolves {url, calls, close}. */
async function startFakeMcpServer(tools) {
  const calls = [];
  const httpServer = http.createServer(async (req, res) => {
    if (req.method !== 'POST') {
      res.writeHead(405, { Allow: 'POST' }).end();
      return;
    }
    let body = '';
    for await (const chunk of req) body += chunk;

    const server = new Server({ name: 'fake-job-scraper', version: '0.0.0' }, { capabilities: { tools: {} } });
    server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: Object.keys(tools).map((name) => ({ name, inputSchema: { type: 'object' } })),
    }));
    server.setRequestHandler(CallToolRequestSchema, async ({ params }) => {
      const args = params.arguments || {};
      calls.push({ name: params.name, arguments: args });
      const handler = tools[params.name];
      if (!handler) return { isError: true, content: [{ type: 'text', text: `unknown tool ${params.name}` }] };
      return { content: [{ type: 'text', text: JSON.stringify(await handler(args)) }] };
    });

    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    res.on('close', () => {
      transport.close();
      server.close();
    });
    await server.connect(transport);
    await transport.handleRequest(req, res, JSON.parse(body));
  });

  await new Promise((resolve) => httpServer.listen(0, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${httpServer.address().port}/mcp`,
    calls,
    close: () =>
      new Promise((resolve) => {
        httpServer.closeAllConnections();
        httpServer.close(resolve);
      }),
  };
}

module.exports = { startFakeMcpServer };
