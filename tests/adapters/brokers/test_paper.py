"""Tests für die Paper-Broker-Adapter (Story S-046 + S-048).

Covers (ausfuehrung-paper): AC1, AC5, AC7, AC8

`IbkrPaperBrokerAdapter`/`KryptoSimBrokerAdapter` implementieren
`app.domain.execution.ports.BrokerPort` identisch bis auf den fest
zugewiesenen `broker_endpunkt_typ` (AC5) — beide liefern eine
`OrderBestaetigung`, die die `OrderAnfrage` echofasst (AC1, Order wird
angenommen).

S-048 ergänzt `ermittle_fill` (AC7/AC8): die deterministische MVP-Paper-
Simulation füllt jede Order vollständig zum bereits bekannten Preis
(`anfrage.preis`, sonst `arrival_price` bei einer Market-Order) — siehe
Moduldocstring `app.adapters.brokers.paper`."""

from __future__ import annotations

from decimal import Decimal

from app.adapters.brokers.paper import IbkrPaperBrokerAdapter, KryptoSimBrokerAdapter
from app.contracts.ausfuehrung_paper import OrderAnfrage


def _order_anfrage(**overrides: object) -> OrderAnfrage:
    basis = dict(
        titel_id="AAPL",
        asset_class_id=1,
        richtung="kauf",
        groesse=Decimal("500"),
        order_typ="limit",
        preis=Decimal("150"),
    )
    basis.update(overrides)
    return OrderAnfrage(**basis)


def test_ac5_ibkr_paper_adapter_meldet_eigenen_endpunkt_typ() -> None:
    """@trace ausfuehrung-paper#AC5 — `IbkrPaperBrokerAdapter` bestätigt
    Order-Annahme mit `broker_endpunkt_typ="ibkr_paper"`."""
    bestaetigung = IbkrPaperBrokerAdapter().platziere_order(_order_anfrage())

    assert bestaetigung.broker_endpunkt_typ == "ibkr_paper"
    assert bestaetigung.titel_id == "AAPL"
    assert bestaetigung.groesse == Decimal("500")
    assert bestaetigung.preis == Decimal("150")
    assert bestaetigung.order_id


def test_ac5_krypto_sim_adapter_meldet_eigenen_endpunkt_typ() -> None:
    """@trace ausfuehrung-paper#AC5 — `KryptoSimBrokerAdapter` bestätigt
    Order-Annahme mit `broker_endpunkt_typ="krypto_sim_brokerless"`."""
    bestaetigung = KryptoSimBrokerAdapter().platziere_order(
        _order_anfrage(richtung="verkauf", order_typ="market", preis=None)
    )

    assert bestaetigung.broker_endpunkt_typ == "krypto_sim_brokerless"
    assert bestaetigung.richtung == "verkauf"
    assert bestaetigung.order_typ == "market"
    assert bestaetigung.preis is None


def test_ac1_beide_adapter_liefern_unterschiedliche_order_ids() -> None:
    """@trace ausfuehrung-paper#AC1 — jede Order-Annahme erhält eine
    eigene `order_id` (keine zufällig kollidierenden Platzhalter)."""
    adapter = IbkrPaperBrokerAdapter()
    erste = adapter.platziere_order(_order_anfrage())
    zweite = adapter.platziere_order(_order_anfrage())

    assert erste.order_id != zweite.order_id


# ---------------------------------------------------------------------------
# AC7/AC8 (S-048) — `ermittle_fill`: deterministischer Happy-Path-Fill
# ---------------------------------------------------------------------------


def test_ac7_ermittle_fill_fuellt_zum_anfrage_preis_bei_limit_order() -> None:
    """@trace ausfuehrung-paper#AC7 — bei einer Limit-Order (`preis`
    gesetzt) füllt die MVP-Paper-Simulation zu genau diesem Preis."""
    adapter = IbkrPaperBrokerAdapter()
    anfrage = _order_anfrage(order_typ="limit", preis=Decimal("150"))
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("149"))

    assert meldung.status == "filled"
    assert meldung.fill_preis == Decimal("150")
    assert meldung.ausgefuehrte_menge == anfrage.groesse


def test_ac7_ermittle_fill_fuellt_zum_arrival_price_bei_market_order() -> None:
    """@trace ausfuehrung-paper#AC7 — bei einer Market-Order (`preis=None`)
    ist der Arrival-Price der einzige verfügbare Referenzpreis der
    MVP-Simulation (kein Slippage-/Spread-Modell, AC9/S-049 Nicht-Ziel)."""
    adapter = KryptoSimBrokerAdapter()
    anfrage = _order_anfrage(order_typ="market", preis=None)
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("148"))

    assert meldung.status == "filled"
    assert meldung.fill_preis == Decimal("148")


def test_ac8_ermittle_fill_liefert_keine_kosten_ohne_plattform_kalkulation() -> None:
    """@trace ausfuehrung-paper#AC8 — die MVP-Simulation kalkuliert keine
    eigenen Kosten (`tatsaechliche_kosten=0`, die Pre-Trade-Kalkulation ist
    AC10/AC11, S-017 — ein eigenständiger Vertrag)."""
    adapter = IbkrPaperBrokerAdapter()
    anfrage = _order_anfrage()
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("150"))

    assert meldung.tatsaechliche_kosten == Decimal("0")
