#!/usr/bin/env bash
# Writes deploy/.env with fresh secrets. Run it in your own terminal: it asks
# for the Gateway admin password and never prints it. Refuses to overwrite.
set -euo pipefail
cd "$(dirname "$0")"
[ -e .env ] && { echo "deploy/.env already exists; not touching it."; exit 1; }
read -rsp "Gateway admin password (12+ chars, no spaces): " p1; echo
read -rsp "Again: " p2; echo
[ "$p1" = "$p2" ] || { echo "They don't match."; exit 1; }
[ ${#p1} -ge 12 ] && [[ "$p1" != *[[:space:]\"\'\$\`\\]* ]] || { echo "Use 12+ characters, no spaces, quotes, \$, backtick or backslash."; exit 1; }
umask 077
sed -e "s/^DB_PASSWORD=$/DB_PASSWORD=$(openssl rand -hex 24)/" \
    -e "s/^DB_OWNER_PASSWORD=$/DB_OWNER_PASSWORD=$(openssl rand -hex 24)/" \
    -e "s/^AGENT_REGISTRATION_TOKEN=$/AGENT_REGISTRATION_TOKEN=$(openssl rand -hex 24)/" \
    -e "s/^SECRET_KEYS=$/SECRET_KEYS=rasoi1:$(openssl rand -hex 32)/" \
    .env.example > .env
printf 'GATEWAY_ADMIN_PASSWORD=%s\n' "$p1" > .env.pw
grep -v '^GATEWAY_ADMIN_PASSWORD=' .env > .env.tmp && cat .env.tmp .env.pw > .env && rm -f .env.tmp .env.pw
chmod 600 .env
echo "deploy/.env written (mode 600). Secrets were not printed."
