"""Tests fuer die trading_platform-/platform_asset_class-Migration (Story
S-017).

Covers (ausfuehrung-paper): AC10

- AC10 (Referenzdaten `{ gebuehrenmodell, mindestgebuehr, typischer_spread }`
  je Plattform/Anlageklasse + Plattform-Zuordnung als Konfiguration) wird
  strukturell gegen die ORM-Modelle (`app.db.models.TradingPlatform`/
  `PlatformAssetClass`, 1:1 aus der Migration
  `f908ab5874fe_create_trading_platform_and_platform_.py`) geprueft:
  Spalten/Defaults, Unique-Constraint auf `trading_platform.name`, der
  Composite-PK auf `platform_asset_class` sowie der von data-model.md §8
  geforderte `(asset_class_id)`-Index.

Bewusst KEIN Seed-Test (anders als `test_data_source_migration.py`/
`test_category_weight_migration.py`): diese Migration seedt keine Zeilen
(siehe Migrations-Docstring — Konzept/Spec nennen keine belegten
Courtage-/Spread-/Mindestgebuehr-Zahlen fuer Interactive Brokers je
Anlageklasse).

Der reale `alembic upgrade head`-Lauf gegen eine lokale Compose-Postgres-
Instanz (beide Tabellen leer angelegt, `alembic check` meldet keinen
Model-Drift) wurde manuell verifiziert (Coder-Self-Test, siehe Handoff).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, PlatformAssetClass, TradingPlatform


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_trading_platform_persists_with_defaults() -> None:
    """@trace ausfuehrung-paper#AC10 — eine Plattform-Zeile mit nur `name`
    gesetzt uebernimmt die data-model.md-Defaults: `mindestgebuehr_chf=0`,
    `api_handelbar=True`, `paper_supported=True`."""
    engine = _engine()
    with Session(engine) as session:
        platform_id = uuid.uuid4()
        session.add(TradingPlatform(id=platform_id, name="Interactive Brokers"))
        session.commit()

        gespeichert = session.get(TradingPlatform, platform_id)
        assert gespeichert is not None
        assert gespeichert.mindestgebuehr_chf == Decimal("0")
        assert gespeichert.api_handelbar is True
        assert gespeichert.paper_supported is True
        assert gespeichert.gebuehrenmodell is None
        assert gespeichert.vault_ref is None


def test_trading_platform_name_is_unique() -> None:
    """@trace ausfuehrung-paper#AC10 — `trading_platform.name` ist UNIQUE
    (data-model.md §1)."""
    engine = _engine()
    with Session(engine) as session:
        session.add(TradingPlatform(id=uuid.uuid4(), name="Interactive Brokers"))
        session.commit()

        session.add(TradingPlatform(id=uuid.uuid4(), name="Interactive Brokers"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_platform_asset_class_composite_pk_persists_via_orm() -> None:
    """@trace ausfuehrung-paper#AC10 — die M:N-Zuordnung Plattform <->
    Anlageklasse (inkl. Kosten-Referenzdaten) ist ueber den Composite-PK
    `(platform_id, asset_class_id)` abfragbar."""
    engine = _engine()
    with Session(engine) as session:
        session.add(
            AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True)
        )
        platform_id = uuid.uuid4()
        session.add(TradingPlatform(id=platform_id, name="Interactive Brokers"))
        session.commit()

        session.add(
            PlatformAssetClass(
                platform_id=platform_id,
                asset_class_id=1,
                courtage_pct=Decimal("0.05"),
                typ_spread_pct=Decimal("0.02"),
                bevorzugt=True,
            )
        )
        session.commit()

        zuordnung = session.get(PlatformAssetClass, (platform_id, 1))
        assert zuordnung is not None
        assert zuordnung.courtage_pct == Decimal("0.05")
        assert zuordnung.bevorzugt is True


def test_platform_asset_class_bevorzugt_defaults_to_false() -> None:
    """@trace ausfuehrung-paper#AC10 — `bevorzugt` ist per Default `false`
    (data-model.md §1), muss also explizit gesetzt werden, um eine
    Plattform als Zuordnungs-Konfiguration auszuzeichnen."""
    engine = _engine()
    with Session(engine) as session:
        session.add(
            AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True)
        )
        platform_id = uuid.uuid4()
        session.add(TradingPlatform(id=platform_id, name="Interactive Brokers"))
        session.commit()

        session.add(PlatformAssetClass(platform_id=platform_id, asset_class_id=1))
        session.commit()

        zuordnung = session.get(PlatformAssetClass, (platform_id, 1))
        assert zuordnung is not None
        assert zuordnung.bevorzugt is False


def test_platform_asset_class_has_index_on_asset_class_id() -> None:
    """@trace ausfuehrung-paper#AC10 — data-model.md §8 verlangt fuer
    `platform_asset_class` einen `(asset_class_id)`-Index ("Plattform-Kosten
    je Klasse"); der Composite-PK (platform_id, asset_class_id) deckt einen
    reinen asset_class_id-Filter allein nicht ab (analog
    `DataSourceAssetClass`-Praezedenzfall)."""
    index_names_by_columns = {
        tuple(col.name for col in index.columns): index.name
        for index in PlatformAssetClass.__table__.indexes
    }
    assert ("asset_class_id",) in index_names_by_columns
    assert index_names_by_columns[("asset_class_id",)] == "ix_platform_asset_class_asset_class_id"
