"""Tests für die Paper-Broker-Adapter (Story S-046).

Covers (ausfuehrung-paper): AC1, AC5

`IbkrPaperBrokerAdapter`/`KryptoSimBrokerAdapter` implementieren
`app.domain.execution.ports.BrokerPort` identisch bis auf den fest
zugewiesenen `broker_endpunkt_typ` (AC5) — beide liefern eine
`OrderBestaetigung`, die die `OrderAnfrage` echofasst (AC1, Order wird
angenommen)."""

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
