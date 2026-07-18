"""StaticFiles-Mount + Jinja2Templates-Setup (Story S-064,
`docs/specs/frontend-cockpit.md` AC11; architecture.md §13.4).

Ausgelagert aus `app/main.py` (Hot-Spot-Konvention, siehe dortiger
Kommentarblock): Folge-Stories, die neue Cockpit-Views/HTMX-Partials
bauen, importieren `templates` von hier statt eine eigene
`Jinja2Templates`-Instanz anzulegen — sonst divergierende Template-
Suchpfade/Auto-Escape-Einstellungen zwischen Modulen.

`configure_web(app)` mountet die vendorten Statics unter `/static`
(`app/web/static/**`, ADR-013 — kein CDN) und wird in `app/main.py` per
Ein-Zeilen-Aufruf verdrahtet."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_WEB_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = _WEB_ROOT / "templates"
STATIC_DIR = _WEB_ROOT / "static"

#: Geteilte Jinja2-Templates-Instanz (AC11) — von `app/api/ui.py` und
#: allen künftigen HTML-/HTMX-Partial-Routen zu importieren.
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def configure_web(app: FastAPI) -> None:
    """Mountet die vendorten Cockpit-Statics (`app/web/static/**`) unter
    `/static` (AC11/AC12, kein CDN, ADR-013). Einmal in `app/main.py`
    aufzurufen."""
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
