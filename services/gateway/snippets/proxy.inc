# Every proxied location: where to send it and what to tell the service.
# The location sets $upstream (host:port) first. Timeouts are set at server level.
proxy_pass http://$upstream;
proxy_set_header Connection "";
proxy_set_header Host $http_host;
proxy_set_header X-Request-ID $req_id;
# Overwritten, never appended, so a forged header never reaches Identity's lockout log.
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
# Proves the request came through the gateway; Content and Learning refuse it otherwise.
proxy_set_header X-Gateway-Key $gateway_key;
# The service echoes the id too; send it once.
proxy_hide_header X-Request-ID;
add_header X-Request-ID $req_id always;
