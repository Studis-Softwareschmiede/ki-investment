"""Tests für die `analysis_result`/`analysis_category_score`/
`analysis_fact`-Migration (Story S-066, Read-Modell-Gap,
`docs/specs/frontend-cockpit.md` AC4/AC5/AC7).

Covers (frontend-cockpit): AC4, AC5, AC7

Analog zur bestehenden Konvention (`tests/db/test_gate_result_migration.py`):
prüft nur die strukturellen DB-Constraints (Pflichtfelder, Wertebereiche,
CASCADE-Verhalten) gegen eine SQLite-In-Memory-DB. Der reale `alembic
upgrade head`-Lauf (inkl. aller FKs) gegen eine lokale Postgres-Instanz ist
Teil des Coder-Self-Tests (siehe Handoff)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    AnalysisCategory,
    AnalysisCategoryScore,
    AnalysisFact,
    AnalysisMethodVersion,
    AnalysisResult,
    AssetClass,
    CategoryWeightVersion,
    DataSource,
    Instrument,
)


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _engine_with_fk():
    """SQLite-Engine mit aktiviertem `PRAGMA foreign_keys=ON` — ohne dieses
    Pragma ignoriert SQLite Fremdschluessel-Constraints (inkl. ON DELETE
    CASCADE) stillschweigend."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def _stammdaten(session: Session) -> dict[str, object]:
    """Legt die für `analysis_result`-FKs nötigen Stammdaten an (Anlage-
    klasse, Instrument, Kategoriegewicht-/Methoden-Version, Datenquelle)."""
    asset_class = AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True)
    instrument = Instrument(
        id=uuid.uuid4(), symbol="AAPL", name="Apple", asset_class_id=1, currency="USD"
    )
    category_weight_version = CategoryWeightVersion(id=uuid.uuid4())
    analysis_method_version = AnalysisMethodVersion(id=uuid.uuid4())
    data_source = DataSource(id=uuid.uuid4(), name="SEC Form 4", frequenz_sekunden=3600)
    session.add_all(
        [asset_class, instrument, category_weight_version, analysis_method_version, data_source]
    )
    session.commit()
    return {
        "asset_class_id": asset_class.id,
        "instrument_id": instrument.id,
        "category_weight_version_id": category_weight_version.id,
        "analysis_method_version_id": analysis_method_version.id,
        "data_source_id": data_source.id,
    }


def _analysis_result(**overrides) -> AnalysisResult:
    defaults = dict(
        id=uuid.uuid4(),
        analyse_typ="neue_titel",
        gesamtscore=Decimal("8.5"),
        signal_enum="KAUF",
        sanity_cap_applied=False,
        schema_valid=True,
        mode="simuliert",
    )
    defaults.update(overrides)
    return AnalysisResult(**defaults)


def test_analysis_result_traegt_alle_ac4_ac5_felder() -> None:
    """@trace frontend-cockpit#AC4,AC5 — eine Zeile führt Instrument,
    Anlageklasse, Konfig-Versionen, Gesamtscore, Signal, Sanity-Cap-Status
    und Begründung."""
    engine = _engine()
    with Session(engine) as session:
        stammdaten = _stammdaten(session)
        ergebnis = _analysis_result(
            instrument_id=stammdaten["instrument_id"],
            asset_class_id=stammdaten["asset_class_id"],
            category_weight_version_id=stammdaten["category_weight_version_id"],
            analysis_method_version_id=stammdaten["analysis_method_version_id"],
            begruendung="Starke Fundamentaldaten.",
        )
        session.add(ergebnis)
        session.commit()

        eintrag = session.query(AnalysisResult).one()
        assert eintrag.instrument_id == stammdaten["instrument_id"]
        assert eintrag.asset_class_id == 1
        assert eintrag.gesamtscore == Decimal("8.5")
        assert eintrag.signal_enum == "KAUF"
        assert eintrag.sanity_cap_applied is False
        assert eintrag.begruendung == "Starke Fundamentaldaten."
        assert eintrag.created_at is not None


def test_analysis_result_gesamtscore_und_signal_sind_nullable_bei_uebersprung() -> None:
    """@trace frontend-cockpit#AC5 — No-Evidence-No-Trade-Übersprung
    (→ BR-108): `gesamtscore`/`signal_enum` bleiben `NULL`, kein
    Schätzwert (deckt E3)."""
    engine = _engine()
    with Session(engine) as session:
        stammdaten = _stammdaten(session)
        ergebnis = _analysis_result(
            instrument_id=stammdaten["instrument_id"],
            asset_class_id=stammdaten["asset_class_id"],
            category_weight_version_id=stammdaten["category_weight_version_id"],
            analysis_method_version_id=stammdaten["analysis_method_version_id"],
            gesamtscore=None,
            signal_enum=None,
        )
        session.add(ergebnis)
        session.commit()
        session.refresh(ergebnis)

        assert ergebnis.gesamtscore is None
        assert ergebnis.signal_enum is None


