## S-035 (PR #27, 2026-07-12)
- Gebaut: append-only `transaction`-Tabelle (Migration a1c4e7f2b930, revises 385adb3a764b) mit Postgres-BEFORE-UPDATE/DELETE-Trigger (BR-115); bewusst kein Update-/Delete-Port. TCA: `arrival_price`/`slippage_abs` je Fill, Formeln in `app/domain/portfolio/transaction_historie.py`, `historie_je_titel` filtert nach `mode` (BR-130).
- Für Folge-Storys: `transaction.position_id` ist NULLable (Multi-Lot-FIFO-Verkauf) — Historie über `titel_id` abfragen, nicht über `position_id`.
- `menge`/`preis`/`typ` sind NOT NULL — falls später `dividend`/`fee`/`fx_adjust`-Einträge gebucht werden, kollidiert das; dann `docs/data-model.md` um explizite NOT-NULL-Zeilen ergänzen (DBA-Hinweis S-035).
- TCA-Aggregation existiert nur als Domain-Formel — es gibt noch keinen API-Endpunkt; die Reporting-/Dashboard-Story muss ihn bauen und dabei das Slippage-Vorzeichen für Verkäufe klarstellen (Reviewer-Hinweis).
