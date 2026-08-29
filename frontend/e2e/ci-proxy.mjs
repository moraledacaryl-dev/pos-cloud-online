import http from 'node:http';

const listenHost = process.env.CI_PROXY_HOST || '127.0.0.1';
const listenPort = Number(process.env.CI_PROXY_PORT || 8080);
const backend = new URL(process.env.CI_BACKEND_URL || 'http://127.0.0.1:8100');
const frontend = new URL(process.env.CI_FRONTEND_URL || 'http://127.0.0.1:3100');

function proxy(req, res, target) {
  const options = {
    protocol: target.protocol,
    hostname: target.hostname,
    port: target.port,
    method: req.method,
    path: req.url,
    headers: {
      ...req.headers,
      host: target.host,
      'x-forwarded-host': req.headers.host || '',
      'x-forwarded-proto': 'http',
    },
  };
  const upstream = http.request(options);
  let upstreamRes = null;
  let settled = false;

  const destroyUpstream = () => {
    if (settled) return;
    settled = true;
    if (!upstream.destroyed) upstream.destroy();
    if (upstreamRes && !upstreamRes.destroyed) upstreamRes.destroy();
  };

  req.once('aborted', destroyUpstream);
  res.once('close', destroyUpstream);

  upstream.on('response', (response) => {
    upstreamRes = response;
    if (res.destroyed) {
      response.destroy();
      return;
    }
    res.writeHead(response.statusCode || 502, response.headers);
    response.once('error', destroyUpstream);
    response.once('end', () => { settled = true; });
    response.pipe(res);
  });

  upstream.on('error', (error) => {
    if (!res.headersSent && !res.destroyed) res.writeHead(502, { 'content-type': 'text/plain' });
    if (!res.destroyed) res.end(`CI proxy upstream failure: ${error.message}`);
  });

  req.pipe(upstream);
}

const server = http.createServer((req, res) => {
  const target = String(req.url || '').startsWith('/api/') ? backend : frontend;
  proxy(req, res, target);
});

server.listen(listenPort, listenHost, () => {
  console.log(`POS CI proxy listening at http://${listenHost}:${listenPort}`);
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
