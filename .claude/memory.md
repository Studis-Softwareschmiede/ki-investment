# Projekt-Memory — ki-investment

> Orientierung, nie Wahrheit: Bei Widerspruch gelten Board und Specs.
> Kuratiert von /flow am Ende jeder Session (max. 60 Zeilen).

## Aktueller Stand

Das Betriebs-Cockpit (F-017) ist komplett auf main gelandet und lokal
ausgerollt (http://localhost:8082): fünf server-gerenderte Kern-Views
(Depot, Kandidaten mit Spinnennetz, Trades, System-Status, Konfiguration)
plus Warteliste- und Hybrid-Entscheide-View, Control-Plane (Toggle/Modus/
Kill-Switch), Demo-Seed (SEED_DEMO) und Playwright-Regressionstests
(39 Specs × 3 Browser). 19 Stories in 5 parallelen Wellen abgearbeitet
(S-063–S-080), jede mit Review-/Test-Gate, DB-Stories mit DBA-Zweitreview.

## Letzte Arbeiten

- F-017 Betriebs-Cockpit (S-064–S-080, 18 Stories) + S-063 Migrations-
  Runner: als Feature-Batch über feature/F-017 gelandet, Merge df2d07c.
- Parallel-Kollisionen beim Landen aufgelöst: BR-140 doppelt vergeben
  (S-080 → BR-141 umnummeriert), alembic-Multi-Head (S-080-Migration an
  S-079 umgehängt), main.py/ui.py/tokens.css-Append-Konflikte per Union.
- Review-Funde mit Substanz: Secret-Leck im Docker-Build (fehlendes
  .dockerignore, S-063), lesbarer Titel statt UUID (3× dasselbe Muster:
  S-066/S-071/S-073), Lost-Update-Guard bei Statusübergängen (S-080).

## Offene Fäden

- S-081 ist DONE (2026-07-19): Depot-Verlauf-Chart mit vendored
  TradingView Lightweight Charts 5.2.0 (Owner-Freigabe), Snapshot-Tabelle
  + Scheduler-Job (BEWUSST noch nicht in main.py/Lifespan verdrahtet —
  analog S-020-Scheduler; Verdrahtung = offener Punkt).
- Bug-Fund aus S-077 (noch ohne Story): Trades-Filter liefert 422 bei
  leeren von/bis-Datumsfeldern (GET /ui/trades/tabelle) — leerer String
  sollte als "kein Filter" gelten; betrifft S-073/AC16.
- Produktions-Image kann alembic nicht selbst ausführen — Migrationen
  laufen beim lokalen Deploy per Host-alembic (S-063-Notiz); Preview-DB
  wurde nach dem Rollout manuell auf Head 827b9dcc737c migriert.
- JS-Helfer doppelt: konfiguration.js (fetch) vs. system-status.js
  (htmx-json-enc) lösen dasselbe Problem — Konsolidierung offen.
