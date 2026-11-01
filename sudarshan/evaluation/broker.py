"""Loopback-only model broker: API credentials never enter the agent worker."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import secrets
import threading
import time
import uuid
from .. import provider, telemetry


class Broker:
    def __init__(self, model, deadline, max_requests):
        self.model, self.deadline, self.maximum = model, deadline, max_requests
        self.token = secrets.token_hex(32)
        self.requests, self.closed = 0, False
        self.lock = threading.Lock()
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                if self.path != "/complete" or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + owner.token):
                    self.send_error(403); return
                with owner.lock:
                    if owner.closed or time.monotonic() >= owner.deadline or owner.requests >= owner.maximum:
                        self.send_error(429); return
                    owner.requests += 1
                counter = None
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1048576: raise ValueError("request size")
                    self.connection.settimeout(max(.1, owner.deadline-time.monotonic()))
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict) or set(data) != {"system", "messages", "tools"}: raise ValueError("protocol")
                    class RetryCounter:
                        request_id = str(uuid.uuid4())
                        retries = 0
                        def emit(self, kind, **kwargs):
                            if kind == "model_retry": self.retries += 1
                    counter = RetryCounter()
                    scope = telemetry.ACTIVE.set(counter)
                    limit = provider.REQUEST_DEADLINE.set(owner.deadline)
                    try:
                        reply = provider.complete(owner.model, data["system"], data["messages"], data["tools"])
                        reply["_broker_retries"] = counter.retries
                    finally:
                        provider.REQUEST_DEADLINE.reset(limit)
                        telemetry.ACTIVE.reset(scope)
                    encoded = json.dumps(reply).encode()
                    if len(encoded) > 2097152: raise ValueError("response size")
                    self.send_response(200); self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
                except BaseException:
                    # The RPC envelope carries retry metadata even when generation
                    # failed. It never carries provider error bodies or messages.
                    encoded = json.dumps({"_broker_failure": True, "_broker_retries": counter.retries if counter else 0}).encode()
                    try:
                        self.send_response(200); self.send_header("Content-Length", str(len(encoded)))
                        self.end_headers(); self.wfile.write(encoded)
                    except OSError: pass
        class Server(ThreadingHTTPServer):
            daemon_threads = True
            def handle_error(self, *args): pass
        self.server = Server(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return {"url": f"http://127.0.0.1:{self.server.server_port}/complete", "capability": self.token,
                "remaining_seconds": max(.1, self.deadline-time.monotonic())}

    def __exit__(self, *args):
        with self.lock: self.closed = True
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
