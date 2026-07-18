"""Query-Funktionen Kandidaten-Views (`docs/specs/frontend-cockpit.md`
AC1/AC4/AC5/AC7/AC10, Story S-066).

Konvention (§ `app/api/queries/__init__.py`): liest ausschliesslich über den
`app.domain.scoring.ports.KandidatenRepository`-Port (kein `sqlalchemy`-
Import, kein `session.add`/`commit`, `tests/architecture/test_ui_boundary
.py` erzwingt das statisch) und liefert Pydantic-View-DTOs aus
`app.contracts.kandidaten` — dieselbe Funktion speist künftig sowohl die
JSON-Route (`app.api.kandidaten`, AC10) als auch die HTML-View (S-072,
NICHT Teil dieser Story)."""

from __future__ import annotations

from app.contracts.kandidaten import (
    KandidatDetailResponse,
    KandidatFaktResponse,
    KandidatUebersichtResponse,
)
from app.domain.scoring.ports import KandidatenRepository


def liste_kandidaten(repository: KandidatenRepository) -> list[KandidatUebersichtResponse]:
    """AC4: Liste bewerteter Kandidaten (Titel, Anlageklasse, Gesamtscore,
    Signal, 5 Kategorie-Scores, `as_of`)."""
    return [
        KandidatUebersichtResponse(
            analysis_result_id=eintrag.analysis_result_id,
            titel_id=eintrag.titel_id,
            titel=eintrag.titel,
            name=eintrag.name,
            asset_class_id=eintrag.asset_class_id,
            gesamtscore=eintrag.gesamtscore,
            signal=eintrag.signal,
            kategorie_scores=eintrag.kategorie_scores,
            as_of=eintrag.as_of,
        )
        for eintrag in repository.liste_kandidaten()
    ]


def kandidat_detail(
    repository: KandidatenRepository, analysis_result_id: str
) -> KandidatDetailResponse | None:
    """AC5: Kategorie-Fakten inkl. Quellen-ID + Timestamp, Begründung,
    Sanity-Cap-Status. Liefert `None`, falls `analysis_result_id` nicht
    existiert (Aufrufer bildet daraus den HTTP-404-Fehlerpfad)."""
    detail = repository.kandidat_detail(analysis_result_id)
    if detail is None:
        return None
    return KandidatDetailResponse(
        analysis_result_id=detail.analysis_result_id,
        titel_id=detail.titel_id,
        titel=detail.titel,
        name=detail.name,
        asset_class_id=detail.asset_class_id,
        gesamtscore=detail.gesamtscore,
        signal=detail.signal,
        kategorie_scores=detail.kategorie_scores,
        sanity_cap_angewendet=detail.sanity_cap_angewendet,
        begruendung=detail.begruendung,
        fakten=[
            KandidatFaktResponse(
                kennzahl=fakt.kennzahl,
                wert=fakt.wert,
                quellen_id=fakt.quellen_id,
                zeitstempel=fakt.zeitstempel,
            )
            for fakt in detail.fakten
        ],
        as_of=detail.as_of,
    )
