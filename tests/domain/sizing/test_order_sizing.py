"""Tests für die Pre-Trade-Kostenkalkulation & Mindest-Ordergrösse
(Story S-041).

Covers (sizing): AC5, AC6

`app.domain.sizing.order_sizing.berechne_ordergroesse` kombiniert
`risiko_pct` (S-039) + Kapitalbasis + `ErwarteteKosten` (S-017) zur
absoluten Netto-Ordergrösse: AC5 prüft, dass die erwarteten Kosten die
Grösse reduzieren bzw. den Trade verwerfen, wenn nach Kostenabzug keine
positive Grösse verbleibt; AC6 prüft, dass die resultierende
Netto-Grösse gegen die konfigurierte Mindest-Ordergrösse geprüft wird
(deckt E2), inkl. des Grenzfalls "genau an der Mindestgrenze" (kein
Verwerfen — nur ein echtes Unterschreiten verwirft).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from app.contracts.ausfuehrung_paper import ErwarteteKosten
from app.contracts.sizing import OrdergroessenKonfiguration
from app.domain.sizing.order_sizing import berechne_ordergroesse

_PLATTFORM_ID = uuid.uuid4()


def _erwartete_kosten(*, gesamtkosten_chf: Decimal, order_wert_chf: Decimal) -> ErwarteteKosten:
    """Test-Helper: baut einen `ErwarteteKosten`-Vertrag (S-017) mit
    frei wählbaren `gesamtkosten_chf` — die interne Aufteilung
    (Courtage/Spread/Slippage) ist für AC5/AC6 dieser Story irrelevant,
    nur die aggregierte Summe zählt."""
    return ErwarteteKosten(
        plattform_id=_PLATTFORM_ID,
        plattform_name="Test-Plattform",
        asset_class_id=1,
        order_wert_chf=order_wert_chf,
        courtage_chf=gesamtkosten_chf,
        mindestgebuehr_chf=Decimal("0"),
        courtage_effektiv_chf=gesamtkosten_chf,
        mindestgebuehr_greift=False,
        spread_kosten_chf=Decimal("0"),
        geschaetzte_slippage_chf=Decimal("0"),
        gesamtkosten_chf=gesamtkosten_chf,
    )


def test_ac5_kosten_reduzieren_die_ordergroesse() -> None:
    """@trace sizing#AC5 — die erwarteten Kosten werden von der
    Brutto-Ordergrösse (risiko_pct * kapitalbasis_chf) abgezogen:
    0.1 * 10'000 = 1'000 Brutto, 50 Kosten -> 950 Netto."""
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("50"), order_wert_chf=Decimal("1000"))
    ergebnis = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0.1"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
    )
    assert ergebnis.ordergroesse_brutto_chf == Decimal("1000.00000000")
    assert ergebnis.ordergroesse_chf == Decimal("950.00000000")
    assert ergebnis.kosten_chf == Decimal("50")
    assert ergebnis.verworfen is None


def test_ac5_kosten_gleich_brutto_verwirft_trade() -> None:
    """@trace sizing#AC5 — verbleibt nach Kostenabzug genau 0 (keine
    positive Netto-Grösse), wird kein Trade erzeugt."""
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("1000"), order_wert_chf=Decimal("1000"))
    ergebnis = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0.1"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
    )
    assert ergebnis.verworfen == "kosten-uebersteigen-ertrag"
    assert ergebnis.ordergroesse_chf == Decimal(0)


def test_ac5_kosten_uebersteigen_brutto_verwirft_trade() -> None:
    """@trace sizing#AC5 — übersteigen die Kosten die Brutto-Ordergrösse
    (negative Netto-Grösse, "kein positiver erwarteter Gewinn"), wird
    kein Trade erzeugt."""
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("1500"), order_wert_chf=Decimal("1000"))
    ergebnis = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0.1"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
    )
    assert ergebnis.verworfen == "kosten-uebersteigen-ertrag"
    assert ergebnis.ordergroesse_chf == Decimal(0)


def test_ac6_ordergroesse_genau_an_der_mindestgrenze_wird_nicht_verworfen() -> None:
    """@trace sizing#AC6 — Netto-Ordergrösse == konfigurierte
    Mindest-Ordergrösse: die Grenze ist erreicht, kein Verwerfen
    ("unterschreitet" ist eine strikte Ungleichung)."""
    konfiguration = OrdergroessenKonfiguration(mindest_ordergroesse_chf=Decimal("950"))
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("50"), order_wert_chf=Decimal("1000"))
    ergebnis = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0.1"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
        konfiguration=konfiguration,
    )
    assert ergebnis.verworfen is None
    assert ergebnis.ordergroesse_chf == Decimal("950.00000000")


def test_ac6_ordergroesse_unter_der_mindestgrenze_wird_verworfen() -> None:
    """@trace sizing#AC6 — unterschreitet die Netto-Ordergrösse die
    konfigurierte Mindest-Ordergrösse (deckt E2), wird kein Auftrag
    erzeugt."""
    konfiguration = OrdergroessenKonfiguration(mindest_ordergroesse_chf=Decimal("950.01"))
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("50"), order_wert_chf=Decimal("1000"))
    ergebnis = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0.1"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
        konfiguration=konfiguration,
    )
    assert ergebnis.verworfen == "unter-mindest-ordergroesse"
    assert ergebnis.ordergroesse_chf == Decimal(0)


def test_ac6_mindest_ordergroesse_ist_konfigurierbar() -> None:
    """@trace sizing#AC6 — "Die Mindest-Ordergrösse ist ein
    konfigurierbarer Parameter": ein niedrigerer Wert lässt dieselbe
    Netto-Grösse passieren, die mit dem Default (50) verworfen würde."""
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("999.50"), order_wert_chf=Decimal("1000"))
    default_konfiguration = OrdergroessenKonfiguration()
    verworfen_mit_default = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0.1"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
        konfiguration=default_konfiguration,
    )
    assert verworfen_mit_default.verworfen == "unter-mindest-ordergroesse"

    niedrige_konfiguration = OrdergroessenKonfiguration(mindest_ordergroesse_chf=Decimal("0.1"))
    erlaubt_mit_niedriger_schwelle = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0.1"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
        konfiguration=niedrige_konfiguration,
    )
    assert erlaubt_mit_niedriger_schwelle.verworfen is None
    assert erlaubt_mit_niedriger_schwelle.ordergroesse_chf == Decimal("0.50000000")


def test_ac5_ungueltiger_risiko_pct_wirft() -> None:
    """@trace sizing#AC5 — `risiko_pct` ausserhalb [0, 1] ist kein
    gültiger Kapitalanteil."""
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("10"), order_wert_chf=Decimal("1000"))
    with pytest.raises(ValueError):
        berechne_ordergroesse(
            titel_id="AAA",
            risiko_pct=Decimal("1.5"),
            kapitalbasis_chf=Decimal("10000"),
            erwartete_kosten=kosten,
        )


def test_ac5_ungueltige_kapitalbasis_wirft() -> None:
    """@trace sizing#AC5 — `kapitalbasis_chf <= 0` ist keine gültige
    Kapitalbasis."""
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("10"), order_wert_chf=Decimal("1000"))
    with pytest.raises(ValueError):
        berechne_ordergroesse(
            titel_id="AAA",
            risiko_pct=Decimal("0.1"),
            kapitalbasis_chf=Decimal("0"),
            erwartete_kosten=kosten,
        )


def test_ac5_risiko_pct_null_wird_als_kein_trade_durchgereicht() -> None:
    """@trace sizing#AC5 — ein `risiko_pct=0` (S-039 verwirft einen Trade mit
    `kelly-negativ` → `risiko_pct=0`) ergibt eine Brutto-Grösse von 0; nach
    Kostenabzug bleibt keine positive Netto-Grösse, der Trade wird sauber als
    `kosten-uebersteigen-ertrag` verworfen (kein negatives/fälschlich positives
    Ergebnis, kein Crash)."""
    kosten = _erwartete_kosten(gesamtkosten_chf=Decimal("10"), order_wert_chf=Decimal("1000"))
    ergebnis = berechne_ordergroesse(
        titel_id="AAA",
        risiko_pct=Decimal("0"),
        kapitalbasis_chf=Decimal("10000"),
        erwartete_kosten=kosten,
    )
    assert ergebnis.ordergroesse_brutto_chf == Decimal(0)
    assert ergebnis.ordergroesse_chf == Decimal(0)
    assert ergebnis.verworfen == "kosten-uebersteigen-ertrag"
