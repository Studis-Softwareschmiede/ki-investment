#!/usr/bin/env bash
# SOURCE diese Datei:  source scripts/load-env.sh
# Entschlüsselt .env.gpg und exportiert die App-Secrets in die aktuelle Shell.
# Kein Klartext-Schreiben auf die Platte nötig.
_app_root="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
# shellcheck source=scripts/_lib.sh
source "$_app_root/scripts/_lib.sh"

if [[ -f "$_app_root/.env.gpg" ]]; then
  _app_pf="$(resolve_pass_file || true)"
  set -a
  if [[ -n "${_app_pf:-}" ]]; then
    eval "$(gpg --batch --quiet --pinentry-mode loopback --passphrase-file "$_app_pf" -d "$_app_root/.env.gpg")"
  elif [[ -n "${GPG_PASSPHRASE:-}" ]]; then
    eval "$(printf '%s' "$GPG_PASSPHRASE" | gpg --batch --quiet --pinentry-mode loopback --passphrase-fd 0 -d "$_app_root/.env.gpg")"
  else
    eval "$(gpg --quiet --pinentry-mode loopback -d "$_app_root/.env.gpg")"
  fi
  set +a
  echo "✓ .env.gpg geladen — App-Secrets in der Shell exportiert"
else
  echo "ℹ .env.gpg fehlt — noch keine Secrets geladen (bash scripts/encrypt-env.sh ausführen, sobald .env vorhanden)"
fi
unset _app_root _app_pf
