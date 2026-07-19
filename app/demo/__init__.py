"""Demo-/Seed-Modus (Story S-070, `docs/specs/frontend-cockpit.md` AC22).

Füllt alle fünf Cockpit-Views mit plausiblen, deterministischen
Beispieldaten, damit sie ohne Live-Betrieb Playwright-testbar sind
(S-077) — env-gated über `SEED_DEMO` (Default aus), idempotent
(Mehrfach-Ausführung = derselbe Zustand, kein Duplikat) und **ORDER-FREI**:
kein Modul unter `app/demo/**` importiert `app.domain.sizing`,
`app.domain.risikomanagement`, `app.domain.execution` oder
`app.orchestration.*_pipeline`/`app.orchestration.execution_service`
(§13.7-6) — Positionen/Transaktionen entstehen über den bestehenden,
selbst order-freien Buchungs-Kern
`app.domain.portfolio.position_booking.verbuche_fill` (direkte
DB-Schreibungen ins Depot-Read-Modell, kein Order-Anfrage-Aufruf), alle
übrigen Entitäten (Instrument, Bronze/Silver/Gold, Kandidaten-Analysen,
Gate-Ergebnis) über bereits bestehende, idempotente Store-Funktionen oder
klar markierte direkte ORM-Inserts (kein Schreibpfad existiert für diese
Tabellen bislang, siehe jeweiliger Modell-Docstring in `app.db.models`).

Alle geschriebenen Datensätze tragen `mode="simuliert"`, wo das Modell dieses
Feld kennt — Demo-Daten sind damit strukturell von echten Daten
unterscheidbar (AC22-Kern-Invariante). Einstiegspunkt: `app.demo.seed`
(`uv run python -m app.demo.seed`)."""
