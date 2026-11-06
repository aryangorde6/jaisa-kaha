#!/usr/bin/env bash
# Who set each agent's addressing rule, from Switch's own log (read-only).
#   make rule-log                      everything since the container started
#   make rule-log AGENT=pothi BY=Mom   exits 1 if anyone but Mom changed Pothi's rule after her
# Why the log is enough, and its limits: jaisa/rulelog.py.
set -euo pipefail
cd "$(dirname "$0")/.."
compose() { docker compose -f deploy/standalone-docker-compose.yml --env-file deploy/.env "$@"; }
c=$(compose ps -q switch 2>/dev/null)
[ -n "$c" ] || { echo "Switch isn't running (make up)"; exit 1; }
started=$(docker inspect -f '{{.State.StartedAt}}' "$c")
args=(--started "$started")
[ -n "${AGENT:-}" ] && args+=("$AGENT")
[ -n "${BY:-}" ] && args+=(--by "$BY")
compose logs --no-color --no-log-prefix switch 2>&1 | "${PY:-python3}" -m jaisa.rulelog "${args[@]}"
