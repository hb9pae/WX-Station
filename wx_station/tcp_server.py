"""Lightweight TCP server for live sensor data queries."""

import json
import socket
import socketserver
import threading
from typing import Optional
from wx_station.ram_cache import RAMCache


class WXClientHandler(socketserver.StreamRequestHandler):
    """Handles incoming client TCP connections."""

    server: "WXTCPServer"  # Type hint for custom server

    def handle(self) -> None:
        self.request.settimeout(10.0)

        # On connect, immediately send the current reading in configured format
        current = self.server.cache.read_sample()
        self._send_reading(current, requested_format=self.server.default_format)

        # Allow client to send commands (e.g. "GET", "JSON", "PLAIN", "QUIT")
        while True:
            try:
                line = self.rfile.readline()
                if not line:
                    break
                cmd = line.decode("utf-8", errors="ignore").strip().upper()
                if not cmd:
                    continue

                if cmd in ("QUIT", "EXIT", "BYE"):
                    break
                elif cmd in ("GET", "READ", "PLAIN"):
                    sample = self.server.cache.read_sample()
                    self._send_reading(sample, requested_format="plaintext")
                elif cmd == "JSON":
                    sample = self.server.cache.read_sample()
                    self._send_reading(sample, requested_format="json")
                elif cmd == "HELP":
                    help_text = "WX-Station Commands: GET, JSON, PLAIN, QUIT\n"
                    self.wfile.write(help_text.encode("utf-8"))
                    self.wfile.flush()
                else:
                    self.wfile.write(b"ERR:UNKNOWN_COMMAND\n")
                    self.wfile.flush()
            except (socket.timeout, ConnectionResetError, BrokenPipeError):
                break

    def _send_reading(self, data: Optional[dict], requested_format: str) -> None:
        if not data:
            msg = "ERR:NO_DATA_AVAILABLE\n"
            self.wfile.write(msg.encode("utf-8"))
            self.wfile.flush()
            return

        if requested_format == "json":
            msg = json.dumps(data) + "\n"
        else:
            # Plaintext format: TEMP:...;HUM:...;PRESS:...;QNH:...;DEW:...;TS:...
            msg = (
                f"TEMP:{data.get('temperature', 0.0):.2f};"
                f"HUM:{data.get('humidity', 0.0):.2f};"
                f"PRESS:{data.get('pressure', 0.0):.2f};"
                f"QNH:{data.get('pressure_qnh', 0.0):.2f};"
                f"DEW:{data.get('dew_point', 0.0):.2f};"
                f"TS:{int(data.get('timestamp', 0))}\n"
            )

        self.wfile.write(msg.encode("utf-8"))
        self.wfile.flush()


class WXTCPServer(socketserver.ThreadingTCPServer):
    """Threaded TCP server instance holding the RAM cache reference."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        cache: RAMCache,
        default_format: str = "plaintext"
    ):
        self.cache = cache
        self.default_format = default_format
        super().__init__(server_address, WXClientHandler)


class TCPServerManager:
    """Controls the background lifecycle of the WXTCPServer."""

    def __init__(self, host: str = "0.0.0.0", port: int = 4001, cache: Optional[RAMCache] = None, default_format: str = "plaintext"):
        self.host = host
        self.port = port
        self.cache = cache or RAMCache()
        self.default_format = default_format
        self.server: Optional[WXTCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the TCP server in a background daemon thread."""
        self.server = WXTCPServer((self.host, self.port), self.cache, default_format=self.default_format)
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        print(f"TCP server running on {self.host}:{self.port} (default: {self.default_format})")

    def stop(self) -> None:
        """Stops the TCP server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None
        print("TCP server stopped.")
