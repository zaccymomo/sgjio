#!/usr/bin/env bash
# Run the end-to-end suite against the whole compose stack (project sgjio-ms):
#
#   scripts/e2e.sh [--clean] [--no-build] [--no-demo] [--resilience] [-- pytest args...]
#
# 1. brings the stack up and waits until every container is healthy (builds changed images
#    unless --no-build; --clean first wipes this project's containers and volumes)
# 2. seeds it (scripts/seed-all.sh, with --demo learners for the insights test unless
#    --no-demo); safe on a stack that is already seeded
# 3. makes e2e/.venv if it is missing (uv, Python 3.11) and runs pytest in e2e/
#
# The suite talks only to the gateway (:8000) and Mailpit (:8025), and makes fresh accounts
# and topics each run, so it can be run again without resetting anything. --resilience also
# runs the drills that stop and start containers (e2e/test_resilience.py).
set -euo pipefail

cd "$(dirname "$0")/.."

clean=0
build=1
demo=1
pytest_args=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --clean) clean=1 ;;
        --no-build) build=0 ;;
        --no-demo) demo=0 ;;
        --resilience) export E2E_RESILIENCE=1 ;;
        --)
            shift
            pytest_args=("$@")
            break
            ;;
        -h | --help)
            sed -n '2,15p' "$0"
            exit 0
            ;;
        *) pytest_args+=("$1") ;;
    esac
    shift
done

if [[ $clean == 1 ]]; then
    echo "==> docker compose down -v (project ${COMPOSE_PROJECT_NAME:-sgjio-ms} only)"
    docker compose down -v
fi

echo "==> docker compose up"
if [[ $build == 1 ]]; then
    docker compose up -d --build --wait
else
    docker compose up -d --wait
fi

if [[ $demo == 1 ]]; then
    scripts/seed-all.sh --demo "${E2E_DEMO_COUNT:-60}"
else
    scripts/seed-all.sh
fi

if [[ ! -x e2e/.venv/bin/python ]]; then
    echo "==> creating e2e/.venv"
    uv venv -q -p 3.11 e2e/.venv
    uv pip install -q -p e2e/.venv/bin/python -r e2e/requirements.txt
fi

echo "==> pytest e2e"
cd e2e
exec .venv/bin/python -m pytest "${pytest_args[@]}"
