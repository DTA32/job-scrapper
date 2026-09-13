// Localhost stand-in for a Discord webhook. `responder(n)` returns {status, body}
// for the nth request; requests are recorded with their headers and raw body.

const http = require('node:http');

async function startWebhookStub(responder = () => ({ status: 200 })) {
  const requests = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => {
      requests.push({ headers: req.headers, body });
      const { status, body: responseBody } = responder(requests.length);
      res.writeHead(status, { 'Content-Type': 'application/json' });
      res.end(responseBody === undefined ? '{}' : responseBody);
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}/api/webhooks/1/token`,
    requests,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

module.exports = { startWebhookStub };
