"""
Tiny stand-in for the WB-CRM /leads API, for the local demo only.

Lets `create_lead` succeed end-to-end (POST /leads -> 201 with a fake id) without the real,
private CRM. Never used in production. Stdlib only, so it runs in a bare python image.
"""

import json
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def do_POST(self):
        if self.path.rstrip("/") == "/leads":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            self._json(201, {
                "id": str(uuid.uuid4()),
                "businessName": body.get("businessName"),
                "sourceGroup": body.get("sourceGroup"),
            })
        else:
            self._json(404, {"error": "not found"})

    def do_GET(self):
        self._json(200, {"ok": True})

    def do_DELETE(self):
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass  # quiet


if __name__ == "__main__":
    print("CRM stub listening on :3010")
    HTTPServer(("0.0.0.0", 3010), Handler).serve_forever()
