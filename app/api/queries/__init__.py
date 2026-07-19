"""Query-Schicht (Read-Only) für das Betriebs-Cockpit.

`docs/specs/frontend-cockpit.md` AC1/AC2/AC10; architecture.md §13.2/§13.7,
Prüfkriterium 1/2/4.

**Konvention (bindend für jede Funktion in diesem Paket, Fundament-Story
S-064 — konkrete Query-Funktionen folgen je View in S-065/S-066/S-067/
S-068/S-069):**

1. **Eine Query-Funktion je Cockpit-View** (AC1): liest ausschliesslich
   über vorhandene Repository-Lese-Ports (z. B.
   `app.domain.portfolio.ports.PositionRepository`) und
   `app.domain.portfolio.ports.LivePriceProvider` (P5) — nie eine eigene
   DB-Session/Preisanbindung. Liefert ein Pydantic-View-DTO aus
   `app.contracts.**` (P2).
2. **Read-only** (AC2, Prüfkriterium 2): kein `session.add`/`session.commit`
   — dieses Paket bucht/entscheidet/schreibt nichts.
3. **Geteilt von HTML- und JSON-Route** (AC10, P4/DRY): dieselbe Funktion
   liefert sowohl den Kontext für `app/api/ui.py` (Jinja2-Rendering) als
   auch den `response_model`-Body der JSON-Route unter `/api/**` — keine
   Route baut ihre Daten selbst zusammen.
4. **UI-/Query-Boundary** (AC2, Prüfkriterium 1, `grep`-/Import-Linter-
   prüfbar via `tests/architecture/test_ui_boundary.py`): kein Modul
   dieses Pakets importiert aus `app.domain.sizing`,
   `app.domain.risikomanagement`, `app.domain.execution`,
   `app.orchestration.*_pipeline` oder `app.orchestration.execution_service`.

Dieses `__init__.py` bleibt bewusst frei von Query-Funktionen — das
Fundament (Story S-064) legt Paket + Konvention + Boundary-Test an; die
konkreten Views hängen die Funktionen in Folge-Stories hier ein."""
