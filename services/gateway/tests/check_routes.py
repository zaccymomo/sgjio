"""Checks the running gateway against stub upstreams (run by run.sh; standard library only).

    python3 check_routes.py http://127.0.0.1:18080 <gateway-key> <phase>

phase "all-up" checks routing, auth, headers, limits and pass-through; "content-down" and
"identity-down" check what happens when a service is unreachable.
"""

import http.client
import json
import sys
from urllib.parse import urlsplit

BASE = urlsplit(sys.argv[1])
KEY = sys.argv[2]
PHASE = sys.argv[3]
USER_ID = "11111111-1111-4111-8111-111111111111"
ADMIN_ID = "22222222-2222-4222-8222-222222222222"
APP = "sgjio_session=user-ok"
ADMIN = "sgjio_admin_session=admin-ok"
NOT_SIGNED_IN = b'{"detail":{"code":"not_signed_in","message":"Please sign in to continue."}}'
NOT_FOUND = b'{"detail":"Not Found"}'

failures: list[str] = []
checks = 0


def request(method: str, path: str, cookie: str | None = None, headers: dict | None = None,
            body: bytes | None = None):
    connection = http.client.HTTPConnection(BASE.hostname, BASE.port, timeout=30)
    sent = dict(headers or {})
    if cookie:
        sent["Cookie"] = cookie
    try:
        connection.request(method, path, body=body, headers=sent)
        response = connection.getresponse()
        data = response.read()
    except (ConnectionError, http.client.HTTPException) as error:
        return 0, {}, str(error).encode(), []
    finally:
        connection.close()
    return response.status, {k.lower(): v for k, v in response.getheaders()}, data, \
        response.getheaders()


