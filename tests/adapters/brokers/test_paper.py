"""Tests für die Paper-Broker-Adapter (Story S-046 + S-048 + S-049).

Covers (ausfuehrung-paper): AC1, AC5, AC7, AC8, AC9

`IbkrPaperBrokerAdapter`/`KryptoSimBrokerAdapter` implementieren
`app.domain.execution.ports.BrokerPort` identisch bis auf den fest
zugewiesenen `broker_endpunkt_typ` (AC5) — beide liefern eine
`OrderBestaetigung`, die die `OrderAnfrage` echofasst (AC1, Order wird
angenommen).

S-048 ergänzt `ermittle_fill` (AC7/AC8): die deterministische MVP-Paper-
Simulation füllt jede Order vollständig zum bereits bekannten Referenzpreis
(`anfrage.preis`, sonst `arrival_price` bei einer Market-Order) — siehe
Moduldocstring `app.adapters.brokers.paper`. Die AC7/AC8-Tests unten setzen
`spread_pct=Decimal("0")`/`slippage_pct=Decimal("0")` explizit (statt sich
auf die `Settings`-Defaults zu verlassen), um ausschliesslich die
Referenzpreis-AUSWAHL zu prüfen — unabhängig vom AC9-Slippage-/Spread-
Modell (eigener Testblock unten).

S-049 ergänzt das AC9/A2-Slippage-/Spread-Modell (`berechne_paper_fill_preis`,
per Adapter-Konstruktor konfigurierbar): Paper-Fills weichen jetzt
richtungsabhängig vom Referenzpreis ab (Kauf teurer, Verkauf günstiger)."""

from __future__ import annotations

from decimal import Decimal

