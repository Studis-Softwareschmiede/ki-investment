# ki-investment

KI-gestützte vollautomatische Investment-App für Semi-Profis: scannt Nachrichten und Marktdaten, bewertet Titel über 11 Anlageklassen und 5 Analysekategorien (Score 0–10) und trifft Kauf-/Verkaufsentscheide — hybrid autonom oder mit Nutzer-Benachrichtigung.

Konzept-Quelle: Obsidian-Vault `300 Projekte/KI Investment` (Ingest via `/agent-flow:from-notes`). Durable Doku unter `docs/`.

## Stack

Python 3.13 + FastAPI (Build: uv) · Postgres (Migrationen: alembic) · Redis (Cache/Queue) · Docker/ghcr

## Entwicklung

```
uv sync
uv run pytest
uv run ruff check .
uv run uvicorn app.main:app --port 8080
```

## Datenbank (postgres)

- Knowledge Pack: `agent-flow/knowledge/sql.md` · Migrationen: `agent-flow/knowledge/migration/alembic.md`
- Migrations-Workflow (alembic): `docker compose up -d db && uv run alembic upgrade head && docker compose up -d app`
- Connection-Vars: `.env.db.example` → in `.env` übernehmen (nie committen)
- Backup/Restore-Vorlagen: `agent-flow/templates/_shared/db-postgres/scripts/` — bei Bedarf ins Projekt kopieren.

## Companion: redis

- Use-Case: Scheduler-Queue (Abruf-Frequenzen 30 s – täglich), Cache, Rate-Limits
- Connect-Env: `REDIS_HOST` / `REDIS_PORT` (`.env.redis.example`)
- Details: `agent-flow/templates/_shared/companion-redis/README.md`

## Secrets

- Modell: `.env` (lokal, nie committen) ↔ `.env.gpg` (verschlüsselt, committet); Vorlage `.env.example`
- Workflow: `bash scripts/decrypt-env.sh` → `.env` editieren → `bash scripts/encrypt-env.sh` → `.env.gpg` + `.env.example` committen
- Bindend: `agent-flow/docs/architecture/secrets-subsystem.md`
