"""Tests für `SqlAlchemyExecutionRepository` (Story S-048, Spec
`docs/specs/ausfuehrung-paper.md` AC7/AC8).

Covers (ausfuehrung-paper): AC7, AC8

`speichere_ausfuehrung` legt IMMER eine `order`-Zeile an; NUR bei
`ergebnis.status ∈ {"filled", "partial"}` zusätzlich eine `trade_fill`-Zeile
(BR-139: kein Fill-Eintrag bei `"rejected"`/`"timeout"` — kein Bestand wird
ohne bestätigten Fill verändert)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.order_repository import SqlAlchemyExecutionRepository
from app.contracts.ausfuehrung_paper import Ausfuehrungsergebnis, OrderAnfrage
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


def _anfrage(**overrides: object) -> OrderAnfrage:
    basis: dict[str, object] = dict(
        titel_id="AAPL",
        asset_class_id=1,
        richtung="kauf",
        groesse=Decimal("10"),
        order_typ="limit",
        preis=Decimal("150"),
    )
    basis.update(overrides)
    return OrderAnfrage(**basis)


def _ergebnis(**overrides: object) -> Ausfuehrungsergebnis:
    basis: dict[str, object] = dict(
        order_id=str(uuid.uuid4()),
        titel_id="AAPL",
        richtung="kauf",
        status="filled",
        angefragte_menge=Decimal("10"),
        ausgefuehrte_menge=Decimal("10"),
        fill_preis=Decimal("151"),
        tatsaechliche_kosten=Decimal("2"),
        arrival_price=Decimal("150"),
        slippage=Decimal("1"),
        restmenge=Decimal("0"),
        restmenge_verhalten=None,
        ablehnungsgrund=None,
    )
    basis.update(overrides)
    return Ausfuehrungsergebnis(**basis)


def test_ac7_ac8_filled_legt_order_und_trade_fill_an() -> None:
    """@trace ausfuehrung-paper#AC7,AC8 — ein `"filled"`-Ergebnis legt eine
    `order`-Zeile (status="filled") UND eine `trade_fill`-Zeile mit der
    korrekten Slippage an."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        repo = SqlAlchemyExecutionRepository(session)

        repo.speichere_ausfuehrung(
            _anfrage(), _ergebnis(status="filled"), instrument_id=instrument_id
        )
        session.commit()

        order = session.query(Order).one()
        assert order.status == "filled"
        assert order.instrument_id == instrument_id
        assert order.richtung == "buy"
        assert order.mode == "simuliert"
        assert order.position_id is None

        fill = session.query(TradeFill).one()
        assert fill.order_id == order.id
        assert fill.fill_preis == Decimal("151")
        assert fill.fill_menge == Decimal("10")
        assert fill.slippage_abs == Decimal("1")
        assert fill.courtage_chf == Decimal("2")


def test_ac8_partial_legt_order_status_teilfill_und_trade_fill_an() -> None:
    """@trace ausfuehrung-paper#AC8 — E1: `status="partial"` mappt auf
    `order.status="teilfill"`, ein `trade_fill`-Eintrag entsteht trotzdem
    (ein Teilfill IST ein bestätigter Fill)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        repo = SqlAlchemyExecutionRepository(session)

        repo.speichere_ausfuehrung(
            _anfrage(groesse=Decimal("10")),
            _ergebnis(
                status="partial",
                ausgefuehrte_menge=Decimal("6"),
                restmenge=Decimal("4"),
                restmenge_verhalten="weiter_offen",
            ),
            instrument_id=instrument_id,
        )
        session.commit()

        order = session.query(Order).one()
        assert order.status == "teilfill"

        fill = session.query(TradeFill).one()
        assert fill.fill_menge == Decimal("6")


@pytest.mark.parametrize("status", ["rejected", "timeout"])
def test_ac8_reject_und_timeout_legen_keine_trade_fill_zeile_an(status: str) -> None:
    """@trace ausfuehrung-paper#AC8 — BR-139: bei `"rejected"`/`"timeout"`
    entsteht NUR die `order`-Zeile, KEIN `trade_fill`-Eintrag (kein Bestand
    ohne bestätigten Fill verändert)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        repo = SqlAlchemyExecutionRepository(session)

        repo.speichere_ausfuehrung(
            _anfrage(),
            _ergebnis(
                status=status,
                ausgefuehrte_menge=Decimal("0"),
                fill_preis=None,
                tatsaechliche_kosten=Decimal("0"),
                slippage=None,
                restmenge=Decimal("10"),
                ablehnungsgrund="Test-Grund" if status == "rejected" else None,
            ),
            instrument_id=instrument_id,
        )
        session.commit()

        order = session.query(Order).one()
        assert order.status == ("rejected" if status == "rejected" else "timeout")
        assert session.query(TradeFill).count() == 0


def test_verkauf_richtung_wird_korrekt_gemappt() -> None:
    """@trace ausfuehrung-paper#AC7 — `richtung="verkauf"` mappt auf
    `order.richtung="sell"` (data-model.md §4 `ORDER_RICHTUNG_VALUES`)."""
    engine = _engine()
    with Session(engine) as session:
        instrument_id = _seed_instrument(session)
        repo = SqlAlchemyExecutionRepository(session)

        repo.speichere_ausfuehrung(
            _anfrage(richtung="verkauf"),
            _ergebnis(richtung="verkauf"),
            instrument_id=instrument_id,
        )
        session.commit()

        assert session.query(Order).one().richtung == "sell"
