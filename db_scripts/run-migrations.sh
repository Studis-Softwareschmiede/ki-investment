#!/usr/bin/env bash
# run-migrations.sh — Migrations-Runner für den Compose-Service `migrations`
# (docs/specs/projekt-setup.md AC1).
#
# db_migration_tool: alembic (siehe .claude/profile.md) — anders als die
# generische Skeleton-Konvention (db_scripts/<NNN>_*.sql + psql) sind die
# Migrationen hier Python-Revisionsdateien unter
# app/db/migrations/versions/. Dieser Container wird daher NICHT aus dem
# postgres:17-alpine-Image gebaut, sondern aus der `build`-Stage des
# Projekt-Dockerfile (siehe docker-compose.yml, Service `migrations`) —
# die bringt den vollen App-Quellcode (inkl. alembic.ini +
# app/db/migrations) sowie das .venv mit installiertem alembic mit.
#
# Startet erst, nachdem `db` per Compose-`depends_on: condition:
# service_healthy` als bereit gilt — kein zusätzlicher Wait-Loop nötig.
#
# Idempotent: `alembic upgrade head` ist bei einer bereits aktuellen DB ein
# No-Op (kanonischer Apply-Befehl, knowledge/migration/alembic.md
# Test-Approach + alembic/A04).
#
# Exit-Code: von `alembic upgrade head` durchgereicht (0 = ok, != 0 =
# Migration fehlgeschlagen).

set -euo pipefail

cd /app

echo "[run-migrations] Applying alembic migrations (DB_HOST=${DB_HOST:-db}, DB=${POSTGRES_DB:-app}) ..."
/app/.venv/bin/alembic upgrade head
echo "[run-migrations] Done — DB is at head."
