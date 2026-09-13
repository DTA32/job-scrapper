// node --test lib/mcp.test.js
const { test } = require('node:test');
const assert = require('node:assert');

const { connect, parseToolResult } = require('./mcp.js');
const { startFakeMcpServer } = require('../test-support/fake-mcp-server.js');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test('callTool returns the parsed JSON value over streamable HTTP', async () => {
  const fake = await startFakeMcpServer({ echo: async (args) => ({ ok: true, args }) });
  const client = await connect(fake.url, { timeoutMs: 5000 });
  try {
    assert.deepEqual(await client.callTool('echo', { run_id: 'abc' }), { ok: true, args: { run_id: 'abc' } });
    assert.deepEqual(fake.calls, [{ name: 'echo', arguments: { run_id: 'abc' } }]);
  } finally {
    await client.close();
    await fake.close();
  }
});

test('a tool that sends nothing until it returns is waited for', async () => {
  const fake = await startFakeMcpServer({ slow: async () => (await sleep(1500), { done: true }) });
  const client = await connect(fake.url, { timeoutMs: 5000 });
  try {
    assert.deepEqual(await client.callTool('slow'), { done: true });
  } finally {
    await client.close();
    await fake.close();
  }
});

test('a call that outlives its timeout rejects', async () => {
  const fake = await startFakeMcpServer({ slow: async () => (await sleep(1000), { done: true }) });
  const client = await connect(fake.url);
  try {
    await assert.rejects(client.callTool('slow', {}, { timeout: 200 }), /timed out/i);
  } finally {
    await client.close();
    await fake.close();
  }
});

test('tool errors surface as exceptions', async () => {
  const fake = await startFakeMcpServer({});
  const client = await connect(fake.url, { timeoutMs: 5000 });
  try {
    await assert.rejects(client.callTool('scrape_jobs'), /scrape_jobs failed: unknown tool scrape_jobs/);
  } finally {
    await client.close();
    await fake.close();
  }
});

test('an unreachable server fails to connect with the URL in the message', async () => {
  await assert.rejects(connect('http://127.0.0.1:9/mcp', { timeoutMs: 2000 }), /cannot reach MCP server at http:\/\/127\.0\.0\.1:9\/mcp/);
});

test('parseToolResult prefers JSON text, falls back to structuredContent', () => {
  assert.deepEqual(parseToolResult('t', { content: [{ type: 'text', text: '{"a":1}' }] }), { a: 1 });
  assert.deepEqual(
    parseToolResult('t', { content: [{ type: 'text', text: 'not json' }], structuredContent: { b: 2 } }),
    { b: 2 },
  );
  assert.throws(() => parseToolResult('t', { content: [] }), /t returned no JSON result/);
  assert.throws(() => parseToolResult('t', { isError: true, content: [{ type: 'text', text: 'boom' }] }), /t failed: boom/);
});
