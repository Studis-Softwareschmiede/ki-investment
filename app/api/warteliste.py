"""Warteliste-JSON-Route (`docs/specs/frontend-cockpit.md` AC26, Story
S-079; architecture.md §13.2/§13.7 "eine Query-Funktion je View,
konsumiert von HTML- **und** JSON-Route").

`GET /api/warteliste?mode=` teilt sich die Query-Funktion
`app.api.queries.warteliste.hole_warteliste` mit der HTML-Route
(`app.api.ui.warteliste_view`) — diese Route baut ihre Daten nicht selbst
zusammen (AC1/AC10, P4/DRY)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.repositories.warteliste_repository import SqlAlchemyWartelisteRepository
from app.api.queries.warteliste import hole_warteliste
from app.contracts.depot import Modus
from app.contracts.warteliste import WartelisteResponse
from app.db.session import get_session
from app.domain.warteliste.ports import WartelisteRepository

router = APIRouter(prefix="/api", tags=["warteliste"])


def get_warteliste_repository(session: Session = Depends(get_session)) -> WartelisteRepository:
    """DI-Factory (fastapi/A02) — eigene Kopie analog `app.api.trades
    .get_position_repository` (Hot-Spot-Konvention: Route-Module bleiben
    voneinander unabhängig, kein geteilter Import aus einem parallel
    bearbeiteten Hot-Spot-File)."""
    return SqlAlchemyWartelisteRepository(session)


@router.get("/warteliste", response_model=WartelisteResponse)
def warteliste(
    mode: Modus = "echt",
    repository: WartelisteRepository = Depends(get_warteliste_repository),
) -> WartelisteResponse:
    """AC26: vom Risikomanagement-Gate blockierte Kauf-Kandidaten,
    mode-isoliert (→ BR-130)."""
    return hole_warteliste(repository, mode=mode)
