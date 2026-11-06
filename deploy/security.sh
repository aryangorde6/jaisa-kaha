#!/usr/bin/env bash
# Pre-push checks. Each prints what it found; the script fails if any did.
# It scans the files that would be committed (tracked, plus untracked files
# that aren't ignored), so it works before the first commit too.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
check() {  # check "<what>" <command...>: the command's output is the finding
    local what=$1; shift
    local out
    out=$("$@" 2>/dev/null)
    if [ -n "$out" ]; then
        echo "FAIL  $what"
        echo "$out" | head -20 | sed 's/^/      /'
        fail=1
    else
        echo "ok    $what"
    fi
}
skipped=0
skip() { echo "skip  $1"; skipped=$((skipped + 1)); }  # a check that can't run here says so, never "ok"

# NUL-separated, so it works with GNU and BSD (macOS) xargs alike.
files() { git ls-files --cached --others --exclude-standard; }
each() { tr '\n' '\0' | xargs -0 "$@"; }
scan() { files | grep -v '^tests/' | each grep -nIE "$@" --; }
export -f files each scan

# The machinery itself: if git, tr, xargs and grep can't find this script's own
# last line in this file, every "ok" below would be hollow, so stop here.
case "$(files | each grep -l 'make security: all clear' -- 2>/dev/null)" in
    *deploy/security.sh*) ;;
    *) echo "FAIL  the scan can't read the files here (git, tr, xargs or grep missing?)"; echo; echo "make security: FAILED"; exit 1 ;;
esac

# The three checks from the project rules, plus the files that must stay local.
# [l] keeps the name itself out of this file, which the second check scans too.
check "no assistant name in commit metadata" bash -c "git log --format='%an %ae %cn %ce%n%B' 2>/dev/null | grep -i 'c[l]aude'"
check "no assistant name in files" bash -c "files | each grep -il 'c[l]aude' --"
check "no assistant name in branches" bash -c "git branch -a | grep -i 'c[l]aude'"
check "private notes not committed" bash -c "files | grep -iE '(^|/)(c[l]aude\.md|handoff\.md|\.c[l]aude/)'"

# Secrets and family data (#8, #19).
check "no secrets files, keys, audio or data" bash -c "files | grep -E '(^|/)(\.env|agents\.env)$|(^|/)(keys|audio|data)/|\.(key|pem|m4a|ogg|opus|mp3|wav)$'"
check "no AWS keys, tokens or private keys in files" scan '(AKIA|ASIA)[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY|Bearer [A-Za-z0-9._-]{20,}|[MN][A-Za-z0-9]{23,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}'
if [ -f deploy/.env ]; then
    # every secret value in deploy/.env, looked for in every file, never printed
    check "no value from deploy/.env in any file" bash -c "
        grep -E '^(DB_PASSWORD|DB_OWNER_PASSWORD|AGENT_REGISTRATION_TOKEN|SECRET_KEYS|GATEWAY_ADMIN_PASSWORD)=' deploy/.env | cut -d= -f2- | sed 's/^[^:]*://' |
        while read -r v; do [ -n \"\$v\" ] && files | each grep -lF -- \"\$v\" ; done | sort -u"
fi

# SQL injection (#1): no string-built queries.
check "no string-built SQL" scan 'execute\(f"|execute\(".*%|\.format\(.*(SELECT|INSERT|UPDATE|DELETE)'

# The Gateway stays private (#3, #11, #12): every Switch port on 127.0.0.1, if it's running.
if command -v ss >/dev/null; then
    check "Switch listens on 127.0.0.1 only" bash -c "ss -ltn | awk '{print \$4}' | grep -E ':(3200|8100|5433)\$' | grep -v '^127\.0\.0\.1:'"
elif command -v lsof >/dev/null; then  # macOS
    check "Switch listens on 127.0.0.1 only" bash -c "lsof -nP -iTCP -sTCP:LISTEN | awk '{print \$9}' | grep -E ':(3200|8100|5433)\$' | grep -v '^127\.0\.0\.1:'"
else
    skip "Switch listens on 127.0.0.1 only (no ss or lsof here)"
fi

# Pinned images (#20): every running container of this stack uses a digest in deploy/images.lock.
if ! docker info >/dev/null 2>&1; then
    skip "running images match deploy/images.lock (Docker isn't running here)"
else
    check "running images match deploy/images.lock" bash -c "
    docker ps --filter label=com.docker.compose.project=jaisakaha --format '{{.Names}}' |
    while read -r c; do d=\$(docker inspect --format '{{.Image}}' \"\$c\"); grep -q \"@\$d\$\" deploy/images.lock || echo \"\$c runs \$d\"; done"
fi

if [ $fail -ne 0 ]; then echo; echo "make security: FAILED"; exit 1; fi
echo; [ $skipped -eq 0 ] && echo "make security: all clear" || echo "make security: all clear, but $skipped check(s) couldn't run here"
