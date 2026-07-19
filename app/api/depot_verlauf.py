"""Depot-Verlauf-Read-Endpunkt (Betriebs-Cockpit, `docs/specs/
frontend-cockpit.md` AC32/AC33, Story S-081; architecture.md §13.2/§13.7).

`GET /api/depot/verlauf?mode=&von=&bis=` — trägt ein `response_model`
(AC10, P2) und konsumiert dieselbe Query-Funktion
(`app.api.queries.depot_verlauf.hole_depot_verlauf`, AC1), die auch die
HTML-Route (`app.api.ui.depot_view`) speist.

Dieser Endpunkt bucht/entscheidet/schreibt NICHTS — reine Anzeige-Schicht
(AC2): die DI-Factory reicht die Request-Session an den
`SqlAlchemyPortfolioSnapshotRepository`-Adapter durch, die eigentliche
Datenzusammenstellung passiert ausschliesslich in der Query-Funktion. Der
Schreibpfad (Snapshot-Aufzeichnung) läuft ausschliesslich über den
periodischen Scheduler-Job (`app.scheduler.portfolio_snapshot_job`), NICHT
über diese Route."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.repositories.portfolio_snapshot_repository import (
    SqlAlchemyPortfolioSnapshotRepository,
)
from app.api.queries.depot_verlauf import hole_depot_verlauf
from app.contracts.depot import Modus
from app.contracts.depot_verlauf import DepotVerlaufResponse
from app.db.session import get_session
from app.domain.portfolio_verlauf.ports import PortfolioSnapshotRepository

router = APIRouter(prefix="/api", tags=["depot-verlauf"])


def get_portfolio_snapshot_repository(
    session: Session = Depends(get_session),
) -> PortfolioSnapshotRepository:
    """DI-Factory (fastapi/A02) — eigene Kopie analog `app.api.warteliste
    .get_warteliste_repository` (Hot-Spot-Konvention: Route-Module bleiben
    voneinander unabhängig)."""
    return SqlAlchemyPortfolioSnapshotRepository(session)


@router.get("/depot/verlauf", response_model=DepotVerlaufResponse)
def depot_verlauf(
    mode: Modus = "echt",
    von: datetime | None = None,
    bis: datetime | None = None,
    repository: PortfolioSnapshotRepository = Depends(get_portfolio_snapshot_repository),
) -> DepotVerlaufResponse:
    """AC32: Portfolio-Wert-Zeitreihe, mode-isoliert (→ BR-130), optional
    auf `[von, bis]` gefiltert."""
    return hole_depot_verlauf(repository, mode=mode, von=von, bis=bis)
