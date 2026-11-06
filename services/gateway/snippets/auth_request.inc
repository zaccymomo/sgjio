# Shared by the /_auth/* locations: ask Identity about the session, without the body.
# Only Cookie, X-Request-ID, X-Forwarded-For and X-Gateway-Key are sent.
internal;
proxy_pass_request_body off;
# The size limit belongs to the location that proxies the body (checked there already); the
# subrequest sees the same Content-Length and would otherwise apply the 10 MB default to it.
client_max_body_size 0;
proxy_pass_request_headers off;
proxy_set_header Content-Length "";
proxy_set_header Cookie $http_cookie;
proxy_set_header X-Request-ID $req_id;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Gateway-Key $gateway_key;
proxy_connect_timeout 2s;
proxy_send_timeout 2s;
proxy_read_timeout 2s;
