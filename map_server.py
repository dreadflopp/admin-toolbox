"""
Map server for serving Google Maps HTML with API key injection.
"""

import sys
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from config import AppConfig

_server = None
_server_port = None


def _map_debug_log_path() -> Path | None:
    """Get path to debug log file, or None if not frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "toolbox_map_debug.txt"
    return None


def _map_debug_log(msg: str) -> None:
    """When frozen, append a line to toolbox_map_debug.txt next to the exe for diagnosing ERR_EMPTY_RESPONSE.
    File is cleared on each app start and limited to 50KB to prevent unbounded growth."""
    log_path = _map_debug_log_path()
    if log_path is None:
        return
    try:
        # Limit file size: if > 50KB, truncate to last 100 lines
        if log_path.exists() and log_path.stat().st_size > 50 * 1024:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            if len(lines) > 100:
                lines = lines[-100:]
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _map_debug_log_clear() -> None:
    """Clear the debug log file (called at app startup)."""
    log_path = _map_debug_log_path()
    if log_path is None:
        return
    try:
        if log_path.exists():
            log_path.unlink()
    except Exception:
        pass


def _make_request_handler(api_key: str):
    """Create a request handler class for the map server."""
    key = (api_key or "").strip()
    project_dir = str(AppConfig.PROJECT_DIR)

    class MapRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, request, client_address, server):
            super().__init__(request, client_address, server, directory=project_dir)

        def _safe_write(self, data: bytes) -> bool:
            """Write response body; return False if wfile is None (connection not ready)."""
            w = getattr(self, "wfile", None)
            if w is None:
                _map_debug_log("wfile is None in _safe_write")
                return False
            try:
                w.write(data)
                w.flush()
                return True
            except Exception as e:
                _map_debug_log(f"write/flush error: {e}")
                return False

        def _send_response_raw(self, status: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
            """Send a full HTTP response over the raw connection when wfile is None (frozen exe workaround)."""
            conn = getattr(self, "connection", None)
            if conn is None:
                return
            try:
                status_lines = {200: "200 OK", 400: "400 Bad Request", 500: "500 Internal Server Error"}
                status_line = f"HTTP/1.0 {status_lines.get(status, '500 Internal Server Error')}\r\n"
                headers = f"Content-Type: {content_type}\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n"
                conn.sendall(status_line.encode("utf-8") + headers.encode("utf-8") + body)
            except Exception as e:
                _map_debug_log(f"_send_response_raw error: {e}")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/map_google.html":
                import sys as _sys
                # In frozen (windowed) exe, sys.stderr is None; BaseHTTPRequestHandler.log_message
                # writes to stderr and breaks. Use raw connection so we never call send_response/log_request.
                use_raw = getattr(_sys, "frozen", False) or getattr(self, "wfile", None) is None
                if use_raw:
                    if not key:
                        self._send_response_raw(400, b"No API key", "text/plain; charset=utf-8")
                        return
                    if not AppConfig.MAP_TEMPLATE_GOOGLE.exists():
                        self._send_response_raw(500, b"<html><body><p>Map template not found.</p></body></html>")
                        return
                    try:
                        html = AppConfig.MAP_TEMPLATE_GOOGLE.read_text(encoding="utf-8").replace("API_KEY_PLACEHOLDER", key)
                        self._send_response_raw(200, html.encode("utf-8"))
                    except Exception as e:
                        _map_debug_log(f"Map handler error: {e}")
                        self._send_response_raw(500, f"<html><body><p>Error: {e!s}</p></body></html>".encode("utf-8"))
                    return
                try:
                    if not key:
                        self.send_response(400)
                        self.send_header("Content-type", "text/plain; charset=utf-8")
                        self.end_headers()
                        self._safe_write(b"No API key")
                        return
                    if not AppConfig.MAP_TEMPLATE_GOOGLE.exists():
                        _map_debug_log(f"Template missing: {AppConfig.MAP_TEMPLATE_GOOGLE}")
                        self.send_response(500)
                        self.send_header("Content-type", "text/html; charset=utf-8")
                        self.end_headers()
                        self._safe_write(b"<html><body><p>Map template not found.</p></body></html>")
                        return
                    html = AppConfig.MAP_TEMPLATE_GOOGLE.read_text(encoding="utf-8")
                    html = html.replace("API_KEY_PLACEHOLDER", key)
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    if not self._safe_write(html.encode("utf-8")):
                        _map_debug_log("_safe_write(html) failed")
                    return
                except Exception as e:
                    _map_debug_log(f"Handler error: {e}")
                    import traceback
                    _map_debug_log(traceback.format_exc())
                    try:
                        if getattr(self, "wfile", None) is not None:
                            self.send_response(500)
                            self.send_header("Content-type", "text/html; charset=utf-8")
                            self.end_headers()
                            self._safe_write(
                                f"<html><body><p>Map error: {e!s}</p></body></html>".encode("utf-8")
                            )
                    except Exception as e2:
                        _map_debug_log(f"Error sending 500: {e2}")
                    return
            super().do_GET()

    return MapRequestHandler


def start_map_server(api_key: str) -> bool:
    """Start local HTTP server for map. Returns True if started."""
    global _server, _server_port
    # Clear debug log on first server start (app startup)
    if _server is None:
        _map_debug_log_clear()
    project_dir = AppConfig.PROJECT_DIR
    if not project_dir.exists():
        _map_debug_log(f"ERROR: PROJECT_DIR does not exist: {project_dir}")
        return False
    template = AppConfig.MAP_TEMPLATE_GOOGLE
    if not template.exists():
        _map_debug_log(f"ERROR: MAP_TEMPLATE_GOOGLE does not exist: {template}")
    for port in range(8765, 8780):
        try:
            handler = _make_request_handler(api_key)
            _server = HTTPServer(("127.0.0.1", port), handler)
            _server_port = port
            thread = threading.Thread(target=_server.serve_forever, daemon=True)
            thread.start()
            time.sleep(0.5)
            return True
        except OSError:
            continue
    _map_debug_log("ERROR: Failed to bind any port in 8765-8779")
    return False


def get_map_url() -> str:
    """Get URL for Google map page."""
    global _server_port
    if _server_port:
        return f"http://127.0.0.1:{_server_port}/map_google.html"
    return ""
