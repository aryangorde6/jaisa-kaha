#!/usr/bin/env bash
# Fetches Switch's own 0.31.0 Compose file from GHCR, where Switch publishes it
# as an OCI artifact (ghcr.io/sandbox-quantum/standalone-compose:0.31.0, one
# YAML layer). It's fetched by its digest, so the bytes are exactly the ones this
# build was tested on, and the sha256 is checked again before the file is kept.
set -euo pipefail
cd "$(dirname "$0")"
REPO=sandbox-quantum/standalone-compose
DIGEST=cba238878078cf3d77fd9e136ef432f1ce5fd1bfe597acd172b9faa6720f0121  # 0.31.0, read Sat 24 Oct 2026
OUT=standalone-docker-compose.yml

sha() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }
if [ -f "$OUT" ] && [ "$(sha "$OUT")" = "$DIGEST" ]; then echo "deploy/$OUT already there (sha256 matches)"; exit 0; fi

# GHCR gives anyone a pull token for a public package; it's kept in a variable, never printed.
token=$(curl -fsS "https://ghcr.io/token?scope=repository:$REPO:pull" | sed -E 's/.*"token":"([^"]+)".*/\1/')
tmp=$(mktemp "$OUT.XXXXXX")
trap 'rm -f "$tmp"' EXIT
curl -fsSL -H "Authorization: Bearer $token" "https://ghcr.io/v2/$REPO/blobs/sha256:$DIGEST" -o "$tmp"
got=$(sha "$tmp")
[ "$got" = "$DIGEST" ] || { echo "sha256 mismatch: got $got, want $DIGEST. Not kept."; exit 1; }
mv "$tmp" "$OUT"
trap - EXIT
echo "deploy/$OUT fetched from ghcr.io/$REPO (sha256 $DIGEST)"