from app.adapters.brokers.paper import (
    IbkrPaperBrokerAdapter,
    KryptoSimBrokerAdapter,
    berechne_paper_fill_preis,
)
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
    gesetzt) ist der Limit-Preis der Referenzpreis der MVP-Paper-Simulation
    (Slippage-Modell hier bewusst ausgeschaltet — eigener AC9-Testblock
    unten prüft die Abweichung)."""
    adapter = IbkrPaperBrokerAdapter(spread_pct=Decimal("0"), slippage_pct=Decimal("0"))
    anfrage = _order_anfrage(order_typ="limit", preis=Decimal("150"))
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("149"))

    assert meldung.status == "filled"
    assert meldung.fill_preis == Decimal("150")
    assert meldung.ausgefuehrte_menge == anfrage.groesse


def test_ac7_ermittle_fill_fuellt_zum_arrival_price_bei_market_order() -> None:
    """@trace ausfuehrung-paper#AC7 — bei einer Market-Order (`preis=None`)
    ist der Arrival-Price der einzige verfügbare Referenzpreis der
    MVP-Simulation (Slippage-Modell hier bewusst ausgeschaltet)."""
    adapter = KryptoSimBrokerAdapter(spread_pct=Decimal("0"), slippage_pct=Decimal("0"))
    anfrage = _order_anfrage(order_typ="market", preis=None)
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("148"))

    assert meldung.status == "filled"
    assert meldung.fill_preis == Decimal("148")


def test_ac8_ermittle_fill_liefert_keine_kosten_ohne_plattform_kalkulation() -> None:
    """@trace ausfuehrung-paper#AC8 — die MVP-Simulation kalkuliert keine
    eigenen Kosten (`tatsaechliche_kosten=0`, die Pre-Trade-Kalkulation ist
    AC10/AC11, S-017 — ein eigenständiger Vertrag)."""
    adapter = IbkrPaperBrokerAdapter(spread_pct=Decimal("0"), slippage_pct=Decimal("0"))
    anfrage = _order_anfrage()
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("150"))

    assert meldung.tatsaechliche_kosten == Decimal("0")


# ---------------------------------------------------------------------------
# AC9 (S-049) — eigenes Slippage-/Spread-Modell auf Paper-Fills (deckt A2)
# ---------------------------------------------------------------------------


def test_ac9_berechne_paper_fill_preis_kauf_ist_teurer_als_referenzpreis() -> None:
    """@trace ausfuehrung-paper#AC9 — ein Kauf füllt teurer als der
    Referenzpreis (Spread + Slippage schlagen auf)."""
    fill_preis = berechne_paper_fill_preis(
        Decimal("100"), richtung="kauf", spread_pct=Decimal("0.05"), slippage_pct=Decimal("0.05")
    )

    assert fill_preis == Decimal("100.10000000")
    assert fill_preis > Decimal("100")


def test_ac9_berechne_paper_fill_preis_verkauf_ist_guenstiger_als_referenzpreis() -> None:
    """@trace ausfuehrung-paper#AC9 — ein Verkauf füllt günstiger als der
    Referenzpreis (Spread + Slippage ziehen ab) — spiegelbildlich zum
    Kauf-Aufschlag."""
    fill_preis = berechne_paper_fill_preis(
        Decimal("100"),
        richtung="verkauf",
        spread_pct=Decimal("0.05"),
        slippage_pct=Decimal("0.05"),
    )

    assert fill_preis == Decimal("99.90000000")
    assert fill_preis < Decimal("100")


def test_ac9_berechne_paper_fill_preis_spread_null_nutzt_nur_slippage() -> None:
    """@trace ausfuehrung-paper#AC9 — Grenzfall `spread_pct=0`: nur die
    Slippage-Komponente wirkt, kein struktureller Fehler bei einer
    ausgeschalteten Modell-Komponente."""
    fill_preis = berechne_paper_fill_preis(
        Decimal("200"), richtung="kauf", spread_pct=Decimal("0"), slippage_pct=Decimal("0.1")
    )

    assert fill_preis == Decimal("200.20000000")


def test_ac9_berechne_paper_fill_preis_beide_parameter_null_liefert_referenzpreis() -> None:
    """@trace ausfuehrung-paper#AC9 — Grenzfall `spread_pct=0` UND
    `slippage_pct=0`: der Referenzpreis bleibt unverändert (kein
    struktureller Zwang zu einer Abweichung ungleich null)."""
    fill_preis = berechne_paper_fill_preis(
        Decimal("150"), richtung="verkauf", spread_pct=Decimal("0"), slippage_pct=Decimal("0")
    )

    assert fill_preis == Decimal("150.00000000")


def test_ac9_berechne_paper_fill_preis_ist_deterministisch() -> None:
    """@trace ausfuehrung-paper#AC9 — P3: keine Zufallskomponente, gleiche
    Eingabe liefert immer denselben Fill-Preis."""
    ergebnisse = {
        berechne_paper_fill_preis(
            Decimal("123.45"),
            richtung="kauf",
            spread_pct=Decimal("0.05"),
            slippage_pct=Decimal("0.05"),
        )
        for _ in range(5)
    }

    assert len(ergebnisse) == 1


def test_ac9_ermittle_fill_wendet_konfigurierbare_parameter_je_adapter_an() -> None:
    """@trace ausfuehrung-paper#AC9 — die Slippage-/Spread-Parameter sind
    je Adapter-Instanz konfigurierbar (Konstruktor-Override statt fixem
    Wert) und wirken auf `ermittle_fill` (nicht nur auf die reine Formel)."""
    adapter = IbkrPaperBrokerAdapter(spread_pct=Decimal("1"), slippage_pct=Decimal("1"))
    anfrage = _order_anfrage(order_typ="limit", preis=Decimal("100"), richtung="kauf")
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("100"))

    assert meldung.fill_preis == Decimal("102.00000000")


def test_ac9_ermittle_fill_nutzt_settings_default_wenn_kein_override() -> None:
    """@trace ausfuehrung-paper#AC9 — ohne expliziten Konstruktor-Override
    liest der Adapter die provisorischen `Settings`-Defaults
    (`paper_fill_spread_pct_default`/`paper_fill_slippage_pct_default`,
    je 0.05 %) — ein Paper-Fill weicht damit standardmässig vom
    Referenzpreis ab (A2: "nicht zum unveränderten Signal-Kurs")."""
    adapter = IbkrPaperBrokerAdapter()
    anfrage = _order_anfrage(order_typ="limit", preis=Decimal("100"), richtung="kauf")
    bestaetigung = adapter.platziere_order(anfrage)

    meldung = adapter.ermittle_fill(anfrage, bestaetigung, arrival_price=Decimal("100"))

    assert meldung.fill_preis == Decimal("100.10000000")
    assert meldung.fill_preis != Decimal("100")
