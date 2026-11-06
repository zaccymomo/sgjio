# Routes with no gateway auth (Identity's own routes, public media): drop any principal
# headers the client sent. An empty value means nginx does not send the header at all.
proxy_set_header X-User-Id "";
proxy_set_header X-User-Scope "";
proxy_set_header X-User-Role "";
proxy_set_header X-User-Type "";
proxy_set_header X-Profile-Completed "";
