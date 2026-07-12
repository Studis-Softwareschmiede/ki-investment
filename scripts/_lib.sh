#!/usr/bin/env bash
# Gemeinsame Helfer — NICHT direkt ausführen, nur via source.
# GPG-Passphrase-Auflösung (eigene Secret-Domäne der Softwareschmiede):
#   $GPG_PASS_FILE > /etc/softwareschmiede/gpg.pass > ~/.config/softwareschmiede/gpg.pass
#   > $GPG_PASSPHRASE > interaktiver Prompt
resolve_pass_file() {
  local f
  for f in "${GPG_PASS_FILE:-}" "/etc/softwareschmiede/gpg.pass" "$HOME/.config/softwareschmiede/gpg.pass"; do
    [[ -n "$f" && -r "$f" ]] && { printf '%s' "$f"; return 0; }
  done
  return 1
}
