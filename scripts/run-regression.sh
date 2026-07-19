#!/usr/bin/env bash
# scripts/run-regression.sh — Playwright-Regressionslauf der 5
# Cockpit-Kern-Views gegen einen ephemeren, demo-geseedeten lokalen Stack
# (Story S-077, docs/specs/frontend-cockpit.md AC23).
#
# Provisioniert (und räumt GARANTIERT wieder ab, auch bei rotem Lauf/
# Zwischenfehler — `trap ... EXIT`):
#   1. Einen temporären Postgres-17-Container auf einem frei ermittelten
#      Host-Port (eigener Containername, keine Kollision mit einem
#      laufenden Preview-/Dev-Stack).
#   2. `uv run alembic upgrade head` gegen diesen Container.
#   3. `SEED_DEMO=1 uv run python -m app.demo.seed` (Demo-Seed, AC22).
#   4. `uv run uvicorn app.main:app` auf einem frei ermittelten lokalen Port.
#   5. Playwright gegen `REGRESSION_BASE_URL=http://127.0.0.1:<app-port>`.
#
# Usage:
#   scripts/run-regression.sh [<spec-datei-oder-verzeichnis> ...]
#   # Default: die fünf Cockpit-View-Suiten (AC23-Scope dieser Story)
#
# Requires: docker, uv, npx (Playwright als devDependency), curl.
# Kein Cloud-/Netz-Zugriff nötig — alles lokal (docker + uv + node).

set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$APP_ROOT"

DEFAULT_SPECS=(
  tests/regression/depot/cockpit-depot-view.spec.ts
  tests/regression/analyse/cockpit-kandidaten-view.spec.ts
  tests/regression/handel/cockpit-trades-view.spec.ts
  tests/regression/betrieb/cockpit-system-status-view.spec.ts
  tests/regression/konfiguration/cockpit-konfiguration-view.spec.ts
)
SPECS=("${@:-${DEFAULT_SPECS[@]}}")

err()  { printf '✗ %s\n' "$*" >&2; }
info() { printf 'ℹ %s\n' "$*"; }

free_port() {
  python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()'
}

DB_CONTAINER="ki-regression-db-$$"
DB_PORT="$(free_port)"
APP_PORT="$(free_port)"
# Ephemer, per PID zufällig — keine echte/wiederverwendete Zugangsdaten
# (Test-Fixture-Passwort, kein Secret-Muster).
DB_PASSWORD="regression-ephemeral-$$"

UVICORN_PID=""

cleanup() {
  local rc=$?
  info "Teardown: räume ephemeren Stack ab (Container ${DB_CONTAINER}, uvicorn PID ${UVICORN_PID:-none})…"
  if [[ -n "$UVICORN_PID" ]] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill "$UVICORN_PID" 2>/dev/null || true
    wait "$UVICORN_PID" 2>/dev/null || true
  fi
  docker rm -f "$DB_CONTAINER" >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup EXIT

info "Starte ephemeren Postgres-17-Container '${DB_CONTAINER}' auf Port ${DB_PORT}…"
docker run -d --name "$DB_CONTAINER" \
  -e POSTGRES_USER=app \
  -e POSTGRES_PASSWORD="$DB_PASSWORD" \
  -e POSTGRES_DB=app \
  -p "127.0.0.1:${DB_PORT}:5432" \
  postgres:17-alpine >/dev/null

info "Warte auf Postgres-Bereitschaft…"
for _ in $(seq 1 60); do
  if docker exec "$DB_CONTAINER" pg_isready -U app -d app >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! docker exec "$DB_CONTAINER" pg_isready -U app -d app >/dev/null 2>&1; then
  err "Postgres-Container nicht bereit (Timeout) — Abbruch."
  exit 1
fi

export DB_HOST="127.0.0.1"
export DB_PORT
export DB_NAME="app"
export DB_USER="app"
export DB_PASSWORD

info "Migriere Schema (alembic upgrade head)…"
uv run alembic upgrade head

info "Befülle Demo-Seed (SEED_DEMO=1, AC22)…"
SEED_DEMO=1 uv run python -m app.demo.seed

info "Starte App (uvicorn) auf Port ${APP_PORT}…"
uv run uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT" &
UVICORN_PID=$!

APP_URL="http://127.0.0.1:${APP_PORT}"
info "Warte auf App-Bereitschaft (${APP_URL}/health)…"
for _ in $(seq 1 60); do
  http_code="$(curl -sS --max-time 2 -o /dev/null -w '%{http_code}' "${APP_URL}/health" 2>/dev/null || true)"
  [[ "$http_code" == "200" ]] && break
  sleep 1
done
http_code="$(curl -sS --max-time 2 -o /dev/null -w '%{http_code}' "${APP_URL}/health" 2>/dev/null || true)"
if [[ "$http_code" != "200" ]]; then
  err "App nicht erreichbar (Timeout, letzter Status '${http_code}') — Abbruch."
  exit 1
fi

info "Playwright-Lauf gegen ${APP_URL}: ${SPECS[*]}"
REGRESSION_BASE_URL="$APP_URL" npx playwright test "${SPECS[@]}"
