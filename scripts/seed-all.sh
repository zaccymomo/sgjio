#!/usr/bin/env bash
# Seed every service, in order, through the running compose stack:
#
#   docker compose up -d --build --wait && scripts/seed-all.sh [--demo [COUNT]]
#
# 1. identity  python -m app.cli seed     seed users (deterministic ids, contracts/README.md),
#                                         publishing identity.user.registered
# 2. content   python -m app.cli seed     topics, lessons from /srv/content (published), the
#                                         aptitude bank, publishing content.* events
# 3. learning  python -m app.cli wait-for-read-models
#                                         blocks until Learning's read models hold what the
#                                         two seeds published (exit 0), or times out (exit 1)
# 4. learning  python -m app.cli seed     seed learners' completions and aptitude results,
#                                         found through the read models by natural keys
#
# --demo [COUNT] (default 60) then adds demo learners for lesson insights (SCRUM-84):
# 5. identity  python -m app.cli seed-demo-learners --count COUNT   (prints a run nonce)
# 6. learning  python -m app.cli demo-activity --count COUNT --run-nonce <that nonce>
#
# Every step is safe to run again: the seeds only add what is missing, and the demo replaces
# the previous demo learners (Identity deletes them, Learning erases their data).
#
# Order matters: the services must be running before anything is seeded, because each
# consumer declares and binds its queue when it starts. An event published before a queue
# was bound goes to sgjio.unrouted and Learning never sees it. So this script first makes
# sure the stack is up (`docker compose up -d --wait`, which does nothing if it already is).
set -euo pipefail

cd "$(dirname "$0")/.."

demo_count=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --demo)
            demo_count=60
            if [[ $# -gt 1 && "$2" =~ ^[0-9]+$ ]]; then
                demo_count="$2"
                shift
            fi
            ;;
        -h | --help)
            sed -n '2,25p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1 (try --help)" >&2
            exit 2
            ;;
    esac
    shift
done

services=(identity content learning notification gateway)
running=$(docker compose ps --status running --services 2>/dev/null || true)
for service in "${services[@]}"; do
    if ! grep -qx "$service" <<<"$running"; then
        echo "==> starting the stack ($service is not running)"
        docker compose up -d --wait
        break
    fi
done

run() {
    local service="$1"
    shift
    echo "==> $service: python -m app.cli $*"
    docker compose exec -T "$service" python -m app.cli "$@"
}

run identity seed
run content seed
run learning wait-for-read-models --timeout "${SEED_WAIT_SECONDS:-60}"
run learning seed

if [[ -n "$demo_count" ]]; then
    echo "==> identity: python -m app.cli seed-demo-learners --count $demo_count"
    output=$(docker compose exec -T identity python -m app.cli seed-demo-learners --count "$demo_count")
    echo "$output"
    nonce=$(sed -n 's/^run nonce: *\([0-9A-Za-z_-]*\)$/\1/p' <<<"$output" | tail -n 1)
    if [[ -z "$nonce" ]]; then
        echo "seed-demo-learners did not print a run nonce" >&2
        exit 1
    fi
    run learning demo-activity --count "$demo_count" --run-nonce "$nonce" \
        --timeout "${SEED_WAIT_SECONDS:-60}"
fi

echo "Seeded. Main app: newcomer@sgjio.example.com / UserPass123; admin: admin@sgjio.example.com / AdminPass123"
