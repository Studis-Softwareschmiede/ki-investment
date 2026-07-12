#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/_lib.sh
source scripts/_lib.sh

[[ -f .env.gpg ]] || { echo "✖ .env.gpg fehlt" >&2; exit 1; }
umask 077

if pass_file="$(resolve_pass_file)"; then
  gpg --batch --yes --pinentry-mode loopback --passphrase-file "$pass_file" -d .env.gpg > .env
elif [[ -n "${GPG_PASSPHRASE:-}" ]]; then
  printf '%s' "$GPG_PASSPHRASE" | gpg --batch --yes --pinentry-mode loopback --passphrase-fd 0 -d .env.gpg > .env
else
  gpg --pinentry-mode loopback -d .env.gpg > .env
fi
chmod 600 .env
echo "✓ .env entschlüsselt (gitignored — nie committen)"
