"""Kandidaten-Endpunkte (`docs/specs/frontend-cockpit.md` AC4/AC5/AC7/AC10,
Story S-066; architecture.md §4 `app/api/kandidaten.py` — "reine Anzeige
(Kandidaten-Analysen) — verändert nie Trading-Logik").

`GET /api/kandidaten` (AC4) und `GET /api/kandidaten/{id}` (AC5) lesen
**ausschliesslich** über die geteilte Query-Schicht
(`app.api.queries.kandidaten`, AC1/AC10, P4/DRY) gegen das
Kandidaten-Analyse-Read-Modell (`app.domain.scoring.ports
.KandidatenRepository` → `app.adapters.repositories
.analysis_result_repository.SqlAlchemyKandidatenRepository`, AC7). Dieser
Endpunkt bucht/entscheidet/schreibt NICHTS (reine Anzeige-Schicht, AC2 gilt
sinngemäss — dieselbe Boundary wie `app.api.dashboard`, nur ausserhalb des
architektur-getesteten `app/api/queries/**`-Verzeichnisses, da hier die
DB-Session injiziert wird, analog `app.api.dashboard.get_position_repository`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.repositories.analysis_result_repository import SqlAlchemyKandidatenRepository
from app.api.queries.kandidaten import kandidat_detail, liste_kandidaten
from app.contracts.kandidaten import KandidatDetailResponse, KandidatUebersichtResponse
from app.db.session import get_session
from app.domain.scoring.ports import KandidatenRepository

router = APIRouter(prefix="/api/kandidaten", tags=["kandidaten"])


def get_kandidaten_repository(session: Session = Depends(get_session)) -> KandidatenRepository:
    """DI-Factory (fastapi/A02): reicht die Request-Session an den
    `SqlAlchemyKandidatenRepository`-Adapter durch."""
    return SqlAlchemyKandidatenRepository(session)


@router.get("", response_model=list[KandidatUebersichtResponse])
def kandidaten_liste(
    repository: KandidatenRepository = Depends(get_kandidaten_repository),
) -> list[KandidatUebersichtResponse]:
    """AC4: Liste bewerteter Kandidaten (Titel, Anlageklasse, Gesamtscore,
    abgeleitetes Signal, 5 Kategorie-Scores, `as_of`)."""
    return liste_kandidaten(repository)


@router.get("/{analysis_result_id}", response_model=KandidatDetailResponse)
def kandidat_detail_view(
    analysis_result_id: str,
    repository: KandidatenRepository = Depends(get_kandidaten_repository),
) -> KandidatDetailResponse:
    """AC5: Kategorie-Fakten inkl. Quellen-ID + Timestamp, Begründung,
    Sanity-Cap-Status. 404, falls `analysis_result_id` nicht existiert."""
    detail = kandidat_detail(repository, analysis_result_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Kandidat nicht gefunden")
    return detail
