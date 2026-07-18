"""Tests für die `order`/`trade_fill`-Migration (Story S-048, Order-
Lifecycle-Zustände & TCA-Fills).

Covers (ausfuehrung-paper): AC6, AC7, AC8

Analog zur bestehenden Konvention (`tests/db/test_transaction_migration.py`,
`tests/db/test_depot_fill_dedup_migration.py`): prüft nur die strukturellen
DB-Constraints (CHECK `richtung`/`order_typ`/`status`/`mode`, `menge`/
`fill_menge` > 0, `position_id`/`platform_id` NULLable) gegen eine
SQLite-In-Memory-DB. Der reale `alembic upgrade head`-Lauf gegen eine
lokale Compose-Postgres-Instanz (inkl. `alembic check` ohne Model-Drift)
ist Teil des Coder-Self-Tests (siehe Handoff). Die funktionalen Schreib-
Tests (`speichere_ausfuehrung`) liegen in
`tests/adapters/repositories/test_order_repository.py`.

- AC6: `order_typ` deckt den vollen `ExecutionOrderTyp`-Wertebereich
  (Market, Limit, Stop, Stop-Limit, Trailing, TWAP) — S-048-präzisiert,
  siehe data-model.md §4 `order`-Präzisierungsnote.
- AC7: `trade_fill.slippage_abs` ist NOT NULL (BR-114) — jeder Fill-Eintrag
  trägt seine Slippage.
- AC8: `order.status` deckt den vollen Lifecycle-Wertebereich (inkl.
  `teilfill`/`rejected`/`timeout`, E1-E3).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, Instrument, Order, TradeFill


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed_instrument(session: Session) -> uuid.UUID:
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    instrument = Instrument(
        id=uuid.uuid4(), symbol="ACME", name="Acme Corp", asset_class_id=1, currency="CHF"
    )
    session.add(instrument)
    session.commit()
    return instrument.id


def _valid_order(instrument_id: uuid.UUID, **overrides: object) -> Order:
    kwargs = {
        "id": uuid.uuid4(),
        "position_id": None,
        "instrument_id": instrument_id,
        "platform_id": None,
        "richtung": "buy",
        "order_typ": "limit",
        "menge": Decimal("10"),
        "limit_preis": Decimal("150"),
        "arrival_price": Decimal("149"),
        "exit_urgency": None,
        "tranche_index": None,
        "tranche_total": None,
        "status": "filled",
        "mode": "simuliert",
    }
    kwargs.update(overrides)
    return Order(**kwargs)


def test_order_traegt_alle_ac6_ac7_ac8_felder() -> None:
    """@trace ausfuehrung-paper#AC6,AC7,AC8 — eine Order-Zeile trägt Titel,
    Richtung, Order-Typ, Menge, Arrival-Price, Status, Modus."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id))
        session.commit()

        zeile = session.query(Order).one()
        assert zeile.instrument_id == instrument_id
        assert zeile.richtung == "buy"
        assert zeile.order_typ == "limit"
        assert zeile.menge == Decimal("10")
        assert zeile.arrival_price == Decimal("149")
        assert zeile.status == "filled"
        assert zeile.mode == "simuliert"
        assert zeile.created_at is not None


def test_order_position_id_und_platform_id_sind_nullable() -> None:
    """@trace ausfuehrung-paper#AC7,AC8 — `position_id` (Positions-
    Zuordnung erst nach Depot-Meldung, Nicht-Ziel dieser Story) und
    `platform_id` bleiben NULLable."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id, position_id=None, platform_id=None))
        session.commit()

        zeile = session.query(Order).one()
        assert zeile.position_id is None
        assert zeile.platform_id is None


@pytest.mark.parametrize("order_typ", ["market", "limit", "stop", "stop_limit", "trailing", "twap"])
def test_order_akzeptiert_alle_ac6_order_typen(order_typ: str) -> None:
    """@trace ausfuehrung-paper#AC6 — S-048-präzisiert: `order_typ` deckt
    den vollen `ExecutionOrderTyp`-Wertebereich (nicht mehr nur die
    schmalere `sizing.OrderTyp`-Menge)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id, order_typ=order_typ))
        session.commit()

        assert session.query(Order).one().order_typ == order_typ


