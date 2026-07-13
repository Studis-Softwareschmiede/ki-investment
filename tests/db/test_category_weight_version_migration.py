"""Tests fuer die category_weight-Versionierungs-Migration (Story S-018).

Covers (anlageklassen-config): AC10

Deckt den Kategoriegewichte-Teil von AC10 ("Kategoriegewichte sind
versioniert: jede Änderung erzeugt eine neue Version, und zu jeder Analyse
ist nachvollziehbar, welche Konfigurationsversion ihr zugrunde lag") anhand
der Migration `app/db/migrations/versions/386f43ae972d_...py`, die die
S-004-Tag-Spalte `config_version` (reine Wert-Markierung ohne Historie)
durch das eigenständige Versionsregister `category_weight_version` ersetzt.

Strukturell (SQLite, ORM-Modell) geprüft: `config_version_id` ist Teil des
zusammengesetzten PK (append-only, zwei Versionen derselben
(Klasse, Kategorie) können nebeneinander existieren), sowie dass das Modell
keine alte `config_version`-Spalte mehr trägt. Der deferred
Σ=100-Constraint-Trigger (BR-101, jetzt versions-scope) ist — wie bereits
bei `2da446925bbc` — nur unter echtem Postgres ausführbar (deferred
CONSTRAINT TRIGGER, kein SQLite-Äquivalent) und wurde manuell gegen die
lokale Compose-Postgres-Instanz verifiziert (Coder-Self-Test, siehe
Handoff): (1) zwei Versionen derselben Klasse können gleichzeitig bestehen,
ohne dass der Trigger die Summen vermischt; (2) eine ungültige Summe
innerhalb EINER Version wird weiterhin abgelehnt.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AnalysisCategory, AssetClass, CategoryWeight, CategoryWeightVersion


def _seed_stammdaten(session: Session) -> None:
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    session.add(AnalysisCategory(code="fundamental", name="Fundamental", ist_risiko=False))
    session.commit()


def test_config_version_id_is_part_of_composite_primary_key() -> None:
    """@trace anlageklassen-config#AC10 — `config_version_id` ist Teil des
    PK von `category_weight` (append-only: zwei Versionen derselben
    Klasse/Kategorie-Kombination können nebeneinander existieren, ohne den
    PK zu verletzen)."""
    pk_columns = {col.name for col in inspect(CategoryWeight).primary_key}
    assert pk_columns == {"asset_class_id", "category_code", "config_version_id"}


def test_old_config_version_tag_column_is_gone() -> None:
    """@trace anlageklassen-config#AC10 — die S-004-Tag-Spalte `config_version`
    (ohne Historie, siehe data-model.md-Notiz) existiert nicht mehr auf dem
    Modell; sie wurde durch `config_version_id` (FK auf
    `category_weight_version`) ersetzt."""
    column_names = {col.name for col in CategoryWeight.__table__.columns}
    assert "config_version" not in column_names
    assert "config_version_id" in column_names


def test_two_versions_of_the_same_class_category_can_coexist() -> None:
    """@trace anlageklassen-config#AC10 — eine neue Version überschreibt
    NICHT die alte Zeile (append-only): beide Versionen derselben
    (Klasse, Kategorie)-Kombination bleiben lesbar."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_stammdaten(session)

        v1 = CategoryWeightVersion(note="Initial")
        session.add(v1)
        session.commit()
        session.add(
            CategoryWeight(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=v1.id,
                weight_pct=Decimal("35"),
            )
        )
        session.commit()

        v2 = CategoryWeightVersion(note="Anpassung Fundamental-Gewicht")
        session.add(v2)
        session.commit()
        session.add(
            CategoryWeight(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=v2.id,
                weight_pct=Decimal("40"),
            )
        )
        session.commit()

        zeilen = session.query(CategoryWeight).order_by(CategoryWeight.config_version_id).all()
        assert len(zeilen) == 2
        werte_je_version = {zeile.config_version_id: zeile.weight_pct for zeile in zeilen}
        assert werte_je_version[v1.id] == Decimal("35")
        assert werte_je_version[v2.id] == Decimal("40")


def test_duplicate_row_within_same_version_is_rejected() -> None:
    """@trace anlageklassen-config#AC10 — innerhalb DERSELBEN Version bleibt
    (asset_class_id, category_code) eindeutig (PK-Verletzung bei Duplikat)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_stammdaten(session)
        version = CategoryWeightVersion()
        session.add(version)
        session.commit()

        session.add(
            CategoryWeight(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=version.id,
                weight_pct=Decimal("35"),
            )
        )
        session.commit()

        session.add(
            CategoryWeight(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=version.id,
                weight_pct=Decimal("50"),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_category_weight_version_model_defaults_to_current() -> None:
    """@trace anlageklassen-config#AC10 — eine neu angelegte Version ist per
    Default `is_current` (App-seitiger Python-Default; DB-seitig zusätzlich
    per `server_default`, siehe Migration)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        version = CategoryWeightVersion()
        session.add(version)
        session.commit()
        assert version.is_current is True
