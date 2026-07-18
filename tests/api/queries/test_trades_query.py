"""Tests für die Query-Funktion `app.api.queries.trades.hole_trade_historie`
(Story S-067, `docs/specs/frontend-cockpit.md` AC6/AC7).

Covers (frontend-cockpit): AC6, AC7

Isolierter Unit-Test der Query-Funktion selbst (Fake-`PositionRepository`,
kein HTTP) — Ergänzung zum HTTP-Ebenen-Test `tests/api/test_trades.py`
(coder/R06): belegt, dass die Filter-Parameter 1:1 an
`PositionRepository.historie_depotweit` durchgereicht werden (AC7:
"die Query-Funktion ist der einzige Ort, an dem das Gap geschlossen
wird") und jedes `TransaktionsEintrag`-Feld verlustfrei auf
`TradeHistorieEintrag` abgebildet wird (AC6)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.api.queries.trades import hole_trade_historie
from app.domain.portfolio.ports import TransaktionsEintrag


class _FakePositionRepository:
    def __init__(self, trades: list[TransaktionsEintrag]):
        self._trades = trades
        self.aufrufe: list[dict[str, object]] = []

    def historie_depotweit(self, *, mode, titel_id=None, von=None, bis=None):
        self.aufrufe.append({"mode": mode, "titel_id": titel_id, "von": von, "bis": bis})
        return self._trades


def test_hole_trade_historie_reicht_filter_unveraendert_durch():
    """@trace frontend-cockpit#AC6,AC7."""
    repository = _FakePositionRepository([])

    ergebnis = hole_trade_historie(
        repository,
        mode="simuliert",
        titel_id="titel-1",
        von=datetime(2026, 7, 1, tzinfo=UTC),
        bis=datetime(2026, 7, 31, tzinfo=UTC),
    )

    assert ergebnis.mode == "simuliert"
    assert ergebnis.trades == []
    assert repository.aufrufe == [
        {
            "mode": "simuliert",
            "titel_id": "titel-1",
            "von": datetime(2026, 7, 1, tzinfo=UTC),
            "bis": datetime(2026, 7, 31, tzinfo=UTC),
        }
    ]


def test_hole_trade_historie_bildet_alle_ac6_felder_verlustfrei_ab():
    """@trace frontend-cockpit#AC6 — jedes `TransaktionsEintrag`-Feld
    (inkl. Slippage/TCA + FX-Split) landet unverändert im DTO."""
    eintrag = TransaktionsEintrag(
        trade_id="t-1",
        titel_id="titel-1",
        richtung="verkauf",
        menge=Decimal("3"),
        fill_preis=Decimal("50"),
        arrival_price=Decimal("49"),
        slippage=Decimal("1"),
        kosten=Decimal("2"),
        waehrung="USD",
        zeitstempel=datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        fx_rate=Decimal("0.9"),
        kapital_gv_chf=Decimal("1.5"),
        waehrungs_gv_chf=Decimal("-0.5"),
    )
    repository = _FakePositionRepository([eintrag])

    ergebnis = hole_trade_historie(repository, mode="echt")

    trade = ergebnis.trades[0]
    assert trade.trade_id == "t-1"
    assert trade.titel_id == "titel-1"
    assert trade.richtung == "verkauf"
    assert trade.menge == Decimal("3")
    assert trade.fill_preis == Decimal("50")
    assert trade.arrival_price == Decimal("49")
    assert trade.slippage == Decimal("1")
    assert trade.kosten == Decimal("2")
    assert trade.waehrung == "USD"
    assert trade.zeitstempel == eintrag.zeitstempel
    assert trade.fx_rate == Decimal("0.9")
    assert trade.kapital_gv_chf == Decimal("1.5")
    assert trade.waehrungs_gv_chf == Decimal("-0.5")
