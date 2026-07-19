"""Depot-Read-Endpunkt (Betriebs-Cockpit, `docs/specs/frontend-cockpit.md`
AC1/AC3/AC10, Story S-065; architecture.md §13.2/§13.7).

`GET /api/depot` generalisiert das bestehende `GET /dashboard/depot`
(`app.api.dashboard`, S-054, das unverändert bestehen bleibt — Verträge-
Tabelle `frontend-cockpit.md`: "JSON-Pfade additiv unter `/api/**`"): trägt
ein `response_model` (AC10, P2) und konsumiert dieselbe Query-Funktion
(`app.api.queries.depot.hole_depot_uebersicht`, AC1), die künftig (S-071,
nicht Teil dieser Story) auch die HTML-Route (`app.api.ui`) speist.

Dieser Endpunkt bucht/entscheidet/schreibt NICHTS — reine Anzeige-Schicht
(AC2): die DI-Factories reichen die Request-Session an den bestehenden
`SqlAlchemyPositionRepository`-Adapter durch (analog `app.api.dashboard`),
die eigentliche Datenzusammenstellung passiert ausschliesslich in der
Query-Funktion."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.marketdata.live_price import NoOpLivePriceProvider
from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.api.queries.depot import hole_depot_uebersicht
from app.contracts.depot import Modus
from app.contracts.depot_uebersicht import DepotUebersichtResponse
from app.db.session import get_session
from app.domain.portfolio.ports import LivePriceProvider, PositionRepository

router = APIRouter(prefix="/api", tags=["depot"])


def get_position_repository(session: Session = Depends(get_session)) -> PositionRepository:
    """DI-Factory (fastapi/A02): reicht die Request-Session an den
    bestehenden `SqlAlchemyPositionRepository`-Adapter durch (analog
    `app.api.dashboard.get_position_repository`)."""
    return SqlAlchemyPositionRepository(session)


def get_live_price_provider() -> LivePriceProvider:
    """DI-Factory (fastapi/A02): aktuell die einzige `LivePriceProvider`-
    Implementierung (siehe `app.adapters.marketdata.live_price`-
    Moduldocstring)."""
    return NoOpLivePriceProvider()


@router.get("/depot", response_model=DepotUebersichtResponse)
def depot_uebersicht(
    mode: Modus = "echt",
    repository: PositionRepository = Depends(get_position_repository),
    live_price: LivePriceProvider = Depends(get_live_price_provider),
) -> DepotUebersichtResponse:
    """AC3: Bestand je Titel (Menge, Ø-Einstand, Live-Kurs, unrealisierter
    G/V), Portfolio-Aggregate (Branchen-/Klassen-Gewichtung, Cash-Quote)
    und depotweiter realisierter G/V, mode-isoliert (BR-130, Default
    `echt`, analog `app.api.dashboard`)."""
    return hole_depot_uebersicht(mode=mode, repository=repository, live_price=live_price)
