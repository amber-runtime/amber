"""
Worker entrypoint — runs an AgentRuntime queue worker with an HTTP health endpoint.

Usage:
  docker run -p 8004:8004 --env-file .env customer-worker

Environment:
  WORKER_TARGET  — module:object for the AgentRuntime (required)
  HEALTH_PORT    — port for /health endpoint (default 8004)
"""

import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    health_port = int(os.environ.get("HEALTH_PORT", "8004"))
    server = HTTPServer(("0.0.0.0", health_port), _HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # Delegate to sdk.worker
    target = os.environ.get("WORKER_TARGET", "")
    if not target:
        print("ERROR: WORKER_TARGET env var is required (e.g. example_customer_app.main:agent_runtime)")
        raise SystemExit(1)

    from sdk.worker import main
    raise SystemExit(main([target]))