def test_order_rejects_invalid_order_typ() -> None:
    """@trace ausfuehrung-paper#AC6 — `stop_market` (die alte, verkaufs-
    seitige `sizing.OrderTyp`-Bezeichnung) ist auf `order`-Ebene KEIN
    gültiger Wert mehr (mappt vor dem Order-Ausführungs-Kern auf `stop`,
    siehe data-model.md-Präzisierungsnote)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id, order_typ="stop_market"))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "status", ["offen", "teilfill", "filled", "rejected", "timeout", "cancelled"]
)
def test_order_akzeptiert_alle_ac8_status_werte(status: str) -> None:
    """@trace ausfuehrung-paper#AC8 — der volle Order-Lifecycle-
    Wertebereich (E1-E3 plus die noch nicht produzierten Zustände
    `offen`/`cancelled`, siehe `app.db.models.ORDER_STATUS_VALUES`-
    Docstring) ist auf Schema-Ebene gültig."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id, status=status))
        session.commit()

        assert session.query(Order).one().status == status


def test_order_rejects_invalid_status() -> None:
    """@trace ausfuehrung-paper#AC8 — ein Fremdwert ausserhalb des
    CHECK-Vokabulars wird abgelehnt."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id, status="ungueltig"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_order_rejects_invalid_mode() -> None:
    """@trace ausfuehrung-paper#AC8 — `mode` nur `echt`/`simuliert`
    (→ BR-113/BR-130)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id, mode="ungueltig"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_order_rejects_non_positive_menge() -> None:
    """@trace ausfuehrung-paper#AC6 — `menge` muss > 0 sein."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        session.add(_valid_order(instrument_id, menge=Decimal("0")))
        with pytest.raises(IntegrityError):
            session.commit()


def _valid_trade_fill(order_id: uuid.UUID, **overrides: object) -> TradeFill:
    kwargs = {
        "id": uuid.uuid4(),
        "order_id": order_id,
        "fill_preis": Decimal("150"),
        "fill_menge": Decimal("10"),
        "courtage_chf": Decimal("2"),
        "spread_kosten_chf": Decimal("0"),
        "slippage_abs": Decimal("1"),
        "executed_at": datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
    }
    kwargs.update(overrides)
    return TradeFill(**kwargs)


def test_trade_fill_traegt_ac7_felder_inkl_slippage() -> None:
    """@trace ausfuehrung-paper#AC7 — `trade_fill.slippage_abs` (→ BR-114)
    ist NOT NULL und wird persistiert."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        order = _valid_order(instrument_id, status="filled")
        session.add(order)
        session.commit()

        session.add(_valid_trade_fill(order.id, slippage_abs=Decimal("1.25")))
        session.commit()

        zeile = session.query(TradeFill).one()
        assert zeile.order_id == order.id
        assert zeile.fill_preis == Decimal("150")
        assert zeile.fill_menge == Decimal("10")
        assert zeile.slippage_abs == Decimal("1.25")
        assert zeile.courtage_chf == Decimal("2")
        assert zeile.spread_kosten_chf == Decimal("0")


def test_trade_fill_rejects_non_positive_fill_menge() -> None:
    """@trace ausfuehrung-paper#AC7 — `fill_menge` muss > 0 sein."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        order = _valid_order(instrument_id, status="filled")
        session.add(order)
        session.commit()

        session.add(_valid_trade_fill(order.id, fill_menge=Decimal("0")))
        with pytest.raises(IntegrityError):
            session.commit()


def test_trade_fill_courtage_und_spread_haben_default_null() -> None:
    """@trace ausfuehrung-paper#AC7 — `courtage_chf`/`spread_kosten_chf`
    fallen ohne Angabe auf den Schema-Default `0` zurück (data-model.md §4
    `trade_fill`)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        order = _valid_order(instrument_id, status="filled")
        session.add(order)
        session.commit()

        eintrag = TradeFill(
            id=uuid.uuid4(),
            order_id=order.id,
            fill_preis=Decimal("150"),
            fill_menge=Decimal("10"),
            slippage_abs=Decimal("0"),
            executed_at=datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
        )
        session.add(eintrag)
        session.commit()
        session.refresh(eintrag)

        assert eintrag.courtage_chf == Decimal("0")
        assert eintrag.spread_kosten_chf == Decimal("0")
