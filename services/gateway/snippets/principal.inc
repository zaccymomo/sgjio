# After `auth_request /_auth/{app,admin};`: copy who Identity says this is onto the request.
# proxy_set_header replaces any copy the client sent, so these can't be forged.
auth_request_set $auth_user_id $upstream_http_x_user_id;
auth_request_set $auth_user_scope $upstream_http_x_user_scope;
auth_request_set $auth_user_role $upstream_http_x_user_role;
auth_request_set $auth_user_type $upstream_http_x_user_type;
auth_request_set $auth_profile_completed $upstream_http_x_profile_completed;
# Identity's sliding session refresh, relayed to the browser (an empty value adds nothing).
auth_request_set $auth_cookie $upstream_http_set_cookie;
proxy_set_header X-User-Id $auth_user_id;
proxy_set_header X-User-Scope $auth_user_scope;
proxy_set_header X-User-Role $auth_user_role;
proxy_set_header X-User-Type $auth_user_type;
proxy_set_header X-Profile-Completed $auth_profile_completed;
add_header Set-Cookie $auth_cookie always;
