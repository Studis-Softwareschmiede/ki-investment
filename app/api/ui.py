"""Server-gerenderte Cockpit-Views (Jinja2 + HTMX, architecture.md §13.1,
§4 `app/api/ui.py` — "reine Anzeige/Control-Plane, ruft NUR queries/ +
Control-Plane-Funktionen").

Story S-064 (`docs/specs/frontend-cockpit.md` AC1/AC2/AC10/AC11/AC12/AC13)
liefert die **Shell** (persistente Statusleiste, Nav mit den fünf
Kern-Views, Hauptbereich) — je View steht hier bewusst nur ein Platzhalter
(`views/<view>.html`); der Dateninhalt (KPI-Tiles, Datentabellen,
Spinnennetz, Control-Elemente) folgt je View in eigenen Stories
(S-071/S-072/S-073/S-075/S-076, siehe `board/features/F-017-*.yaml`).

Story S-073 (AC16) befüllt hier die **Trade-Historie-View** (`/ui/trades`)
+ eine HTMX-Partial-Route (`/ui/trades/tabelle`) für den Filter-Formular-
Swap. Alle anderen Views bleiben unverändert Platzhalter (Hot-Spot-
Disziplin — vier parallele Stories teilen sich diese Datei, siehe
Story-Prompt).

**UI-Boundary (AC2):** diese Datei importiert bewusst NICHTS aus
`app.domain.sizing`, `app.domain.risikomanagement`, `app.domain.execution`,
`app.orchestration.*_pipeline`, `app.orchestration.execution_service` und
nichts direkt aus `sqlalchemy`/`app.db.session` — die Views bauen ihre
Daten NICHT selbst zusammen (AC1), sie werden ausschliesslich über
`app/api/queries/**`-Funktionen gespeist (`tests/architecture/
test_ui_boundary.py` erzwingt das statisch). Die DI-Factory für den
`PositionRepository` (die selbst `sqlalchemy`/`app.db.session` importiert)
lebt bewusst NICHT hier, sondern wird von der bereits bestehenden,
boundary-unkritischen JSON-Route `app.api.trades` importiert (diese Datei
ist kein Hot-Spot dieser Story-Runde) — Wiederverwendung derselben
DI-Factory wie `GET /api/trades` (P4/DRY), ohne den Boundary-Scan zu
verletzen."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request

from app.api.queries.trades import hole_trade_historie
from app.api.trades import get_position_repository
from app.contracts.depot import Modus
from app.domain.portfolio.ports import PositionRepository
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


def _trades_kontext(
    *,
    mode: Modus,
    titel: str | None,
    von: datetime | None,
    bis: datetime | None,
    repository: PositionRepository,
) -> dict[str, object]:
    """AC16: liefert den Trade-Historie-Kontext über dieselbe Query-Funktion
    wie `GET /api/trades` (AC1/AC7, P4/DRY) — die HTML-Route baut keine
    eigenen Daten zusammen."""
    daten = hole_trade_historie(repository, mode=mode, titel_id=titel, von=von, bis=bis)
    return {
        "trades": daten.trades,
        "mode": daten.mode,
        "filter": {"titel": titel or "", "von": von, "bis": bis},
    }


@router.get("/trades", name="ui_trades")
def trades_view(
    request: Request,
    mode: Modus = "echt",
    titel: str | None = None,
    von: datetime | None = None,
    bis: datetime | None = None,
    repository: PositionRepository = Depends(get_position_repository),
) -> object:
    """AC16: Trade-Historie-View — dichte Datentabelle + HTMX-Filter-Form
    (Modus/Titel/Zeitraum), dieselben Query-Parameter wie `GET /api/trades`
    (AC6/AC7)."""
    kontext = _trades_kontext(mode=mode, titel=titel, von=von, bis=bis, repository=repository)
    return templates.TemplateResponse(
        request,
        "views/trades.html",
        {"active_view": "trades", "kern_views": KERN_VIEWS, **kontext},
    )


@router.get("/trades/tabelle", name="ui_trades_tabelle")
def trades_tabelle_partial(
    request: Request,
    mode: Modus = "echt",
    titel: str | None = None,
    von: datetime | None = None,
    bis: datetime | None = None,
    repository: PositionRepository = Depends(get_position_repository),
) -> object:
    """AC16: HTMX-Partial-Swap-Ziel des Filter-Formulars — rendert
    ausschliesslich das Tabellen-Partial (kein volles Seiten-Layout) neu,
    über dieselbe Query-Funktion wie die volle View/JSON-Route."""
    kontext = _trades_kontext(mode=mode, titel=titel, von=von, bis=bis, repository=repository)
    return templates.TemplateResponse(request, "partials/trades-tabelle.html", kontext)


@router.get("/system-status", name="ui_system_status")
def system_status_view(request: Request) -> object:
    return _render(request, active_view="system-status")


@router.get("/konfiguration", name="ui_konfiguration")
def konfiguration_view(request: Request) -> object:
    return _render(request, active_view="konfiguration")
