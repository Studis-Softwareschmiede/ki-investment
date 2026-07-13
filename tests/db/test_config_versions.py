"""Tests fuer die Versionierungs-Mechanik `app/db/config_versions.py` (Story S-018).

Covers (anlageklassen-config): AC7, AC9, AC10

Deckt primär die BEHAVIOR-Seite von AC10 ("jede Änderung erzeugt eine neue
Version") — nicht nur das Schema (siehe
`tests/db/test_category_weight_version_migration.py` +
`tests/db/test_analysis_method_migration.py`), sondern die tatsächliche
Versions-Bump-Funktion, die eine Folge-Story (Config-Schreibpfad/Admin-API)
konsumieren würde. Beide Domänen (Kategoriegewichte, Methodentabellen)
versionieren unabhängig voneinander (kein gemeinsamer Versionszähler, siehe
Modul-Docstring `app/db/config_versions.py`). AC7 und AC9 tauchen nur dort
zusätzlich als Tag auf, wo derselbe Testfall inzident auch die
Gewichtungssumme (E1) bzw. die Ranking-DB-CHECK-Ablehnung (BR-102) im
Zusammenspiel mit der Versionierungs-Funktion mitprüft.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.category_weights import InvalidCategoryWeightsError
from app.db.config_versions import (
    erstelle_neue_analysis_method_version,
    erstelle_neue_category_weight_version,
)
from app.db.models import (
    AnalysisCategory,
    AnalysisMethod,
    AssetClass,
    CategoryWeight,
    CategoryWeightVersion,
)

VALID_WEIGHTS = {
    "fundamental": 35,
    "technisch": 15,
    "qualitativ": 20,
    "makro": 10,
    "risiko_quant": 20,
}


def _engine_mit_stammdaten() -> tuple:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    for code, name, ist_risiko in (
        ("fundamental", "Fundamental", False),
        ("technisch", "Technisch", False),
        ("qualitativ", "Qualitativ", False),
        ("makro", "Makro", False),
        ("risiko_quant", "Risiko & Quantitativ", True),
    ):
        session.add(AnalysisCategory(code=code, name=name, ist_risiko=ist_risiko))
    session.commit()
    return engine, session


def test_erstelle_neue_category_weight_version_marks_old_version_not_current() -> None:
    """@trace anlageklassen-config#AC10 — jede Änderung erzeugt eine neue,
    aktuell gültige Version; die vorherige Version bleibt (nicht mehr
    aktuell, aber unverändert) als Historie erhalten."""
    _, session = _engine_mit_stammdaten()

    v1 = erstelle_neue_category_weight_version(
        session, gewichte_je_klasse={1: VALID_WEIGHTS}, note="Initial"
    )
    session.commit()
    assert v1.is_current is True

    angepasste_gewichte = dict(VALID_WEIGHTS)
    angepasste_gewichte["fundamental"] = 40
    angepasste_gewichte["makro"] = 5
    v2 = erstelle_neue_category_weight_version(
        session, gewichte_je_klasse={1: angepasste_gewichte}, note="Fundamental hochgewichtet"
    )
    session.commit()

    session.refresh(v1)
    assert v1.is_current is False
    assert v2.is_current is True

    v1_zeilen = (
        session.execute(select(CategoryWeight).where(CategoryWeight.config_version_id == v1.id))
        .scalars()
        .all()
    )
    v2_zeilen = (
        session.execute(select(CategoryWeight).where(CategoryWeight.config_version_id == v2.id))
        .scalars()
        .all()
    )
    assert {z.weight_pct for z in v1_zeilen if z.category_code == "fundamental"} == {Decimal("35")}
    assert {z.weight_pct for z in v2_zeilen if z.category_code == "fundamental"} == {Decimal("40")}


def test_erstelle_neue_category_weight_version_rejects_invalid_sum_without_creating_version() -> (
    None
):
    """@trace anlageklassen-config#AC10,AC7 — eine ungültige Gewichtung (Σ ≠
    100, E1) wird zurückgewiesen, BEVOR eine neue Version angelegt wird
    (nichts wird wirksam)."""
    _, session = _engine_mit_stammdaten()
    ungueltig = dict(VALID_WEIGHTS)
    ungueltig["makro"] = ungueltig["makro"] + 5

    with pytest.raises(InvalidCategoryWeightsError):
        erstelle_neue_category_weight_version(session, gewichte_je_klasse={1: ungueltig})

    anzahl_versionen = session.execute(select(CategoryWeightVersion)).scalars().all()
    assert anzahl_versionen == []


def test_erstelle_neue_analysis_method_version_marks_old_version_not_current() -> None:
    """@trace anlageklassen-config#AC10 — analog Kategoriegewichte: eine neue
    Methodentabellen-Version markiert die Vorversion als nicht mehr
    aktuell, ohne deren Zeilen zu verändern (append-only)."""
    _, session = _engine_mit_stammdaten()

    v1 = erstelle_neue_analysis_method_version(
        session,
        methoden=[
            {
                "asset_class_id": 1,
                "category_code": "fundamental",
                "code": "F1",
                "kurzbezeichnung": "DCF",
                "ranking": 9,
            }
        ],
        note="Initial",
    )
    session.commit()
    assert v1.is_current is True

    v2 = erstelle_neue_analysis_method_version(
        session,
        methoden=[
            {
                "asset_class_id": 1,
                "category_code": "fundamental",
                "code": "F1",
                "kurzbezeichnung": "DCF",
                "ranking": 8,
            }
        ],
        note="Quartals-Review-Anpassung",
    )
    session.commit()

    session.refresh(v1)
    assert v1.is_current is False
    assert v2.is_current is True

    v1_zeile = session.execute(
        select(AnalysisMethod).where(AnalysisMethod.config_version_id == v1.id)
    ).scalar_one()
    v2_zeile = session.execute(
        select(AnalysisMethod).where(AnalysisMethod.config_version_id == v2.id)
    ).scalar_one()
    assert v1_zeile.ranking == 9
    assert v2_zeile.ranking == 8


def test_erstelle_neue_analysis_method_version_rejects_invalid_ranking_via_db_check() -> None:
    """@trace anlageklassen-config#AC10,AC9 — ein Ranking ausserhalb 1-10
    wird beim Flush über den DB-CHECK abgelehnt (BR-102: Enforcement-Layer
    ist ausschliesslich DB-CHECK, keine App-Vorab-Prüfung)."""
    from sqlalchemy.exc import IntegrityError

    _, session = _engine_mit_stammdaten()

    with pytest.raises(IntegrityError):
        erstelle_neue_analysis_method_version(
            session,
            methoden=[
                {
                    "asset_class_id": 1,
                    "category_code": "fundamental",
                    "code": "F1",
                    "kurzbezeichnung": "DCF",
                    "ranking": 11,
                }
            ],
        )
        session.commit()


def test_at_most_one_current_version_after_multiple_bumps() -> None:
    """@trace anlageklassen-config#AC10 — nach mehreren Versions-Bumps ist
    weiterhin genau eine Version je Domäne aktuell gültig (App-seitige
    Konsistenz; DB-seitig zusätzlich per partiellem UNIQUE-Index, BR-133,
    manuell gegen Postgres verifiziert, siehe Handoff)."""
    _, session = _engine_mit_stammdaten()

    for i in range(3):
        gewichte = dict(VALID_WEIGHTS)
        gewichte["fundamental"] = 35 - i
        gewichte["makro"] = 10 + i
        erstelle_neue_category_weight_version(session, gewichte_je_klasse={1: gewichte})
        session.commit()

    aktuelle = (
        session.execute(
            select(CategoryWeightVersion).where(CategoryWeightVersion.is_current.is_(True))
        )
        .scalars()
        .all()
    )
    assert len(aktuelle) == 1
