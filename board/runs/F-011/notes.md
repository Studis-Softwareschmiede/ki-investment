
## Nachtwächter-Handoff für S-016 (2. Anlauf)
- Spec-Blocker ist gelöst: docs/specs/depot.md v2 definiert jetzt AC12 (Fill→Position-Orchestrierung, Pflichtfeld `modus` echt|simuliert, Mode-Isolation, `strategie_id` statt Name). S-016 implementiert zusätzlich AC12.
- Fertiger, geprüfter Vorarbeits-Stand liegt auf Branch `wip/S-016-gv-rechnung` (app/domain/portfolio/position_buchung.py + Tests) — übernehmen/anpassen statt neu schreiben, danach den wip-Branch löschen.
## S-035 (PR #27, 2026-07-12)
- Gebaut: append-only `transaction`-Tabelle (Migration a1c4e7f2b930, revises 385adb3a764b) mit Postgres-BEFORE-UPDATE/DELETE-Trigger (BR-115); bewusst kein Update-/Delete-Port. TCA: `arrival_price`/`slippage_abs` je Fill, Formeln in `app/domain/portfolio/transaction_historie.py`, `historie_je_titel` filtert nach `mode` (BR-130).
- Für Folge-Storys: `transaction.position_id` ist NULLable (Multi-Lot-FIFO-Verkauf) — Historie über `titel_id` abfragen, nicht über `position_id`.
- `menge`/`preis`/`typ` sind NOT NULL — falls später `dividend`/`fee`/`fx_adjust`-Einträge gebucht werden, kollidiert das; dann `docs/data-model.md` um explizite NOT-NULL-Zeilen ergänzen (DBA-Hinweis S-035).
- TCA-Aggregation existiert nur als Domain-Formel — es gibt noch keinen API-Endpunkt; die Reporting-/Dashboard-Story muss ihn bauen und dabei das Slippage-Vorzeichen für Verkäufe klarstellen (Reviewer-Hinweis).

## S-016 (PR #24, 2026-07-12)
- Gebaut: G/V-Rechnung (`app/domain/portfolio/position_booking.py` — unrealisiert/realisiert je Position + aggregiert, Decimal), Gebühren-Netting in Kostenbasis/Erlös, Einstand-Methode konfigurierbar (`EINSTAND_METHODE_DEFAULT`, Default gleitender Ø, FIFO-Option mit Multi-Lot-Entnahme).
- Fill-Idempotenz (ADR-011): `client_order_id` ist universelles Pflichtfeld + Dedup-Schlüssel (Tabelle `depot_fill_dedup`, Migration 385adb3a764b) — Folge-Storys dürfen denselben Fill nie doppelt verbuchen.
- Mode-Isolation (BR-113/BR-130): `offene_positionen`/`aktuelle_menge` filtern nach `mode`; Lost-Update-Schutz via `with_for_update()` + `UnzureichenderBestandFehler`.
- Hinweis: Story lag nach PR-#24-Merge mit verlorenem Board-Flip liegen; dieser Lauf hat nur re-verifiziert (271 Tests, Migrations-Kette, Security-Smoke grün) und Done nachgezogen — kein neuer Code.

## S-053 (PR #32, gelandet 2026-07-12, Done-Flip nachgezogen 2026-07-13)
- Gebaut: FX-Attribution (depot AC6) — `app/domain/portfolio/fx_attribution.py` (Split realisiert/unrealisiert, Summe = Gesamt-G/V CHF), Ø-Einstands-FX-Kurs-Fortschreibung mit Rundung an der Schreibgrenze (`position_booking.py`), Migration f065be116c72 (nullable FX-Spalten an `position`).
- Für Folge-Storys: `FillInput.fx_rate` ist Pflicht bei Fremdwährung (BR-129); bei `waehrung == CHF` sind alle vier FX-Attributionswerte `None` — Konsumenten müssen den None-Fall behandeln.
- FIFO: jeder Lot trägt seinen eigenen FX-Kurs; Multi-Lot-Verkäufe aggregieren den FX-Split über die Lots.
- Dieser Lauf: nur Re-Verifikation (364 Tests, ruff, Migrations-Kette Head f065be116c72, pip-audit, gitleaks — grün) + Done-Flip; kein neuer Code. Story lag nach Merge mit verlorenem Board-Flip (Drain-Reset 64b962e).
