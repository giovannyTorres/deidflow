"""Small authenticated loopback-only review server; no telemetry or uploads."""

from __future__ import annotations

import hmac
import json
import secrets
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .gmail import strict_json
from .security import write_private

Response = tuple[int, bytes, str]


def json_response(value: Any, status: int = 200) -> Response:
    return status, json.dumps(value, ensure_ascii=True).encode(), "application/json"


class LocalReviewServer(HTTPServer):
    """Serial HTTP requests bound exclusively to IPv4 loopback, never wildcard."""

    def __init__(
        self, html: str, application: Callable[[str, str, Any], Response], *, port: int = 0
    ) -> None:
        self.token = secrets.token_urlsafe(32)
        self.nonce = secrets.token_urlsafe(18)
        self.application = application
        self.html = html.replace("__NONCE__", self.nonce).encode()
        super().__init__(("127.0.0.1", port), _Handler)

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.server_port}"

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Default socketserver tracebacks could expose private paths or values.
        pass

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


class _Handler(BaseHTTPRequestHandler):
    server: LocalReviewServer

    def log_message(self, *args: Any) -> None:
        pass

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        self._send(json_response({"error": "REQUEST_REJECTED"}, code))

    def _send(self, response: Response) -> None:
        status, data, mime = response
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'none'; script-src 'nonce-{self.server.nonce}'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method: str) -> None:
        try:
            if (
                self.headers.get("Host") != self.server.origin.removeprefix("http://")
                or self.headers.get("Origin", self.server.origin) != self.server.origin
            ):
                self._send(json_response({"error": "REQUEST_REJECTED"}, 403))
                return
            if method == "GET" and self.path == "/":
                self._send((200, self.server.html, "text/html; charset=utf-8"))
                return
            auth = self.headers.get("Authorization", "")
            if not hmac.compare_digest(auth, "Bearer " + self.server.token):
                self._send(json_response({"error": "REQUEST_REJECTED"}, 403))
                return
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc or not parsed.path.startswith("/api/"):
                self._send(json_response({"error": "REQUEST_REJECTED"}, 404))
                return
            body = None
            if method == "POST":
                if self.headers.get("Content-Type", "").split(";")[
                    0
                ] != "application/json" or not hmac.compare_digest(
                    self.headers.get("X-DeidFlow-CSRF", ""), self.server.token
                ):
                    raise ValueError
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2 * 1024 * 1024:
                    raise ValueError
                body = strict_json(self.rfile.read(size).decode("utf-8"))
            self._send(self.server.application(method, self.path, body))
        except Exception:
            self._send(json_response({"error": "REQUEST_REJECTED"}, 400))

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_OPTIONS(self) -> None:
        self._send(json_response({"error": "REQUEST_REJECTED"}, 403))


def serve(server: LocalReviewServer, private_root: Path) -> None:
    """Open the private UI locally; never print its bearer token or private data."""
    url = server.origin + "/#token=" + server.token
    locator = private_root / ".local-review-url"
    write_private(locator, url.encode(), overwrite=locator.exists())
    try:
        webbrowser.open(url, new=1)
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        locator.unlink(missing_ok=True)


def browser_script() -> str:
    return """const token=new URLSearchParams(location.hash.slice(1)).get('token');history.replaceState(null,'','/');async function api(path,body){const options={headers:{'Authorization':'Bearer '+token}};if(body!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.headers['X-DeidFlow-CSRF']=token;options.body=JSON.stringify(body);}const response=await fetch(path,options);if(!response.ok)throw new Error('Request rejected');return response;}function showError(){document.getElementById('message').textContent='Request rejected. Check the local configuration and consent.';}"""
