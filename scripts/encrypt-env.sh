#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_lib.sh
source scripts/_lib.sh

[[ -f .env ]] || { echo "✖ .env fehlt — erst anlegen" >&2; exit 1; }

if pass_file="$(resolve_pass_file)"; then
  gpg --batch --yes --pinentry-mode loopback --passphrase-file "$pass_file" \
      --symmetric --cipher-algo AES256 -o .env.gpg .env
elif [[ -n "${GPG_PASSPHRASE:-}" ]]; then
  printf '%s' "$GPG_PASSPHRASE" | gpg --batch --yes --pinentry-mode loopback --passphrase-fd 0 \
      --symmetric --cipher-algo AES256 -o .env.gpg .env
else
  gpg --pinentry-mode loopback --symmetric --cipher-algo AES256 -o .env.gpg .env
fi
echo "✓ .env.gpg geschrieben — committen, .env bleibt lokal"
