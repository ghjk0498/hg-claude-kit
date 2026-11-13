"""테스트용 가짜 torchcast. 요청마다 handler(body) -> (status, json, delay_s)를 부른다."""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

Handler = Callable[[dict], tuple[int, dict, float]]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeTorchcast:
    def __init__(self, handler: Handler):
        self.handler = handler
        self.requests: list[dict] = []
        self.health_status = {"status": "ok"}
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # 조용히
                pass

            def _send(self, status: int, body: dict):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                if self.path == "/health":
                    self._send(200, fake.health_status)
                elif self.path == "/v1/models":
                    self._send(200, {"data": [{"id": "fake-model"}]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n))
                fake.requests.append(body)
                status, resp, delay = fake.handler(body)
                if delay:
                    time.sleep(delay)
                self._send(status, resp)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def __exit__(self, *a):
        try:
            self.stop()
        except Exception:
            pass


def choice_answer(choice: str, probs: dict[str, float]) -> dict:
    n = len(probs)
    conf = (max(probs.values()) - 1 / n) / (1 - 1 / n)
    return {"answers": {"q": {"type": "choice", "choice": choice, "confidence": round(conf, 3),
                              "probabilities": probs}}, "latency_ms": 30.0}


def noul_answer(p: float) -> dict:
    return {"answers": {"q": {"type": "noul", "noul": p}}, "latency_ms": 25.0}
