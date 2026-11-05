#!/usr/bin/env bash
# What's still missing before the three agents can run live. Read-only.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-python3}
missing=0
ok()   { echo "ok      $1"; }
todo() { echo "TODO    $1"; missing=$((missing + 1)); }
step() { if eval "$2" >/dev/null 2>&1; then ok "$1"; else todo "$1${3:+ ($3)}"; fi; }

step "Switch API healthy on 127.0.0.1:8100" "curl -fsS http://127.0.0.1:8100/health" "make up"
step "Gateway answers on 127.0.0.1:3200" "curl -fsS -o /dev/null http://127.0.0.1:3200/" "make up"
step "ffmpeg and ffprobe installed" "command -v ffmpeg && command -v ffprobe"
step "python has httpx and websockets" "$PY -c 'import httpx, websockets'" "PY=… or a venv"
step "AWS profile hackathon works" "AWS_PROFILE=hackathon aws sts get-caller-identity"
for name in Tape Lekhak Pothi; do
    step "$name registered (keys/$name.json, mode 600)" "[ \"\$(stat -c %a keys/$name.json)\" = 600 ]" "make register NAME=$name"
done
if [ -f deploy/agents.env ]; then
    set -a; . deploy/agents.env; set +a
    step "JAISA_ROOM set" "[ -n \"${JAISA_ROOM:-}\" ]" "the room id, after the first message in the channel"
    step "JAISA_BUCKET reachable" "[ -n \"${JAISA_BUCKET:-}\" ] && AWS_PROFILE=hackathon AWS_REGION=ap-south-1 aws s3api head-bucket --bucket \"$JAISA_BUCKET\""
    step "JAISA_ARYAN_SENDER set" "[ -n \"${JAISA_ARYAN_SENDER:-}\" ]" "Tape logs it the first time you write"
    step "JAISA_MOM_SENDER set" "[ -n \"${JAISA_MOM_SENDER:-}\" ]" "Pothi logs it the first time Mom writes"
    step "JAISA_TAPE_SENDER set" "[ -n \"${JAISA_TAPE_SENDER:-}\" ]" "make senders"
    step "JAISA_LEKHAK_SENDER set" "[ -n \"${JAISA_LEKHAK_SENDER:-}\" ]" "make senders"
    step "JAISA_POTHI_SENDER set" "[ -n \"${JAISA_POTHI_SENDER:-}\" ]" "make senders"
    step "JAISA_LEDGER_ROOM set" "[ -n \"${JAISA_LEDGER_ROOM:-}\" ]" "the family room's id, never #dev's"
    if [ -n "${JAISA_VOCABULARY:-}" ]; then
        step "vocabulary $JAISA_VOCABULARY READY" "[ \"\$(AWS_PROFILE=hackathon AWS_REGION=ap-south-1 aws transcribe get-vocabulary --vocabulary-name $JAISA_VOCABULARY --query VocabularyState --output text)\" = READY ]"
    fi
else
    todo "deploy/agents.env (copy deploy/agents.env.example)"
fi
step "prompts committed (frozen before the first real recording)" "git ls-files --error-unmatch prompts/baseline-v1.txt prompts/lekhak-v1.txt && git diff --quiet HEAD -- prompts/" "git commit"

echo
[ $missing -eq 0 ] && echo "make doctor: ready to go live" || echo "make doctor: $missing to do"
