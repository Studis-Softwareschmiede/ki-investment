"""Offene-Entscheide-JSON-Route (`docs/specs/frontend-cockpit.md`
AC29/AC31, Story S-080; architecture.md §13.2/§13.7 "eine Query-Funktion
je View, konsumiert von HTML- **und** JSON-Route").

`GET /api/entscheide/offen` teilt sich die Query-Funktion
`app.api.queries.entscheide.offene_entscheide_uebersicht` mit der
HTML-Route (`app.api.ui.entscheide_view`) — diese Route baut ihre Daten
nicht selbst zusammen (AC1/AC10, P4/DRY). `get_hybrid_entscheidung_
repository` ist bewusst hier (nicht in `app/api/ui.py`) verortet, analog
`app.api.trades.get_position_repository` — die UI-Route importiert diese
DI-Factory (kein eigener `sqlalchemy`-Import, AC2-Boundary,
`tests/architecture/test_ui_boundary.py`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.repositories.hybrid_entscheid_repository import (
    SqlAlchemyHybridEntscheidungRepository,
)
from app.api.queries.entscheide import offene_entscheide_uebersicht
from app.config import Settings, get_settings
from app.contracts.entscheide import OffeneEntscheideResponse
from app.db.session import get_session
from app.domain.hybrid_entscheidung.ports import HybridEntscheidungRepository

router = APIRouter(prefix="/api", tags=["entscheide"])


def get_hybrid_entscheidung_repository(
    session: Session = Depends(get_session),
) -> HybridEntscheidungRepository:
    """DI-Factory (fastapi/A02) — eigene Kopie analog `app.api.trades
    .get_position_repository` (Hot-Spot-Konvention S-064: Route-Module
    bleiben voneinander unabhängig)."""
    return SqlAlchemyHybridEntscheidungRepository(session)


@router.get("/entscheide/offen", response_model=OffeneEntscheideResponse)
def entscheide_offen(
    repository: HybridEntscheidungRepository = Depends(get_hybrid_entscheidung_repository),
    settings: Settings = Depends(get_settings),
) -> OffeneEntscheideResponse:
    """AC29: offene, bestätigungspflichtige Hybrid-Entscheide. AC31:
    feature-gated über `Settings.hybrid_bestaetigung_aktiv` (Default aus)
    — inaktiv liefert IMMER eine leere Liste."""
    return offene_entscheide_uebersicht(
        repository, feature_aktiv=settings.hybrid_bestaetigung_aktiv
    )
