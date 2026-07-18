"""SQLAlchemy-Implementierung des `KandidatenRepository`-Ports
(architecture.md §4 `app/adapters/repositories/`, Story S-066,
`docs/specs/frontend-cockpit.md` AC4/AC5/AC7).

Implementiert `app.domain.scoring.ports.KandidatenRepository` strukturell
(Protocol, keine explizite Vererbung nötig) gegen die
`analysis_result`/`analysis_category_score`/`analysis_fact`-Tabellen
(`app.db.models`, `docs/data-model.md` §3) — analog zu
`app.adapters.repositories.position_repository.SqlAlchemyPositionRepository`.
Zusätzlich ein Lookup gegen `instrument` (Review-Fund S-066 Iteration 1):
AC4/AC5 verlangen den menschenlesbaren Titel (`symbol`/`name`), nicht nur
die rohe `instrument_id`.

Rein lesend (AC7, kein `session.add`/`commit`): dieser Adapter bucht/
entscheidet/schreibt nichts."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.analyse_framework import KATEGORIE_NAMEN, KategorieScores
from app.db.models import AnalysisCategoryScore, AnalysisFact, AnalysisResult, Instrument
from app.domain.scoring.ports import KandidatDetail, KandidatFakt, KandidatUebersicht

#: `analysis_category.code`-Werte (data-model.md §1) → `KategorieName`
#: (`app.contracts.analyse_framework`). Bewusst als eigenständiges Mapping
#: statt Wiederverwendung derselben Wörter: die DB-Spalte heisst
#: `risiko_quant`, der Kategorie-Score-Vertrag `risiko` (P1/P3-Boundary:
#: `app/db/**`-Wertemengen und `app/contracts/**`-Literale dürfen
#: unabhängig benannt sein).
_CATEGORY_CODE_ZU_KATEGORIE_NAME: dict[str, str] = {
    "fundamental": "fundamental",
    "technisch": "technisch",
    "qualitativ": "qualitativ",
    "makro": "makro",
    "risiko_quant": "risiko",
}


def _als_uuid(analysis_result_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(analysis_result_id)
    except (ValueError, AttributeError, TypeError):
        return None


def _kategorie_scores_je_analyse(
    session: Session, analysis_result_ids: list[uuid.UUID]
) -> dict[uuid.UUID, KategorieScores]:
    """Lädt alle `analysis_category_score`-Zeilen der übergebenen
    Analyse-IDs in EINER Query und gruppiert sie zu je einer
    `KategorieScores`-Instanz (fehlende Kategorien bleiben `None`, identisch
    zur Score-Engine-Semantik, `app.domain.scoring.score_engine`)."""
    if not analysis_result_ids:
        return {}

    zeilen = (
        session.execute(
            select(AnalysisCategoryScore).where(
                AnalysisCategoryScore.analysis_result_id.in_(analysis_result_ids)
            )
        )
        .scalars()
        .all()
    )

    werte_je_analyse: dict[uuid.UUID, dict[str, float | None]] = {
        analysis_result_id: {} for analysis_result_id in analysis_result_ids
    }
    for zeile in zeilen:
        kategorie_name = _CATEGORY_CODE_ZU_KATEGORIE_NAME.get(zeile.category_code)
        if kategorie_name is None:
            continue  # pragma: no cover — unbekannter Kategorie-Code, DB-CHECK verhindert dies
        werte_je_analyse[zeile.analysis_result_id][kategorie_name] = (
            float(zeile.score) if zeile.score is not None else None
        )

    return {
        analysis_result_id: KategorieScores(
            **{
                kategorie: werte_je_analyse[analysis_result_id].get(kategorie)
                for kategorie in KATEGORIE_NAMEN
            }
        )
        for analysis_result_id in analysis_result_ids
    }


def _instrumente_je_id(
    session: Session, instrument_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Instrument]:
    """Lädt die `instrument`-Zeilen der übergebenen IDs in EINER Query
    (Review-Fund S-066 Iteration 1: AC4/AC5 verlangen den menschenlesbaren
    Titel — `symbol`/`name` —, nicht nur die rohe `instrument_id`)."""
    if not instrument_ids:
        return {}

    zeilen = (
        session.execute(select(Instrument).where(Instrument.id.in_(instrument_ids))).scalars().all()
    )
    return {zeile.id: zeile for zeile in zeilen}


def _fakten_je_analyse(session: Session, analysis_result_id: uuid.UUID) -> tuple[KandidatFakt, ...]:
    zeilen = (
        session.execute(
            select(AnalysisFact)
            .where(AnalysisFact.analysis_result_id == analysis_result_id)
            .order_by(AnalysisFact.source_timestamp.asc())
        )
        .scalars()
        .all()
    )
    return tuple(
        KandidatFakt(
            kennzahl=zeile.kennzahl,
            wert=zeile.wert,
            quellen_id=str(zeile.source_id),
            zeitstempel=zeile.source_timestamp,
        )
        for zeile in zeilen
    )


class SqlAlchemyKandidatenRepository:
    """Implementiert `app.domain.scoring.ports.KandidatenRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def liste_kandidaten(self) -> list[KandidatUebersicht]:
        """AC4: nur vollständig bewertete Analysen (`gesamtscore` UND
        `signal_enum` gesetzt — eine wegen fehlender Evidenz übersprungene
        Analyse hat laut `AnalysisResult`-Docstring beide `NULL` und
        erscheint hier nicht), neueste zuerst."""
        ergebnisse = (
            self._session.execute(
                select(AnalysisResult)
                .where(AnalysisResult.gesamtscore.is_not(None))
                .where(AnalysisResult.signal_enum.is_not(None))
                .order_by(AnalysisResult.created_at.desc())
            )
            .scalars()
            .all()
        )
        kategorie_scores_je_analyse = _kategorie_scores_je_analyse(
            self._session, [ergebnis.id for ergebnis in ergebnisse]
        )
        instrumente_je_id = _instrumente_je_id(
            self._session, [ergebnis.instrument_id for ergebnis in ergebnisse]
        )
        return [
            KandidatUebersicht(
                analysis_result_id=str(ergebnis.id),
                titel_id=str(ergebnis.instrument_id),
                titel=instrumente_je_id[ergebnis.instrument_id].symbol,
                name=instrumente_je_id[ergebnis.instrument_id].name,
                asset_class_id=ergebnis.asset_class_id,
                gesamtscore=float(ergebnis.gesamtscore),
                signal=ergebnis.signal_enum,
                kategorie_scores=kategorie_scores_je_analyse[ergebnis.id],
                as_of=ergebnis.created_at,
            )
            for ergebnis in ergebnisse
        ]

    def kandidat_detail(self, analysis_result_id: str) -> KandidatDetail | None:
        """AC5: liefert `None` für eine ungültige/unbekannte ID (deckt den
        HTTP-404-Fehlerpfad der Route) statt einer Exception."""
        analysis_result_uuid = _als_uuid(analysis_result_id)
        if analysis_result_uuid is None:
            return None

        ergebnis = self._session.get(AnalysisResult, analysis_result_uuid)
        if ergebnis is None:
            return None

        kategorie_scores = _kategorie_scores_je_analyse(self._session, [ergebnis.id])[ergebnis.id]
        fakten = _fakten_je_analyse(self._session, ergebnis.id)
        gesamtscore: Decimal | None = ergebnis.gesamtscore
        instrument = self._session.get(Instrument, ergebnis.instrument_id)

        return KandidatDetail(
            analysis_result_id=str(ergebnis.id),
            titel_id=str(ergebnis.instrument_id),
            titel=instrument.symbol,
            name=instrument.name,
            asset_class_id=ergebnis.asset_class_id,
            gesamtscore=float(gesamtscore) if gesamtscore is not None else None,
            signal=ergebnis.signal_enum,
            kategorie_scores=kategorie_scores,
            sanity_cap_angewendet=ergebnis.sanity_cap_applied,
            begruendung=ergebnis.begruendung,
            fakten=fakten,
            as_of=ergebnis.created_at,
        )