def check(name: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{name}: {detail}")


def echo(data: bytes) -> dict:
    try:
        return json.loads(data)
    except ValueError:
        return {}


# (method, path, service, auth) for every path the front ends call (web/src, admin/src,
# packages/ui/src), plus the regex routes' neighbours. auth: None, "app" or "admin".
ROUTES = [
    # Identity, passed straight through
    ("POST", "/api/auth/sign-in", "identity", None),
    ("POST", "/api/auth/register", "identity", None),
    ("POST", "/api/auth/google", "identity", None),
    ("GET", "/api/auth/privacy-notice-version", "identity", None),
    ("GET", "/api/auth/me", "identity", None),
    ("POST", "/api/auth/sign-out", "identity", None),
    ("POST", "/api/auth/change-password", "identity", None),
    ("POST", "/api/auth/delete-account", "identity", None),
    ("POST", "/api/auth/forgot-password", "identity", None),
    ("POST", "/api/auth/reset-password/check", "identity", None),
    ("POST", "/api/auth/reset-password", "identity", None),
    ("POST", "/api/admin/auth/sign-in", "identity", None),
    ("GET", "/api/admin/auth/me", "identity", None),
    ("POST", "/api/admin/auth/invite/check", "identity", None),
    ("POST", "/api/admin/auth/invite/accept", "identity", None),
    ("POST", "/api/admin/auth/forgot-password", "identity", None),
    ("GET", "/api/admin/admins", "identity", None),
    ("POST", "/api/admin/admins", "identity", None),
    ("POST", "/api/admin/admins/abc/resend-invite", "identity", None),
    ("POST", "/api/admin/admins/abc/remove", "identity", None),
    ("POST", "/api/admin/admins/abc/restore", "identity", None),
    ("GET", "/api/admin/ping", "identity", None),
    ("GET", "/api/profile", "identity", None),
    ("PUT", "/api/profile", "identity", None),
    ("GET", "/api/profile/options", "identity", None),
    ("POST", "/api/intro/finished", "identity", None),
    # Content
    ("GET", "/api/admin/topics", "content", "admin"),
    ("POST", "/api/admin/topics", "content", "admin"),
    ("PUT", "/api/admin/topics/order", "content", "admin"),
    ("PATCH", "/api/admin/topics/abc", "content", "admin"),
    ("DELETE", "/api/admin/topics/abc", "content", "admin"),
    ("POST", "/api/admin/topics/abc/archive", "content", "admin"),
    ("POST", "/api/admin/topics/abc/restore", "content", "admin"),
    ("GET", "/api/admin/lessons", "content", "admin"),
    ("POST", "/api/admin/lessons", "content", "admin"),
    ("PUT", "/api/admin/lessons/order", "content", "admin"),
    ("GET", "/api/admin/lessons/abc", "content", "admin"),
    ("PATCH", "/api/admin/lessons/abc", "content", "admin"),
    ("DELETE", "/api/admin/lessons/abc", "content", "admin"),
    ("POST", "/api/admin/lessons/abc/publish", "content", "admin"),
    ("POST", "/api/admin/lessons/abc/discard", "content", "admin"),
    ("POST", "/api/admin/lessons/abc/withdraw", "content", "admin"),
    ("POST", "/api/admin/lessons/abc/restore", "content", "admin"),
    ("POST", "/api/admin/media", "content", "admin"),
    ("GET", "/api/admin/reports?status=open", "content", "admin"),
    ("PUT", "/api/admin/reports/abc/status", "content", "admin"),
    ("GET", "/api/admin/aptitude-questions", "content", "admin"),
    ("POST", "/api/admin/aptitude-questions", "content", "admin"),
    ("PATCH", "/api/admin/aptitude-questions/abc", "content", "admin"),
    ("GET", "/api/media/abc", "content", None),
    ("POST", "/api/lessons/abc/reports", "content", "app"),
    # Learning
    ("GET", "/api/admin/lessons/abc/insights?version=2&learners=newcomer", "learning", "admin"),
    ("GET", "/api/lessons/abc", "learning", "app"),
    ("POST", "/api/lessons/abc/attempts", "learning", "app"),
    ("POST", "/api/attempts/abc/answers", "learning", "app"),
    ("POST", "/api/attempts/abc/finish", "learning", "app"),
    ("GET", "/api/progress", "learning", "app"),
    ("GET", "/api/topics/abc", "learning", "app"),
    ("GET", "/api/search?q=chope%20lah", "learning", "app"),
    ("GET", "/api/review", "learning", "app"),
    ("POST", "/api/aptitude/start", "learning", "app"),
    ("POST", "/api/aptitude/next", "learning", "app"),
    ("POST", "/api/aptitude/submit", "learning", "app"),
    ("POST", "/api/aptitude/skip", "learning", "app"),
    ("GET", "/api/aptitude/result", "learning", "app"),
]
FORGED = {
    "X-User-Id": "99999999-9999-4999-8999-999999999999",
    "X-User-Scope": "admin",
    "X-User-Role": "admin",
    "X-User-Type": "singaporean",
    "X-Profile-Completed": "true",
    "X-Gateway-Key": "forged",
    "X-Forwarded-For": "6.6.6.6",
}


def all_up() -> None:
    # Gateway's own answers
    status, headers, data, _ = request("GET", "/api/health")
    check("health", status == 200 and data == b'{"status":"ok"}', f"{status} {data!r}")
    check("health json", headers.get("content-type") == "application/json", str(headers))
    for path in ["/api/nope", "/", "/api/docs", "/api/openapi.json", "/_auth/app",
                 "/_auth/admin", "/internal/auth/app", "/api/admin/unknown"]:
        status, headers, data, _ = request("GET", path, cookie=f"{APP}; {ADMIN}")
        check(f"404 {path}", status == 404 and data == NOT_FOUND, f"{status} {data!r}")
        check(f"404 json {path}", headers.get("content-type") == "application/json")

    for method, path, service, auth in ROUTES:
        name = f"{method} {path}"
        cookie = {None: None, "app": APP, "admin": ADMIN}[auth]
        status, headers, data, _ = request(method, path, cookie=cookie, headers=FORGED,
                                           body=b"{}" if method != "GET" else None)
        body = echo(data)
        check(f"{name} routed", status == 200 and body.get("service") == service,
              f"{status} {data[:200]!r}")
        if status != 200:
            continue
        sent = body["headers"]
        check(f"{name} raw path", body["path"] == path, body["path"])
        check(f"{name} gateway key", sent.get("x-gateway-key") == KEY, sent.get("x-gateway-key"))
        check(f"{name} xff overwritten", "6.6.6.6" not in sent.get("x-forwarded-for", ""),
              sent.get("x-forwarded-for"))
        check(f"{name} request id", bool(sent.get("x-request-id")))
        if auth is None:
            check(f"{name} principal stripped",
                  not any(h.startswith("x-user-") or h == "x-profile-completed" for h in sent),
                  str(sent))
        elif auth == "app":
            check(f"{name} app principal",
                  sent.get("x-user-id") == USER_ID and sent.get("x-user-scope") == "app"
                  and sent.get("x-user-role") == "user" and sent.get("x-user-type") == "newcomer"
                  and sent.get("x-profile-completed") == "true", str(sent))
        else:
            check(f"{name} admin principal",
                  sent.get("x-user-id") == ADMIN_ID and sent.get("x-user-scope") == "admin"
                  and sent.get("x-user-role") == "admin" and "x-user-type" not in sent, str(sent))

        if auth is not None:
            # Signed out, or signed in to the other front end only: 401, today's exact body.
            others = [None, ADMIN] if auth == "app" else [None, APP, "sgjio_admin_session=nope"]
            for other in others:
                status, headers, data, _ = request(method, path, cookie=other)
                check(f"{name} 401 with {other}", status == 401 and data == NOT_SIGNED_IN,
                      f"{status} {data!r}")
                check(f"{name} 401 json", headers.get("content-type") == "application/json")

    # Correlation id: the client's one is passed on and returned once; otherwise one is made.
    status, headers, data, raw = request("GET", "/api/progress", APP,
                                         {"X-Request-ID": "req-test-123"})
    check("request id passed", echo(data)["headers"].get("x-request-id") == "req-test-123")
    returned = [v for k, v in raw if k.lower() == "x-request-id"]
    check("request id returned once", returned == ["req-test-123"], str(returned))
    status, headers, data, _ = request("GET", "/api/progress", APP)
    made = echo(data)["headers"].get("x-request-id")
    check("request id made", bool(made) and headers.get("x-request-id") == made, str(made))
    status, headers, data, _ = request("GET", "/api/nope")
    check("request id on gateway errors", bool(headers.get("x-request-id")))
    status, headers, data, _ = request("GET", "/api/progress")
    check("request id on 401", bool(headers.get("x-request-id")))

    # Sliding session refresh: Identity's Set-Cookie reaches the browser.
    status, headers, data, _ = request("GET", "/api/progress", "sgjio_session=user-refresh")
    check("set-cookie relayed", status == 200 and
          headers.get("set-cookie", "").startswith("sgjio_session=user-refresh"), str(headers))
    status, headers, data, _ = request("GET", "/api/progress", APP)
    check("no set-cookie without refresh", "set-cookie" not in headers, str(headers))

    # Service errors pass through untouched, including 401 and 404 bodies.
    for path, cookie, code in [("/api/lessons/abc/status/409", APP, 409),
                               ("/api/auth/status/401", None, 401),
                               ("/api/auth/status/429", None, 429),
                               ("/api/admin/topics/status/404", ADMIN, 404),
                               ("/api/progress/status/422", APP, 404),  # = route: not proxied
                               ("/api/topics/x/status/500", APP, 500),
                               ("/api/media/x/status/404", None, 404)]:
        status, headers, data, _ = request("GET", path, cookie)
        body = echo(data)
        if path.startswith("/api/progress/"):
            check(f"{path} not routed", status == 404 and data == NOT_FOUND, f"{status} {data!r}")
            continue
        check(f"{path} passes through", status == code and
              body.get("detail", {}).get("code") == "from_upstream", f"{status} {data!r}")
        if code == 429:
            check("retry-after passes", headers.get("retry-after") == "7", str(headers))

    # Body limits: 10 MB by default, 20 MB on media upload, JSON 413s.
    eleven = b"x" * (11 * 1024 * 1024)
    status, headers, data, _ = request("POST", "/api/admin/lessons", ADMIN, body=eleven)
    check("413 default", status == 413 and echo(data).get("detail", {}).get("code") ==
          "payload_too_large", f"{status} {data!r}")
    status, headers, data, _ = request("POST", "/api/admin/media", ADMIN, body=eleven)
    check("media 11 MB reaches content", status == 200 and
          echo(data).get("body_length") == len(eleven), f"{status} {data[:200]!r}")
    status, headers, data, _ = request("POST", "/api/admin/media", ADMIN,
                                       body=b"x" * (21 * 1024 * 1024))
    check("413 media", status == 413 and data == (
        b'{"detail":{"code":"media_too_large","message":"That file is too large. '
        b'The limit is 15 MB."}}'), f"{status} {data!r}")
    check("413 json", headers.get("content-type") == "application/json")

    # Public media streams: Range and If-None-Match reach Content; 206 and 304 come back.
    status, headers, data, _ = request("GET", "/api/media/abc", headers={"Range": "bytes=2-5"})
    check("media range", status == 206 and data == b"2345" and
          headers.get("content-range") == "bytes 2-5/10", f"{status} {headers} {data!r}")
    status, headers, data, _ = request("GET", "/api/media/abc", headers={"If-None-Match": '"abc"'})
    check("media 304", status == 304 and data == b"", f"{status} {data!r}")
    status, headers, data, _ = request("GET", "/api/media/abc", headers={
        "Authorization": "Bearer x"})
    check("media authorization stripped", "authorization" not in echo(data).get("headers", {}))

    # Identity too slow: the auth check gives up after 2 s and answers 503.
    status, headers, data, _ = request("GET", "/api/progress", "sgjio_session=slow")
    check("auth timeout -> 503", status == 503 and
          echo(data).get("detail", {}).get("code") == "service_unavailable", f"{status} {data!r}")


def content_down() -> None:
    status, headers, data, _ = request("GET", "/api/media/abc")
    check("content down: media 503", status == 503 and
          echo(data).get("detail", {}).get("code") == "service_unavailable", f"{status} {data!r}")
    status, headers, data, _ = request("GET", "/api/admin/topics", ADMIN)
    check("content down: admin 503", status == 503, f"{status} {data!r}")
    status, headers, data, _ = request("GET", "/api/progress", APP)
    check("content down: learning still up", status == 200, f"{status} {data!r}")
    status, headers, data, _ = request("GET", "/api/health")
    check("content down: health", status == 200, f"{status} {data!r}")


def identity_down() -> None:
    for path in ["/api/progress", "/api/admin/lessons/abc/insights"]:
        status, headers, data, _ = request("GET", path, f"{APP}; {ADMIN}")
        check(f"identity down: {path} 503", status == 503 and
              echo(data).get("detail", {}).get("code") == "service_unavailable",
              f"{status} {data!r}")
    status, headers, data, _ = request("GET", "/api/auth/me", APP)
    check("identity down: identity route 503", status == 503, f"{status} {data!r}")
    status, headers, data, _ = request("GET", "/api/health")
    check("identity down: health", status == 200, f"{status} {data!r}")


{"all-up": all_up, "content-down": content_down, "identity-down": identity_down}[PHASE]()
for failure in failures:
    print("FAIL", failure)
print(f"{PHASE}: {checks - len(failures)}/{checks} checks passed")
sys.exit(1 if failures else 0)
