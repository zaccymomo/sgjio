# Gateway

nginx on port 8000 (container 8080): the only way in from a browser. Both Vite dev servers proxy `/api` here, so the front ends still see one origin and one API. It routes each path to its service, asks Identity who is signed in on every protected request, and answers its own errors in the API's JSON shape. It owns no data.

## Routing

The full table, numbered, is `templates/gateway.conf.template`.

| Paths                                                                                                                    | Service                      | Session check                              |
| ------------------------------------------------------------------------------------------------------------------------ | ---------------------------- | ------------------------------------------ |
| `/api/auth/*`, `/api/admin/auth/*`, `/api/admin/admins*`, `/api/admin/ping`, `/api/profile*`, `/api/intro/*`             | Identity                     | none here: Identity checks its own cookies |
| `/api/admin/topics*`, `/api/admin/lessons*`, `/api/admin/media`, `/api/admin/reports*`, `/api/admin/aptitude-questions*` | Content                      | admin                                      |
| `/api/lessons/{id}/reports`                                                                                              | Content                      | app                                        |
| `/api/media/*`                                                                                                           | Content                      | none (public)                              |
| `/api/lessons/*`, `/api/attempts/*`, `/api/progress`, `/api/topics/*`, `/api/search`, `/api/review`, `/api/aptitude/*`   | Learning                     | app                                        |
| `/api/admin/lessons/{id}/insights`                                                                                       | Learning                     | admin                                      |
| `/api/health`                                                                                                            | the gateway itself           | none                                       |
| anything else, including `/internal/*`                                                                                   | 404 `{"detail":"Not Found"}` |                                            |

## Session check (forward auth)

For a protected route nginx makes an `auth_request` subrequest, without the body, to Identity's `GET /internal/auth/app` or `/internal/auth/admin` (the scope comes from the path), sending only `Cookie`, `X-Request-ID`, `X-Forwarded-For` and `X-Gateway-Key`.

- 200: nginx copies `X-User-Id`, `X-User-Scope`, `X-User-Role`, `X-User-Type` and `X-Profile-Completed` onto the request (replacing any the client sent), adds `X-Gateway-Key`, and relays Identity's refreshed session cookie to the browser.
- 401: `{"detail":{"code":"not_signed_in",...}}`. A request with no cookie for that scope gets this at once, without asking Identity, so a visitor still sees sign-in while Identity is down.
- Identity down or slower than 2 s: 503 `service_unavailable` with `Retry-After: 5`.

There is no cache: signing out or deleting an account takes effect on the next request. On unprotected routes, client `X-User-*` headers are dropped. Content and Learning refuse any request without the right `X-Gateway-Key`, and inside Docker only the gateway can reach the services (it is on `identity-net`, `content-net` and `learning-net`; no two services share a network), so going around the gateway gets nowhere. The compose default key (`dev-gateway-key`) is in the repository, so on the development machine itself the `127.0.0.1` service ports can be called with it: set `GATEWAY_KEY` (in a root `.env`) anywhere else.

## Errors and limits

| Case                                          | Answer                                      |
| --------------------------------------------- | ------------------------------------------- |
| a service is down (cannot connect)            | 503 `service_unavailable`, `Retry-After: 5` |
| a service connects but answers after 15 s     | 504 `gateway_timeout`                       |
| body over 10 MB (20 MB on `/api/admin/media`) | 413 `payload_too_large` / `media_too_large` |

Errors a service returns pass through unchanged. Every response carries `X-Request-ID` (the client's, or a new one), which is also sent to the service and logged as JSON by both.

## Settings

`GATEWAY_KEY` (required: the container refuses to start without it), `IDENTITY_UPSTREAM`, `CONTENT_UPSTREAM`, `LEARNING_UPSTREAM`, `MEDIA_MAX_MB`. Upstreams are resolved through Docker's DNS on each request, so the gateway starts, and keeps serving other routes, while a service is down.

## Tests

```bash
services/gateway/tests/run.sh    # needs docker, python3 and curl; uses ports 18080-18081
```

It builds the image, runs `nginx -t`, starts it beside three stub services on a private network, and checks every route, the auth headers, limits, a slow service (504), an unreachable one (503), Content down and Identity down. Its containers and network (`sgjio-gwtest-*`) are removed afterwards. CI runs it in the Gateway job.
