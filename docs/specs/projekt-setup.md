---
id: projekt-setup
title: Projekt-Setup-Restpunkte (Migrationen, Knowledge-Pack)
status: active
version: 1
spec_format: use-case-2.0
area: konfiguration
---

# Spec: Projekt-Setup-Restpunkte  (`projekt-setup`)

> Konzept-Herkunft: (← C-020)

## Zweck
Vom Bootstrap offen gelassene Setup-Arbeiten, damit der Datenbank-Migrationspfad (alembic) und die zugehörige Fabrik-Wissensbasis stehen, bevor die ersten Schema-Stories gebaut werden.

## Acceptance-Kriterien

- **AC1** — Alembic ist im Projekt initialisiert: `alembic.ini` + `migrations/`-Struktur vorhanden, `env.py` liest die DB-Verbindung aus den Umgebungsvariablen der `.env.db`-Konvention (keine Klartext-Credentials im Repo); eine erste Migration existiert und `alembic upgrade head` läuft gegen die Compose-Postgres-Instanz fehlerfrei durch.
- **AC2** — Der Fabrik-Knowledge-Pack `knowledge/migration/alembic.md` existiert (via `/train --bootstrap migration/alembic` oder manuell aus Primärquellen) und beschreibt die alembic-Konventionen, die der coder für dieses Projekt nutzt.

## Verträge
Alembic-Konfiguration konsumiert `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` (bzw. `POSTGRES_*` gemäss `.env.db.example`).

## Edge-Cases & Fehlerverhalten
Fehlende Env-Variablen → klarer Startfehler mit Nennung der fehlenden Variable, kein Fallback auf Defaults mit echten Credentials.

## NFRs
Keine Secrets in Migrations- oder Konfigurationsdateien.

## Nicht-Ziele
Fachliche Schema-Inhalte (kommen aus `docs/data-model.md` über die Feature-Stories).

## Abhängigkeiten
`docs/data-model.md` (Migrations-Reihenfolge), Secrets-Subsystem.
