#!/bin/sh
# Refuse to start without GATEWAY_KEY: Content and Learning only accept requests carrying it.
if [ -z "${GATEWAY_KEY:-}" ]; then
    echo "gateway: GATEWAY_KEY must be set" >&2
    exit 1
fi
