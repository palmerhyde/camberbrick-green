/**
 * Minimal Node.js preview server — no npm packages, stdlib only.
 * Serves the static scan UI so preview_start works.
 *
 * For full FastAPI functionality run:
 *   .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
 */
const http = require('http')
const fs   = require('fs')
const path = require('path')

const PORT    = 8000
const BASE    = __dirname
const TYPES   = { '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript' }

const server = http.createServer((req, res) => {
  let filePath

  if (req.url === '/' || req.url === '') {
    filePath = path.join(BASE, 'templates', 'preview.html')
  } else if (req.url.startsWith('/static/')) {
    filePath = path.join(BASE, req.url)
  } else {
    res.writeHead(404)
    return res.end('Not found')
  }

  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404)
      return res.end('Not found')
    }
    const ext = path.extname(filePath)
    res.writeHead(200, { 'Content-Type': TYPES[ext] || 'text/plain' })
    res.end(data)
  })
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Preview server running on http://0.0.0.0:${PORT}`)
})
