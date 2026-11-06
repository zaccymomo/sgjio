"""A stand-in for identity, content and learning, for the gateway's route tests.

Run as one container per service name (SERVICE_NAME), standard library only.

- GET /internal/auth/{app,admin}: Identity's session check, following the auth contract in
  contracts/README.md. Sessions are fixed test tokens (see SESSIONS). The request must carry
  the gateway key and a request id, and no body, or the check answers 400 (which the
  gateway turns into 503, failing the test that made it).
- /…/status/<code>: answers that status with a JSON body, to show errors pass through.
- /api/media/…: honours Range (206) and If-None-Match (304) like Content does.
- anything else: 200 with what arrived (service, method, raw path, headers, body length).
"""

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE = os.environ.get("SERVICE_NAME", "stub")
GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "")
USER_ID = "11111111-1111-4111-8111-111111111111"
ADMIN_ID = "22222222-2222-4222-8222-222222222222"

# cookie value -> (scope, principal headers, refresh?)
SESSIONS = {
    ("app", "user-ok"): {"X-User-Id": USER_ID, "X-User-Role": "user", "X-User-Type": "newcomer",
                         "X-Profile-Completed": "true"},
    ("app", "user-refresh"): {"X-User-Id": USER_ID, "X-User-Role": "user",
                              "X-User-Type": "newcomer", "X-Profile-Completed": "false"},
    ("admin", "admin-ok"): {"X-User-Id": ADMIN_ID, "X-User-Role": "admin", "X-User-Type": "",
                            "X-Profile-Completed": "false"},
}
COOKIES = {"app": "sgjio_session", "admin": "sgjio_admin_session"}
MEDIA = b"0123456789"


def _cookies(header: str) -> dict:
    jar = {}
    for part in header.split(";"):
        if "=" in part:
            name, value = part.strip().split("=", 1)
            jar[name] = value
    return jar


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # quiet
        pass

    def _send(self, status: int, body: bytes = b"", headers: dict | None = None,
              content_type: str = "application/json") -> None:
        self.send_response(status)
        if body or status not in (204, 304):
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload, headers: dict | None = None) -> None:
        self._send(status, json.dumps(payload).encode(), headers)

    def _body_length(self) -> int:
        length = int(self.headers.get("Content-Length") or 0)
        remaining = length
        while remaining:
            chunk = self.rfile.read(min(remaining, 1 << 20))
            if not chunk:
                break
            remaining -= len(chunk)
        return length

    def _auth(self, scope: str) -> None:
        if self.headers.get("X-Gateway-Key") != GATEWAY_KEY:
            return self._send(400)
        if not self.headers.get("X-Request-ID"):
            return self._send(400)
        if self.headers.get("Content-Length") not in (None, "0"):
            return self._send(400)
        if any(name.lower().startswith("x-user-") for name in self.headers.keys()):
            return self._send(400)
        token = _cookies(self.headers.get("Cookie", "")).get(COOKIES[scope])
        if token == "slow":
            time.sleep(4)
        principal = SESSIONS.get((scope, token))
        if principal is None:
            return self._send(401)
        headers = {**principal, "X-User-Scope": scope}
        if token == "user-refresh":
            headers["Set-Cookie"] = (
                "sgjio_session=user-refresh; HttpOnly; Max-Age=604800; Path=/api; SameSite=lax"
            )
        self._send(200, headers=headers)

    def _handle(self) -> None:
        match = re.fullmatch(r"/internal/auth/(app|admin)", self.path)
        if match and SERVICE == "identity":
            return self._auth(match[1])
        length = self._body_length()
        if "/slow-answer" in self.path:
            time.sleep(17)  # past the gateway's 15 s read timeout
        status = re.search(r"/status/(\d{3})$", self.path.split("?")[0])
        if status:
            code = int(status[1])
            return self._json(code, {"detail": {"code": "from_upstream", "service": SERVICE}},
                              {"Retry-After": "7"} if code == 429 else None)
        if self.path.startswith("/api/media/"):
            if self.headers.get("If-None-Match") == '"abc"':
                return self._send(304, headers={"ETag": '"abc"'})
            ranged = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
            if ranged:
                start, end = int(ranged[1]), int(ranged[2])
                return self._send(206, MEDIA[start:end + 1], {
                    "Content-Range": f"bytes {start}-{end}/{len(MEDIA)}", "ETag": '"abc"',
                }, "audio/mpeg")
        self._json(200, {
            "service": SERVICE,
            "method": self.command,
            "path": self.path,
            "headers": {name.lower(): value for name, value in self.headers.items()},
            "body_length": length,
        }, {"X-Request-ID": "from-upstream-should-be-hidden"})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _handle


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
