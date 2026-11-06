#!/usr/bin/env bash
# Gateway route tests: builds the gateway image, starts it on a private network beside three
# stub upstreams (identity, content, learning), checks every route, then takes services down.
#
#   services/gateway/tests/run.sh            (needs docker and python3; port 18080 free)
#
# Uses its own network and containers (sgjio-gwtest-*), removed afterwards.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
GATEWAY_DIR="$(dirname "$HERE")"
PORT="${GATEWAY_TEST_PORT:-18080}"
KEY="gateway-test-key"
NET="sgjio-gwtest-net"
IMAGE="sgjio-gwtest-gateway"
STUB_IMAGE="python:3.11-slim"

cleanup() {
    docker rm -f sgjio-gwtest-gateway sgjio-gwtest-identity sgjio-gwtest-content \
        sgjio-gwtest-learning >/dev/null 2>&1 || true
    docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker build -q -t "$IMAGE" "$GATEWAY_DIR" >/dev/null
docker network create "$NET" >/dev/null

for svc in identity content learning; do
    docker run -d --name "sgjio-gwtest-$svc" --network "$NET" --network-alias "$svc" \
        -e SERVICE_NAME="$svc" -e GATEWAY_KEY="$KEY" \
        -v "$HERE/stub_upstream.py:/stub.py:ro" "$STUB_IMAGE" python -u /stub.py >/dev/null
done

docker run -d --name sgjio-gwtest-gateway --network "$NET" -p "127.0.0.1:$PORT:8080" \
    -e GATEWAY_KEY="$KEY" "$IMAGE" >/dev/null

echo "nginx -t:"
docker exec sgjio-gwtest-gateway nginx -t

for _ in $(seq 1 50); do
    if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 &&
        docker exec sgjio-gwtest-identity python -c \
            "import urllib.request; urllib.request.urlopen('http://localhost:8000/x')" 2>/dev/null; then
        break
    fi
    sleep 0.2
done

python3 "$HERE/check_routes.py" "http://127.0.0.1:$PORT" "$KEY" all-up
docker stop sgjio-gwtest-content >/dev/null
python3 "$HERE/check_routes.py" "http://127.0.0.1:$PORT" "$KEY" content-down
docker stop sgjio-gwtest-identity >/dev/null
python3 "$HERE/check_routes.py" "http://127.0.0.1:$PORT" "$KEY" identity-down

# Without GATEWAY_KEY the gateway must refuse to start.
if docker run --rm "$IMAGE" >/dev/null 2>&1; then
    echo "FAIL gateway started without GATEWAY_KEY"
    exit 1
fi
echo "gateway refuses to start without GATEWAY_KEY: ok"
echo "ALL GATEWAY CHECKS PASSED"
