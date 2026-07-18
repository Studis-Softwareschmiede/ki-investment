"""System-Status-Endpunkt (Betriebs-Cockpit, Story S-068, Spec
`docs/specs/frontend-cockpit.md` AC8/AC10; architecture.md §4
`app/api/system_status.py`).

`GET /api/system/status` liefert `response_model=SystemStatusResponse`
(P2) über die geteilte Query-Funktion `app.api.queries.system_status
.system_status_uebersicht` (AC1/AC10) — dieser Router baut selbst KEINE
Daten zusammen, er löst nur die Dependency-Injection des `Session`-
gebundenen `GateErgebnisRepository`-Adapters auf (analog `app.api
.dashboard.get_position_repository`).

Die (künftige) HTML-Route/Statusleisten-Verdrahtung derselben Query-
Funktion (AC10, P4/DRY) ist NICHT Teil dieser Story (S-075)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.repositories.gate_result_repository import SqlAlchemyGateErgebnisRepository
from app.api.queries.system_status import system_status_uebersicht
from app.contracts.system_status import SystemStatusResponse
from app.db.session import get_session
from app.domain.lernschleife.ports import GateErgebnisRepository

router = APIRouter(prefix="/api/system", tags=["system-status"])


def get_gate_ergebnis_repository(
    session: Session = Depends(get_session),
) -> GateErgebnisRepository:
    """DI-Factory (fastapi/A02): reicht die Request-Session an den
    bestehenden `SqlAlchemyGateErgebnisRepository`-Adapter durch."""
    return SqlAlchemyGateErgebnisRepository(session)


@router.get("/status", response_model=SystemStatusResponse)
def system_status(
    gate_ergebnis_repository: GateErgebnisRepository = Depends(get_gate_ergebnis_repository),
) -> SystemStatusResponse:
    """AC8: konsolidierter Betriebsstatus (Kill-Switch, Modus je
    Anlageklasse, Heartbeat, Drawdown, Halluzinations-KPI, Gate-Ampel)."""
    return system_status_uebersicht(gate_ergebnis_repository=gate_ergebnis_repository)
