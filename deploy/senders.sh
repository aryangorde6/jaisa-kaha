#!/usr/bin/env bash
# Switch sender ids for deploy/agents.env. Read-only. Sender ids aren't
# secrets: they're how Switch names who posted.
#
# Our agents tell everyone apart by these ids, because Switch's live events say
# which kind of sender a message came from only for the platform itself. The
# agents' lines can be pasted as they are. People are listed for you to pick
# from: your own id is JAISA_ARYAN_SENDER, Mom's is JAISA_MOM_SENDER, and Mom's
# username is JAISA_MOM_NAME (Pothi addresses her by it).
set -euo pipefail
cd "$(dirname "$0")/.."
query() {
    docker compose -f deploy/standalone-docker-compose.yml --env-file deploy/.env exec -T postgres \
        sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -At -F ' ' -c \"$1\""
}
query "select display_name, matrix_user_id from clients where type = 'agent' and display_name in ('tape', 'lekhak', 'pothi') order by created_at;" |
while read -r name sender; do
    printf 'JAISA_%s_SENDER=%s\n' "$(printf %s "$name" | tr a-z A-Z)" "$sender"
done
echo "# People Switch has seen in a bridged room (username, sender id):"
query "select display_name, matrix_user_id from clients where type = 'user' order by created_at;" |
while read -r name sender; do
    printf '#   %s  %s\n' "$name" "$sender"
done
