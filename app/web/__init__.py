"""UI-Assets-Paket (architecture.md §4 `app/web/`, ADR-013).

Liegt bewusst UNTER `app/`, weil der Dockerfile nur `/app/app` ins
Runtime-Image kopiert (§13.4) — Templates/Statics außerhalb `app/` fehlen
zur Laufzeit (404).

`templates_setup` bündelt das `StaticFiles`-Mount + `Jinja2Templates`-Setup
(Story S-064, Hot-Spot-Konvention `app/main.py`): Folge-Stories importieren
von hier (`from app.web.templates_setup import templates`), statt eigene
`Jinja2Templates`-Instanzen anzulegen (sonst divergierende Template-Suchpfade)."""
