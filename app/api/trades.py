"""Trade-Historie-JSON-Route (`docs/specs/frontend-cockpit.md` AC6/AC7,
Story S-067; architecture.md §13.2/§13.7 "eine Query-Funktion je View,
konsumiert von HTML- **und** JSON-Route").

`GET /api/trades` teilt sich die Query-Funktion
`app.api.queries.trades.hole_trade_historie` mit der HTML-Route
(`app.api.ui.trades_view`, deren Dateninhalt erst in Story S-073 verdrahtet
wird) — diese Route baut ihre Daten nicht selbst zusammen (AC1/AC10,
P4/DRY)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.api.queries.trades import hole_trade_historie
from app.contracts.depot import Modus
from app.contracts.trades import TradesResponse
from app.db.session import get_session
from app.domain.portfolio.ports import PositionRepository

router = APIRouter(prefix="/api", tags=["trades"])


def get_position_repository(session: Session = Depends(get_session)) -> PositionRepository:
    """DI-Factory (fastapi/A02) — eigene Kopie analog `app.api.dashboard
    .get_position_repository` (Hot-Spot-Konvention S-064: Route-Module
    bleiben voneinander unabhängig, kein geteilter Import aus einem
    parallel bearbeiteten Hot-Spot-File)."""
    return SqlAlchemyPositionRepository(session)


@router.get("/trades", response_model=TradesResponse)
def trades(
    mode: Modus = "echt",
    titel: str | None = None,
    von: datetime | None = None,
    bis: datetime | None = None,
    repository: PositionRepository = Depends(get_position_repository),
) -> TradesResponse:
    """AC6: depotweite Fill-/Transaktionshistorie, mode-isoliert (BR-130),
    optional gefiltert nach Titel (`titel`) und Zeitraum (`von`/`bis`)."""
    return hole_trade_historie(repository, mode=mode, titel_id=titel, von=von, bis=bis)
