"""View-Hilfsmodule der Kandidaten-View (Story S-072,
`docs/specs/frontend-cockpit.md` AC15). Reine, DB-freie Python-Helfer, die
`app/api/ui.py` und die Jinja2-Templates unter `app/web/templates/views/
kandidaten.html` + `app/web/templates/partials/kandidaten/**` konsumieren:

- `spinnennetz.py` — Geometrie des server-gerenderten Spinnennetz-SVG
  (design.md §8.1), reine Funktionen (kein Markup-Bau, kein DB-Zugriff).
- `anlageklassen.py` — Anlageklassen-Kürzel für den Klassen-Chip
  (design.md §2.4)."""

from __future__ import annotations
