# ADR 0005: Gateway forward auth with trusted headers

**Status:** accepted, built

## Context

Content and Learning need to know who is calling, but sessions live in Identity's database (ADR 0002), and the front ends must keep using the same cookies (`sgjio_session` on `/api`, `sgjio_admin_session` on `/api/admin`).

## Decision

- **nginx is the only way in** (port 8000). For a protected route it makes an `auth_request` subrequest, without the body, to Identity's `GET /internal/auth/app` or `/internal/auth/admin`. Identity runs the same checks its own routes run (session exists for that scope and is not expired, account not removed, admin for admin scope) and slides the session's expiry.
- On 200, Identity returns `X-User-Id`, `X-User-Scope`, `X-User-Role`, `X-User-Type` and `X-Profile-Completed`. nginx **replaces** any copies the client sent with these, and relays Identity's refreshed cookie to the browser. On 401 the gateway answers `not_signed_in` in the API's JSON shape.
- A request with **no cookie for that scope** is signed out for certain, so the gateway answers 401 without asking Identity.
- **No cache.** Every protected request asks Identity. Signing out, removing an administrator or deleting an account takes effect on the very next request.
- **`X-Gateway-Key`.** The gateway adds a shared secret to every proxied request. Content and Learning (`require_principal` in `app/platform/principal.py`) refuse a request without it, so the `X-User-*` headers can only have come from the gateway. Identity's `/internal/auth/*` refuses it too, and the gateway never routes `/internal/*`.

## Consequences

- Content and Learning hold no session logic; a route says `Depends(require_principal("app"))` and gets a `Principal`.
- One extra local HTTP hop per protected request (milliseconds on the compose network).
- **Identity is a hard dependency for signed-in routes:** if it is down they answer 503 `service_unavailable`. Public media and signed-out visitors still work (resilience drill `test_identity_down_refuses_signed_in_routes_but_serves_media`).
- The shared key is a development-grade trust boundary. In production it would be mutual TLS or a private network policy.
- Alternatives: signed JWTs checked by each service (no hop, but sign-out would not take effect until the token expired, and key rotation adds work); a short auth cache in nginx (planned at first, dropped so sign-out stays immediate).
