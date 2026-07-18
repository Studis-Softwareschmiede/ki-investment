"""Tests für das Fill-Handling des Order-Ausführungs-Kerns (Story S-048).

Covers (ausfuehrung-paper): AC5, AC7, AC8

- AC7: `berechne_arrival_price_slippage` ist die reine Formel (Fill-Preis −
  Arrival-Price); `verarbeite_fill` wendet sie NUR bei einem bestätigten
  Fill (`status ∈ {"filled", "partial"}`) an — bei `"rejected"`/`"timeout"`
  bleibt `slippage=None` (kein Fill, keine Slippage messbar).
- AC8 (deckt E1-E3): `verarbeite_fill` verarbeitet eine rohe
  `BrokerFillMeldung` zum vollständigen `Ausfuehrungsergebnis`:
  - E1 (Teilfill): `status="partial"` — die Restmenge wird über
    `bestimme_restmenge_verhalten` je Order-Typ behandelt (weiter offen für
    resting Order-Typen, storniert für "sofort oder gar nicht"-Typen), kein
    stiller Verlust der Restmenge.
  - E2 (Reject) / E3 (Timeout): `status ∈ {"rejected", "timeout"}` liefert
    strukturell KEINEN Fill-Preis/keine ausgeführte Menge (BR-139) — der
    Bestand bleibt strukturell unverändert (kein Depot-Aufruf möglich ohne
    `fill_preis`).
  - Protokollierung (AC8 "protokolliert"): `"partial"`/`"rejected"`/
    `"timeout"` werden über `app.core.order_audit_log` festgehalten,
    `"filled"` nicht.
  - `fuehre_order_aus_und_verarbeite_fill` kombiniert Order-Annahme +
    Fill-Ermittlung + Verarbeitung zu einem Aufruf, gegen denselben Port."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.contracts.ausfuehrung_paper import (
    BrokerFillMeldung,
    ExecutionOrderTyp,
    OrderAnfrage,
    OrderBestaetigung,
)
from app.core import order_audit_log
from app.domain.execution.order_ausfuehrung import (
    berechne_arrival_price_slippage,
    bestimme_restmenge_verhalten,
    fuehre_order_aus_und_verarbeite_fill,
    verarbeite_fill,
)


@pytest.fixture(autouse=True)
def _reset_audit_log():
    order_audit_log.reset_fuer_tests()
    yield
    order_audit_log.reset_fuer_tests()


def _anfrage(**overrides: object) -> OrderAnfrage:
    basis: dict[str, object] = dict(
        titel_id="AAPL",
        asset_class_id=1,
        richtung="kauf",
        groesse=Decimal("100"),
        order_typ="limit",
        preis=Decimal("150"),
    )
    basis.update(overrides)
    return OrderAnfrage(**basis)


def _bestaetigung(anfrage: OrderAnfrage, **overrides: object) -> OrderBestaetigung:
    basis: dict[str, object] = dict(
        order_id=str(uuid.uuid4()),
        broker_endpunkt_typ="ibkr_paper",
        titel_id=anfrage.titel_id,
        richtung=anfrage.richtung,
        order_typ=anfrage.order_typ,
        groesse=anfrage.groesse,
        preis=anfrage.preis,
    )
    basis.update(overrides)
    return OrderBestaetigung(**basis)


class _FakeBrokerPort:
    """Test-Double des `BrokerPort`-Protocol — meldet eine vorkonfigurierte
    `BrokerFillMeldung`, unabhängig von der `OrderAnfrage`."""

    def __init__(self, *, broker_endpunkt_typ: str, meldung: BrokerFillMeldung) -> None:
        self._broker_endpunkt_typ = broker_endpunkt_typ
        self._meldung = meldung
        self.ermittelte_anfragen: list[OrderAnfrage] = []

    def platziere_order(self, anfrage: OrderAnfrage) -> OrderBestaetigung:
        return OrderBestaetigung(
            order_id=str(uuid.uuid4()),
            broker_endpunkt_typ=self._broker_endpunkt_typ,
            titel_id=anfrage.titel_id,
            richtung=anfrage.richtung,
            order_typ=anfrage.order_typ,
            groesse=anfrage.groesse,
            preis=anfrage.preis,
        )

    def ermittle_fill(
        self, anfrage: OrderAnfrage, bestaetigung: OrderBestaetigung, *, arrival_price: Decimal
    ) -> BrokerFillMeldung:
        self.ermittelte_anfragen.append(anfrage)
        return self._meldung


# ---------------------------------------------------------------------------
# AC7 — Arrival-Price-Slippage-Formel
# ---------------------------------------------------------------------------


def test_ac7_slippage_formel_positiv_bei_teurerem_fill() -> None:
    """@trace ausfuehrung-paper#AC7 — Fill teurer als Signal-Kurs → positive
    Slippage."""
    assert berechne_arrival_price_slippage(Decimal("101.50"), Decimal("100.00")) == Decimal("1.50")


def test_ac7_slippage_formel_negativ_bei_guenstigerem_fill() -> None:
    """@trace ausfuehrung-paper#AC7 — Fill günstiger als Signal-Kurs →
    negative Slippage."""
    assert berechne_arrival_price_slippage(Decimal("99.00"), Decimal("100.00")) == Decimal("-1.00")


def test_ac7_slippage_formel_null_bei_identischem_fill() -> None:
    """@trace ausfuehrung-paper#AC7 — Fill exakt zum Signal-Kurs → Slippage
    0."""
    assert berechne_arrival_price_slippage(Decimal("100"), Decimal("100")) == Decimal("0")


def test_ac7_verarbeite_fill_berechnet_slippage_bei_vollstaendigem_fill() -> None:
    """@trace ausfuehrung-paper#AC7 — ein vollständiger Fill trägt die
    korrekt berechnete Slippage + den Arrival-Price."""
    anfrage = _anfrage(groesse=Decimal("100"), preis=Decimal("150"))
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(
        status="filled",
        ausgefuehrte_menge=Decimal("100"),
        fill_preis=Decimal("151"),
        tatsaechliche_kosten=Decimal("5"),
    )

    ergebnis = verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    assert ergebnis.status == "filled"
    assert ergebnis.fill_preis == Decimal("151")
    assert ergebnis.arrival_price == Decimal("150")
    assert ergebnis.slippage == Decimal("1")
    assert ergebnis.ausgefuehrte_menge == Decimal("100")
    assert ergebnis.tatsaechliche_kosten == Decimal("5")
    assert ergebnis.restmenge == Decimal("0")
    assert ergebnis.restmenge_verhalten is None


def test_ac7_geld_felder_werden_auf_numeric_8_quantisiert() -> None:
    """@trace ausfuehrung-paper#AC7 — alle Geld-/Preis-Felder des Ergebnisses
    (fill_preis/tatsaechliche_kosten/arrival_price/slippage) werden an der
    NUMERIC(20,8)-Schreibgrenze kaufmännisch auf 8 Nachkommastellen gerundet
    (S-041/S-053-Lesson: sonst Postgres-vs-SQLite-Divergenz). Belegt mit
    Werten > 8 Nachkommastellen — glatte Fixtures prüfen die Quantisierung
    nicht."""
    anfrage = _anfrage(groesse=Decimal("100"), preis=Decimal("150"))
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(
        status="filled",
        ausgefuehrte_menge=Decimal("100"),
        fill_preis=Decimal("151.1234567891"),
        tatsaechliche_kosten=Decimal("5.0000000004"),
    )

    ergebnis = verarbeite_fill(
        anfrage, bestaetigung, meldung, arrival_price=Decimal("150.0000000006")
    )

    assert ergebnis.fill_preis == Decimal("151.12345679")
    assert ergebnis.tatsaechliche_kosten == Decimal("5.00000000")
    assert ergebnis.arrival_price == Decimal("150.00000000")
    assert ergebnis.slippage == Decimal("1.12345679")
    for wert in (
        ergebnis.fill_preis,
        ergebnis.tatsaechliche_kosten,
        ergebnis.arrival_price,
        ergebnis.slippage,
    ):
        assert wert.as_tuple().exponent == -8


def test_ac7_verarbeite_fill_bei_reject_hat_keine_slippage() -> None:
    """@trace ausfuehrung-paper#AC7 — ohne Fill (Reject) ist die Slippage
    nicht messbar → `None`, nicht fälschlich 0."""
    anfrage = _anfrage()
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(status="rejected", ablehnungsgrund="Kontingent erschöpft")

    ergebnis = verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    assert ergebnis.slippage is None
    assert ergebnis.fill_preis is None


# ---------------------------------------------------------------------------
# AC8/E1 — Teilfill: Restmenge protokolliert behandelt (weiter offen/storniert)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("order_typ", "erwartetes_verhalten"),
    [
        ("market", "storniert"),
        ("limit", "weiter_offen"),
        ("stop", "storniert"),
        ("stop_limit", "weiter_offen"),
        ("trailing", "weiter_offen"),
        ("twap", "weiter_offen"),
    ],
)
def test_ac8_e1_restmenge_verhalten_je_order_typ(
    order_typ: ExecutionOrderTyp, erwartetes_verhalten: str
) -> None:
    """@trace ausfuehrung-paper#AC8 — E1: "weiter offen / storniert je
    Order-Typ" — Market/Stop stornieren die Restmenge (sofort-oder-gar-
    nicht), Limit/Stop-Limit/Trailing/TWAP lassen sie weiter offen
    (resting)."""
    assert bestimme_restmenge_verhalten(order_typ) == erwartetes_verhalten


def test_ac8_e1_teilfill_meldet_ausgefuehrte_teilmenge_und_restmenge() -> None:
    """@trace ausfuehrung-paper#AC8 — E1: ein Teilfill meldet die
    tatsächlich ausgeführte Teilmenge (kein stiller Verlust der
    Restmenge) und bestimmt deren Verhalten je Order-Typ."""
    anfrage = _anfrage(groesse=Decimal("100"), order_typ="limit", preis=Decimal("150"))
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(
        status="partial",
        ausgefuehrte_menge=Decimal("60"),
        fill_preis=Decimal("150"),
        tatsaechliche_kosten=Decimal("3"),
    )

    ergebnis = verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("149"))

    assert ergebnis.status == "partial"
    assert ergebnis.ausgefuehrte_menge == Decimal("60")
    assert ergebnis.restmenge == Decimal("40")
    assert ergebnis.restmenge_verhalten == "weiter_offen"
    assert ergebnis.slippage == Decimal("1")


def test_ac8_e1_teilfill_market_storniert_restmenge() -> None:
    """@trace ausfuehrung-paper#AC8 — E1: ein Teilfill einer Market-Order
    storniert die Restmenge (kein Resting-Charakter)."""
    anfrage = _anfrage(groesse=Decimal("100"), order_typ="market", preis=None)
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(
        status="partial", ausgefuehrte_menge=Decimal("70"), fill_preis=Decimal("150")
    )

    ergebnis = verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    assert ergebnis.restmenge == Decimal("30")
    assert ergebnis.restmenge_verhalten == "storniert"


def test_ac8_e1_teilfill_wird_protokolliert() -> None:
    """@trace ausfuehrung-paper#AC8 — E1 "protokolliert": ein Teilfill wird
    im Audit-Log festgehalten."""
    anfrage = _anfrage()
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(
        status="partial", ausgefuehrte_menge=Decimal("50"), fill_preis=Decimal("150")
    )

    verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    eintraege = order_audit_log.alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].status == "partial"


# ---------------------------------------------------------------------------
# AC8/E2 — Reject: kein Bestand verändert, Grund protokolliert
# ---------------------------------------------------------------------------


def test_ac8_e2_reject_liefert_keinen_fill_und_wird_protokolliert() -> None:
    """@trace ausfuehrung-paper#AC8 — E2: eine abgelehnte Order liefert
    strukturell KEINEN Fill-Preis/keine ausgeführte Menge (BR-139) und wird
    mit Grund protokolliert."""
    anfrage = _anfrage(groesse=Decimal("100"))
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(status="rejected", ablehnungsgrund="Limit ausserhalb Marktband")

    ergebnis = verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    assert ergebnis.status == "rejected"
    assert ergebnis.fill_preis is None
    assert ergebnis.ausgefuehrte_menge == Decimal("0")
    assert ergebnis.restmenge == anfrage.groesse
    assert ergebnis.ablehnungsgrund == "Limit ausserhalb Marktband"

    eintraege = order_audit_log.alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].status == "rejected"
    assert eintraege[0].ablehnungsgrund == "Limit ausserhalb Marktband"


def test_ac8_e2_reject_ignoriert_fill_preis_einer_fehlerhaften_meldung() -> None:
    """@trace ausfuehrung-paper#AC8 — BR-139-Härtung: selbst wenn eine
    (fehlerhafte) Broker-Meldung bei `status="rejected"` einen `fill_preis`
    mitliefert, ignoriert `verarbeite_fill` ihn bewusst — kein Fill-Preis im
    Ergebnis."""
    anfrage = _anfrage()
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(
        status="rejected", fill_preis=Decimal("999"), ablehnungsgrund="inkonsistente Meldung"
    )

    ergebnis = verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    assert ergebnis.fill_preis is None
    assert ergebnis.status == "rejected"


# ---------------------------------------------------------------------------
# AC8/E3 — Timeout: kein Bestand verändert, protokolliert
# ---------------------------------------------------------------------------


def test_ac8_e3_timeout_liefert_keinen_fill_und_wird_protokolliert() -> None:
    """@trace ausfuehrung-paper#AC8 — E3: keine Antwort binnen Frist →
    keine Ausführung angenommen, kein Bestand verändert, protokolliert."""
    anfrage = _anfrage(groesse=Decimal("100"))
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(status="timeout")

    ergebnis = verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    assert ergebnis.status == "timeout"
    assert ergebnis.fill_preis is None
    assert ergebnis.ausgefuehrte_menge == Decimal("0")
    assert ergebnis.restmenge == anfrage.groesse

    eintraege = order_audit_log.alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].status == "timeout"


# ---------------------------------------------------------------------------
# Protokollierung — "filled" wird NICHT protokolliert (kein Fehlerfall)
# ---------------------------------------------------------------------------


def test_filled_wird_nicht_protokolliert() -> None:
    """@trace ausfuehrung-paper#AC8 — nur Teilfills/Rejects/Timeouts werden
    protokolliert (Spec-Wortlaut) — ein vollständiger Fill nicht."""
    anfrage = _anfrage()
    bestaetigung = _bestaetigung(anfrage)
    meldung = BrokerFillMeldung(
        status="filled", ausgefuehrte_menge=anfrage.groesse, fill_preis=Decimal("150")
    )

    verarbeite_fill(anfrage, bestaetigung, meldung, arrival_price=Decimal("150"))

    assert order_audit_log.alle_eintraege() == ()


# ---------------------------------------------------------------------------
# fuehre_order_aus_und_verarbeite_fill — kombinierter Aufruf
# ---------------------------------------------------------------------------


def test_fuehre_order_aus_und_verarbeite_fill_nutzt_denselben_port_fuer_beide_schritte() -> None:
    """@trace ausfuehrung-paper#AC7,AC8 — Order-Annahme + Fill-Ermittlung
    laufen gegen denselben (nach AC5 gewählten) `BrokerPort`."""
    ibkr_port = _FakeBrokerPort(
        broker_endpunkt_typ="ibkr_paper",
        meldung=BrokerFillMeldung(
            status="filled", ausgefuehrte_menge=Decimal("100"), fill_preis=Decimal("151")
        ),
    )
    krypto_port = _FakeBrokerPort(
        broker_endpunkt_typ="krypto_sim_brokerless",
        meldung=BrokerFillMeldung(status="rejected"),
    )
    anfrage = _anfrage(asset_class_id=1, groesse=Decimal("100"), preis=Decimal("150"))

    ergebnis = fuehre_order_aus_und_verarbeite_fill(
        anfrage,
        ibkr_paper_port=ibkr_port,
        krypto_sim_port=krypto_port,
        arrival_price=Decimal("150"),
    )

    assert ergebnis.status == "filled"
    assert ergebnis.fill_preis == Decimal("151")
    assert ergebnis.slippage == Decimal("1")
    assert anfrage in ibkr_port.ermittelte_anfragen
    assert krypto_port.ermittelte_anfragen == []


def test_fuehre_order_aus_und_verarbeite_fill_routet_krypto_auf_krypto_sim_port() -> None:
    """@trace ausfuehrung-paper#AC5,AC7,AC8 — Krypto-Order (AC5) nutzt für
    BEIDE Schritte den `krypto_sim_port`."""
    ibkr_port = _FakeBrokerPort(
        broker_endpunkt_typ="ibkr_paper", meldung=BrokerFillMeldung(status="filled")
    )
    krypto_port = _FakeBrokerPort(
        broker_endpunkt_typ="krypto_sim_brokerless",
        meldung=BrokerFillMeldung(
            status="filled", ausgefuehrte_menge=Decimal("10"), fill_preis=Decimal("50000")
        ),
    )
    anfrage = _anfrage(asset_class_id=7, groesse=Decimal("10"), preis=Decimal("50000"))

    ergebnis = fuehre_order_aus_und_verarbeite_fill(
        anfrage,
        ibkr_paper_port=ibkr_port,
        krypto_sim_port=krypto_port,
        arrival_price=Decimal("50000"),
    )

    assert ergebnis.fill_preis == Decimal("50000")
    assert anfrage in krypto_port.ermittelte_anfragen
    assert ibkr_port.ermittelte_anfragen == []
