"""Demo-Kandidaten-Analysen (Story S-070, `docs/specs/frontend-cockpit.md`
AC22): `analysis_result`/`analysis_category_score`/`analysis_fact`
(S-066-Read-Modell).

`app.db.models.AnalysisResult` hat laut eigenem Docstring bislang KEINEN
Erzeuger-Pfad (kein Modul legt heute eine Zeile an — "diese Story liefert
nur Schema + Lese-Pfad", S-066) — diese Datei füllt daher direkt per ORM
(klar markierter Fixture-Insert, AC22): reine Analyse-Read-Modell-Zeilen,
kein Order-/Sizing-/Risiko-Bezug (die Score-Werte sind Demo-Fixture-Daten,
keine echte LLM-Analyse).

Idempotent: `analysis_result.id` ist deterministisch aus einem Demo-Slug
abgeleitet (`app.demo._namespace.demo_id`) — ein wiederholter Aufruf
überspringt einen bereits vorhandenen Kandidaten vollständig (inklusive
seiner Kategorie-Scores/Fakten, die nur zusammen mit dem `AnalysisResult`
neu angelegt werden)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AnalysisCategoryScore,
    AnalysisFact,
    AnalysisMethodVersion,
    AnalysisResult,
    CategoryWeightVersion,
    DataSource,
)
from app.demo._namespace import demo_id
from app.demo.instrumente import instrument_id

#: Bereits von der bestehenden `data_source`-Seed-Migration (`ea80c97626ee`)
#: angelegte, aktive Quelle — dieselbe wie in `app.demo.marktdaten`
#: (konsistente Demo-Fakten-Herkunft).
_DEMO_QUELLE_NAME = "SEC Form 4 Insider-Trades"

#: `analysis_category.code`-Werte (data-model.md §1) — identisch zur
#: `analysis_result_repository`-Konvention (`_CATEGORY_CODE_ZU_KATEGORIE_NAME`).
_KATEGORIE_CODES: tuple[str, ...] = (
    "fundamental",
    "technisch",
    "qualitativ",
    "makro",
    "risiko_quant",
)


@dataclass(frozen=True)
class _DemoFakt:
    kennzahl: str
    wert: Decimal
    zeitstempel: datetime


@dataclass(frozen=True)
class _DemoKandidat:
    slug: str
    titel_slug: str
    asset_class_id: int
    analyse_typ: str
    gesamtscore: Decimal
    signal_enum: str
    kategorie_scores: dict[str, Decimal]
    begruendung: str
    sanity_cap_applied: bool
    fakten: tuple[_DemoFakt, ...]
    as_of: datetime


#: Drei Kandidaten — zwei bereits gehaltene Titel (NESN/NOVN, "Analyse
#: bestehende Titel") + ein neuer Kandidat (ROG, "Analyse neue Titel"),
#: darunter GENAU EIN Sanity-Cap-Fall (ROG, → BR-008), wie von AC22
#: verlangt ("mind. 1 Sanity-Cap-Fall").
_DEMO_KANDIDATEN: tuple[_DemoKandidat, ...] = (
    _DemoKandidat(
        slug="demo-analyse-nesn",
        titel_slug="demo-instrument-nesn",
        asset_class_id=1,
        analyse_typ="bestehende_titel",
        gesamtscore=Decimal("6.80"),
        signal_enum="HALTEN",
        kategorie_scores={
            "fundamental": Decimal("7.0"),
            "technisch": Decimal("6.0"),
            "qualitativ": Decimal("7.5"),
            "makro": Decimal("6.0"),
            "risiko_quant": Decimal("7.5"),
        },
        begruendung=(
            "Stabile Cashflows, defensiver Sektor — keine Katalysatoren für "
            "eine Aufstockung, These weiterhin intakt."
        ),
        sanity_cap_applied=False,
        fakten=(
            _DemoFakt("kgv", Decimal("19.40"), datetime(2026, 6, 1, 7, 0, tzinfo=UTC)),
            _DemoFakt("dividendenrendite", Decimal("2.90"), datetime(2026, 6, 1, 7, 0, tzinfo=UTC)),
        ),
        as_of=datetime(2026, 6, 2, 7, 30, tzinfo=UTC),
    ),
    _DemoKandidat(
        slug="demo-analyse-novn",
        titel_slug="demo-instrument-novn",
        asset_class_id=1,
        analyse_typ="bestehende_titel",
        gesamtscore=Decimal("7.90"),
        signal_enum="KAUF",
        kategorie_scores={
            "fundamental": Decimal("8.0"),
            "technisch": Decimal("7.5"),
            "qualitativ": Decimal("8.5"),
            "makro": Decimal("7.0"),
            "risiko_quant": Decimal("8.0"),
        },
        begruendung="Pipeline-Meilenstein erreicht, Bewertung weiterhin moderat.",
        sanity_cap_applied=False,
        fakten=(
            _DemoFakt("kgv", Decimal("17.10"), datetime(2026, 6, 4, 7, 0, tzinfo=UTC)),
            _DemoFakt(
                "marktkapitalisierung",
                Decimal("205000000000"),
                datetime(2026, 6, 4, 7, 0, tzinfo=UTC),
            ),
        ),
        as_of=datetime(2026, 6, 5, 7, 45, tzinfo=UTC),
    ),
    _DemoKandidat(
        slug="demo-analyse-rog",
        titel_slug="demo-instrument-rog",
        asset_class_id=1,
        analyse_typ="neue_titel",
        gesamtscore=Decimal("8.50"),
        signal_enum="KAUF",
        kategorie_scores={
            "fundamental": Decimal("9.5"),
            "technisch": Decimal("8.0"),
            "qualitativ": Decimal("9.0"),
            "makro": Decimal("7.0"),
            "risiko_quant": Decimal("8.5"),
        },
        begruendung=(
            "Fundamentalscore lag vor Anwendung des Sanity-Caps bei 9.9 — "
            "auf die BR-008-Obergrenze gedeckelt, da eine Einzelquelle den "
            "Ausschlag gab (→ Sanity-Cap-Status im Detail sichtbar)."
        ),
        sanity_cap_applied=True,
        fakten=(
            _DemoFakt("kgv", Decimal("22.80"), datetime(2026, 6, 8, 7, 0, tzinfo=UTC)),
            _DemoFakt("kurs", Decimal("265.40"), datetime(2026, 6, 8, 7, 0, tzinfo=UTC)),
        ),
        as_of=datetime(2026, 6, 9, 7, 15, tzinfo=UTC),
    ),
)


def _analysis_result_id(slug: str) -> uuid.UUID:
    return demo_id(slug)


def seed_kandidaten(session: Session) -> None:
    """AC22: Kandidaten-Analysen inkl. 5 Kategorie-Scores + Signal,
    mindestens ein Sanity-Cap-Fall — je Kandidat ein Commit (begrenzt den
    Rollback-Radius wie in `app.demo.depot`/`app.demo.marktdaten`)."""
    quelle_id = session.execute(
        select(DataSource.id).where(DataSource.name == _DEMO_QUELLE_NAME)
    ).scalar_one()
    category_weight_version_id = session.execute(
        select(CategoryWeightVersion.id).where(CategoryWeightVersion.is_current.is_(True))
    ).scalar_one()
    analysis_method_version_id = session.execute(
        select(AnalysisMethodVersion.id).where(AnalysisMethodVersion.is_current.is_(True))
    ).scalar_one()

    for kandidat in _DEMO_KANDIDATEN:
        analysis_result_id = _analysis_result_id(kandidat.slug)
        if session.get(AnalysisResult, analysis_result_id) is not None:
            continue

        session.add(
            AnalysisResult(
                id=analysis_result_id,
                instrument_id=instrument_id(kandidat.titel_slug),
                analyse_typ=kandidat.analyse_typ,
                asset_class_id=kandidat.asset_class_id,
                category_weight_version_id=category_weight_version_id,
                analysis_method_version_id=analysis_method_version_id,
                gesamtscore=kandidat.gesamtscore,
                signal_enum=kandidat.signal_enum,
                exit_urgency="none",
                sanity_cap_applied=kandidat.sanity_cap_applied,
                schema_valid=True,
                llm_model="demo-seed",
                mode="simuliert",
                begruendung=kandidat.begruendung,
                created_at=kandidat.as_of,
            )
        )
        # Explizites Flush zwischen Parent (`analysis_result`) und den
        # abhängigen Zeilen (`analysis_category_score`/`analysis_fact`):
        # ohne gemappte `relationship()` sortiert SQLAlchemy die
        # INSERT-Reihenfolge innerhalb EINES Flushs nicht zuverlässig nach
        # der FK-Abhängigkeit (empirisch gegen Postgres 17 beobachtet —
        # `ForeignKeyViolation`, wenn Kategorie-Scores vor der
        # `analysis_result`-Zeile selbst gesendet werden).
        session.flush()
        for category_code in _KATEGORIE_CODES:
            session.add(
                AnalysisCategoryScore(
                    analysis_result_id=analysis_result_id,
                    category_code=category_code,
                    score=kandidat.kategorie_scores[category_code],
                    evidence_present=True,
                )
            )
        for fakt in kandidat.fakten:
            session.add(
                AnalysisFact(
                    id=demo_id(f"{kandidat.slug}-fakt-{fakt.kennzahl}"),
                    analysis_result_id=analysis_result_id,
                    kennzahl=fakt.kennzahl,
                    wert=fakt.wert,
                    source_id=quelle_id,
                    source_timestamp=fakt.zeitstempel,
                    cross_check_status="ok",
                )
            )
        session.commit()
