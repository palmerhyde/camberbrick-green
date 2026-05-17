"""
Minimal stdlib-only HTTP server for Claude preview_start compatibility.
Serves static HTML so the UI is visible in the preview panel.

For full functionality (database, HTMX, API routes) run:
    .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import http.server
import socketserver
import os
import mimetypes

PORT = int(os.environ.get("PORT", 8002))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Handler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._serve_file('templates/preview.html', 'text/html')
        elif self.path.startswith('/static/'):
            rel = self.path.lstrip('/')
            self._serve_file(rel, mimetypes.guess_type(rel)[0] or 'text/plain')
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_file(self, rel_path, content_type):
        full = os.path.join(BASE_DIR, rel_path)
        try:
            with open(full, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress request logs


os.chdir(BASE_DIR)
with socketserver.TCPServer(('0.0.0.0', PORT), Handler) as httpd:
    httpd.allow_reuse_address = True
    httpd.serve_forever()