def test_analysis_result_rejects_unbekannten_signal_wert() -> None:
    """@trace frontend-cockpit#AC4 — `ck_analysis_result_signal_enum`
    erzwingt `signal_enum ∈ {KAUF, BEOBACHTEN, HALTEN, REDUZIEREN,
    VERKAUF}` DB-seitig (→ BR-105)."""
    engine = _engine()
    with Session(engine) as session:
        stammdaten = _stammdaten(session)
        session.add(
            _analysis_result(
                instrument_id=stammdaten["instrument_id"],
                asset_class_id=stammdaten["asset_class_id"],
                category_weight_version_id=stammdaten["category_weight_version_id"],
                analysis_method_version_id=stammdaten["analysis_method_version_id"],
                signal_enum="UNBEKANNT",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_analysis_result_rejects_gesamtscore_ausserhalb_range() -> None:
    """@trace frontend-cockpit#AC4 — `ck_analysis_result_gesamtscore_range`
    erzwingt `0 ≤ gesamtscore ≤ 10` (→ BR-104)."""
    engine = _engine()
    with Session(engine) as session:
        stammdaten = _stammdaten(session)
        session.add(
            _analysis_result(
                instrument_id=stammdaten["instrument_id"],
                asset_class_id=stammdaten["asset_class_id"],
                category_weight_version_id=stammdaten["category_weight_version_id"],
                analysis_method_version_id=stammdaten["analysis_method_version_id"],
                gesamtscore=Decimal("11"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_analysis_category_score_score_ist_nullable_bei_fehlender_evidenz() -> None:
    """@trace frontend-cockpit#AC5 — `score IS NULL` markiert eine Kategorie
    ohne verwertbare Evidenz (`evidence_present = false`, → BR-108), wird
    als fehlend ausgewiesen statt geschätzt (deckt E3)."""
    engine = _engine()
    with Session(engine) as session:
        stammdaten = _stammdaten(session)
        session.add(
            AnalysisCategory(code="fundamental", name="Fundamental"),
        )
        ergebnis = _analysis_result(
            instrument_id=stammdaten["instrument_id"],
            asset_class_id=stammdaten["asset_class_id"],
            category_weight_version_id=stammdaten["category_weight_version_id"],
            analysis_method_version_id=stammdaten["analysis_method_version_id"],
            gesamtscore=None,
            signal_enum=None,
        )
        session.add(ergebnis)
        session.commit()

        session.add(
            AnalysisCategoryScore(
                analysis_result_id=ergebnis.id,
                category_code="fundamental",
                score=None,
                evidence_present=False,
            )
        )
        session.commit()

        eintrag = session.query(AnalysisCategoryScore).one()
        assert eintrag.score is None
        assert eintrag.evidence_present is False


def test_analysis_fact_verlangt_source_id_und_source_timestamp() -> None:
    """@trace frontend-cockpit#AC5 — `source_id`/`source_timestamp` sind
    NOT NULL (→ BR-107/BR-002-Grounding-Pflicht)."""
    engine = _engine()
    with Session(engine) as session:
        stammdaten = _stammdaten(session)
        ergebnis = _analysis_result(
            instrument_id=stammdaten["instrument_id"],
            asset_class_id=stammdaten["asset_class_id"],
            category_weight_version_id=stammdaten["category_weight_version_id"],
            analysis_method_version_id=stammdaten["analysis_method_version_id"],
        )
        session.add(ergebnis)
        session.commit()

        fakt = AnalysisFact(
            id=uuid.uuid4(),
            analysis_result_id=ergebnis.id,
            kennzahl="kgv",
            wert=Decimal("15.5"),
            source_id=stammdaten["data_source_id"],
            source_timestamp=datetime(2026, 7, 1, tzinfo=UTC),
        )
        session.add(fakt)
        session.commit()

        eintrag = session.query(AnalysisFact).one()
        assert eintrag.source_id == stammdaten["data_source_id"]
        assert eintrag.source_timestamp is not None


def test_analysis_category_score_und_analysis_fact_werden_bei_delete_kaskadiert() -> None:
    """@trace frontend-cockpit#AC7 — `ON DELETE CASCADE` (data-model.md §3):
    Kind-Zeilen haben keine eigenständige Existenz ohne ihre
    `analysis_result`-Zeile."""
    engine = _engine_with_fk()
    with Session(engine) as session:
        stammdaten = _stammdaten(session)
        session.add(AnalysisCategory(code="fundamental", name="Fundamental"))
        ergebnis = _analysis_result(
            instrument_id=stammdaten["instrument_id"],
            asset_class_id=stammdaten["asset_class_id"],
            category_weight_version_id=stammdaten["category_weight_version_id"],
            analysis_method_version_id=stammdaten["analysis_method_version_id"],
        )
        session.add(ergebnis)
        session.commit()

        session.add(
            AnalysisCategoryScore(
                analysis_result_id=ergebnis.id,
                category_code="fundamental",
                score=8,
                evidence_present=True,
            )
        )
        session.add(
            AnalysisFact(
                id=uuid.uuid4(),
                analysis_result_id=ergebnis.id,
                kennzahl="kgv",
                wert=Decimal("15.5"),
                source_id=stammdaten["data_source_id"],
                source_timestamp=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )
        session.commit()

        session.delete(ergebnis)
        session.commit()

        assert session.execute(select(AnalysisCategoryScore)).scalars().all() == []
        assert session.execute(select(AnalysisFact)).scalars().all() == []
