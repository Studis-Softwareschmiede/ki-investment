"""Server-gerenderte Cockpit-Views (Jinja2 + HTMX, architecture.md §13.1,
§4 `app/api/ui.py` — "reine Anzeige/Control-Plane, ruft NUR queries/ +
Control-Plane-Funktionen").

Story S-064 (`docs/specs/frontend-cockpit.md` AC1/AC2/AC10/AC11/AC12/AC13)
liefert die **Shell** (persistente Statusleiste, Nav mit den fünf
Kern-Views, Hauptbereich) — je View steht hier bewusst nur ein Platzhalter
(`views/<view>.html`); der Dateninhalt (KPI-Tiles, Datentabellen,
Spinnennetz, Control-Elemente) folgt je View in eigenen Stories
(S-071/S-072/S-073/S-075/S-076, siehe `board/features/F-017-*.yaml`).

**UI-Boundary (AC2):** diese Datei importiert bewusst NICHTS aus
`app.domain.sizing`, `app.domain.risikomanagement`, `app.domain.execution`,
`app.orchestration.*_pipeline`, `app.orchestration.execution_service` und
nichts aus `sqlalchemy`/`app.db.session` — die Views bauen ihre Daten NICHT
selbst zusammen (AC1), sie werden künftig ausschliesslich über
`app/api/queries/**`-Funktionen gespeist (`tests/architecture/
test_ui_boundary.py` erzwingt das statisch)."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.web.templates_setup import templates

router = APIRouter(prefix="/ui", tags=["ui"])

#: Die fünf Kern-Views (design.md §5 Nav-Blaupause, architecture.md §13.3),
#: in Anzeige-Reihenfolge. `slug` = URL-Segment + Template-Basisname,
#: `route_name` = FastAPI-Routenname (für `url_for` in der Nav-Partial),
#: `label` = Nav-/`<h1>`-Text.
KERN_VIEWS: tuple[dict[str, str], ...] = (
    {"slug": "depot", "route_name": "ui_depot", "label": "Depot"},
    {"slug": "kandidaten", "route_name": "ui_kandidaten", "label": "Kandidaten"},
    {"slug": "trades", "route_name": "ui_trades", "label": "Trades"},
    {"slug": "system-status", "route_name": "ui_system_status", "label": "System-Status"},
    {"slug": "konfiguration", "route_name": "ui_konfiguration", "label": "Konfiguration"},
)


def _render(request: Request, *, active_view: str) -> object:
    return templates.TemplateResponse(
        request,
        f"views/{active_view}.html",
        {"active_view": active_view, "kern_views": KERN_VIEWS},
    )


@router.get("/depot", name="ui_depot")
def depot_view(request: Request) -> object:
    return _render(request, active_view="depot")


@router.get("/kandidaten", name="ui_kandidaten")
def kandidaten_view(request: Request) -> object:
    return _render(request, active_view="kandidaten")


@router.get("/trades", name="ui_trades")
def trades_view(request: Request) -> object:
    return _render(request, active_view="trades")


@router.get("/system-status", name="ui_system_status")
def system_status_view(request: Request) -> object:
    return _render(request, active_view="system-status")


@router.get("/konfiguration", name="ui_konfiguration")
def konfiguration_view(request: Request) -> object:
    return _render(request, active_view="konfiguration")
