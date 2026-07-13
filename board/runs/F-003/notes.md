## S-020 (2026-07-13, PR #40)
- Scheduler-Subsystem neu: `app/scheduler/` (scheduler.py Tick/AC4+AC9, worker.py Backoff+DLQ/AC10, queue.py Redis-Queue + token_bucket.py/AC11), DTO `app/contracts/scheduler.py`.
- Neue Tabelle `ingest_dead_letter` (Modell + Migration 9c1e6a2f3b7d, Head der Kette) — Folge-Storys mit Migrationen: down_revision=9c1e6a2f3b7d.
- Fehlerklassifikation `app/scheduler/errors.py::ist_transienter_fehler` deckt httpx-Timeouts/TransportError explizit ab (Review-Fix It.2).
- S-050 (Recalculation-Window, letzte offene F-003-Story) kann auf Scheduler-Tick + Queue aufsetzen; Adapter-Verdrahtung (ingest_pipeline) ist bewusst NICHT Teil von S-020.
