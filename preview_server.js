/**
 * Minimal Node.js preview server — no npm packages, stdlib only.
 * Proxies all requests to the FastAPI app on port 8000 so the
 * preview panel shows the real app (not just the static mockup).
 *
 * For full FastAPI functionality run:
 *   .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
 */
const http = require('http')

const PORT     = parseInt(process.env.PORT || '8002', 10)
const UPSTREAM = { host: '127.0.0.1', port: 8000 }

const server = http.createServer((req, res) => {
  const options = {
    host: UPSTREAM.host,
    port: UPSTREAM.port,
    path: req.url,
    method: req.method,
    headers: req.headers,
  }

  const proxy = http.request(options, (upRes) => {
    res.writeHead(upRes.statusCode, upRes.headers)
    upRes.pipe(res, { end: true })
  })

  proxy.on('error', () => {
    res.writeHead(502)
    res.end('FastAPI app not running — start it with:\n  .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000')
  })

  req.pipe(proxy, { end: true })
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Preview proxy running on http://0.0.0.0:${PORT} → FastAPI :8000`)
})
