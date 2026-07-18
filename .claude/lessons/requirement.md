# requirement — projekt-lokale Prozess-Lessons (newest-first)

## 2026-07-18 — Story-IDs werden in Anlage-Reihenfolge vergeben, nicht nach Wunsch-Label
Beim Batch-Anlegen mehrerer Stories über `board story add` weist das CLI die IDs **strikt sequenziell in Aufruf-Reihenfolge** zu (S-064, S-065, …) — unabhängig davon, welche Story man gedanklich mit welcher Nummer verknüpft hat. Wer `--depends` mit **geratenen, noch nicht angelegten** IDs füttert, verdrahtet den DAG falsch (Selbst-Referenz, Verweis auf die falsche Story) und muss hinterher korrigieren.
- **Regel:** Forward-Dependencies nie raten. Entweder (a) Stories so ordnen, dass jede Story nur auf **bereits angelegte** (kleinere) IDs zeigt und `--depends` erst mit den **tatsächlich zurückgegebenen** IDs setzen, oder (b) alle Stories ohne kritische Forward-Depends anlegen und die Dependencies danach per `board set <id> depends "…"` nachziehen.
- **Zusatz:** `board set <id> depends "A,B,C"` schreibt den Wert als **Skalar-String**, nicht als YAML-Liste (anders als `story add`). Danach die betroffenen Story-YAMLs auf eine echte YAML-Liste normalisieren, sonst droht Schema-/Lint-Drift.
