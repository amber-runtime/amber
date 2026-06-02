"""
Worker entrypoint — runs an AgentRuntime queue worker with an HTTP health endpoint.

Usage:
  docker run -p 8004:8004 --env-file .env customer-worker

Environment:
  WORKER_TARGET  — module:object for the AgentRuntime (required)
  HEALTH_PORT    — port for /health endpoint (default 8004)
  QUEUE_METRICS_ENABLED — emit DBOS queue metrics as CloudWatch EMF logs
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

    target = os.environ.get("WORKER_TARGET", "")
    if not target:
        print("ERROR: WORKER_TARGET env var is required (e.g. example_customer_app.main:agent_runtime)")
        raise SystemExit(1)

    from sdk.queue_metrics import env_flag, start_queue_metrics_publisher
    from sdk.worker import _load_target

    agent_runtime = _load_target(target)
    run_worker = getattr(agent_runtime, "run_worker", None)
    if not callable(run_worker):
        print(f"ERROR: Worker target {target!r} must expose a callable run_worker() method.")
        raise SystemExit(1)

    if env_flag("QUEUE_METRICS_ENABLED", default=False):
        db_url = os.environ.get("DB_URL") or os.environ.get("DBOS_SYSTEM_DATABASE_URL")
        if not db_url:
            print("ERROR: QUEUE_METRICS_ENABLED requires DB_URL or DBOS_SYSTEM_DATABASE_URL.")
            raise SystemExit(1)
        queue_name = getattr(agent_runtime, "queue_name", None) or os.environ.get(
            "QUEUE_NAME", "agent-runs"
        )
        interval_seconds = float(os.environ.get("QUEUE_METRICS_INTERVAL_SECONDS", "60"))
        start_queue_metrics_publisher(
            db_url=db_url,
            queue_name=queue_name,
            namespace=os.environ.get("QUEUE_METRICS_NAMESPACE", "Amber/Queues"),
            interval_seconds=interval_seconds,
            dimensions={
                "Project": os.environ.get("PROJECT_NAME", "unknown"),
                "Environment": os.environ.get("ENVIRONMENT", "unknown"),
                "Service": os.environ.get("SERVICE_NAME", "customer-worker"),
            },
        )

    run_worker()
    raise SystemExit(0)
