"""Four fixed websites used to exercise the monitor.

A day on the response-time graph is 500 dots, about 173 seconds each.
A 10-minute UTC piece is roughly three dots, so the square wave stays visible.
Even pieces wait 100 ms. Odd pieces wait 900 ms.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PIECE_SECONDS = 10 * 60
SITES = (
    (17781, "steady"),
    (17782, "missing"),
    (17783, "square"),
    (17784, "slow"),
)


def response_for(kind: str, moment: datetime) -> tuple[int, int]:
    """Return the HTTP status and the delay in milliseconds."""
    if kind == "steady":
        return 200, 100
    if kind == "missing":
        return 404, 300
    if kind == "slow":
        return 200, 6000
    piece = int(moment.timestamp()) // PIECE_SECONDS
    return 200, 100 if piece % 2 == 0 else 900


def handler_for(kind: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, delay_ms = response_for(kind, datetime.now(timezone.utc))
            time.sleep(delay_ms / 1000)
            body = b"ok\n" if status == 200 else b"missing\n"
            try:
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                return

        def log_message(self, fmt: str, *args) -> None:
            port = self.server.server_address[1]
            print(f"http://{HOST}:{port} {fmt % args}", flush=True)

    return Handler


def serve(bindings: tuple[tuple[int, str], ...] = SITES) -> None:
    servers: list[ThreadingHTTPServer] = []
    try:
        for port, kind in bindings:
            try:
                server = ThreadingHTTPServer((HOST, port), handler_for(kind))
            except OSError:
                print(f"Port {port} is already in use.", flush=True)
                raise SystemExit(1) from None
            servers.append(server)
    except SystemExit:
        for server in servers:
            server.server_close()
        raise

    threads = []
    for server in servers:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        threads.append(thread)
        port = server.server_address[1]
        print(f"Listening on http://{HOST}:{port}", flush=True)
    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping mock websites.", flush=True)
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
