# JSON bodies for errors the gateway itself produces. Errors from services pass through
# untouched (proxy_intercept_errors off), so these never replace a service's own 401 or 404.
# A location that sets any error_page loses the server's, so it includes this file again.
error_page 401 @not_signed_in;
error_page 404 @not_found;
# 500 here is an auth_request whose Identity call failed (Identity down or timing out).
error_page 500 502 503 =503 @unavailable;
error_page 504 @timeout;
