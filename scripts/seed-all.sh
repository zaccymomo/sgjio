#!/usr/bin/env bash
# Seed every service, in order, through the running compose stack:
#
#   docker compose up -d --build --wait && scripts/seed-all.sh
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
# Each command is the service builder's to implement with exactly these names. Every seed
# must be safe to run twice.
set -euo pipefail

cd "$(dirname "$0")/.."
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
echo "Seeded. Main app: newcomer@sgjio.example.com / UserPass123; admin: admin@sgjio.example.com / AdminPass123"
