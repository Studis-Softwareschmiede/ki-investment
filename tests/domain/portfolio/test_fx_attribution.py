"""Tests für die reinen FX-Attribution-Formeln (Story S-053, AC6).

Covers (depot): AC6

`app.domain.portfolio.fx_attribution` liefert die reinen Formel-Bausteine,
die den G/V einer Fremdwährungsposition/-Trades in Kapital- und
Währungsgewinn zerlegen (beide in CHF, deckt A3):

- `berechne_neuen_einstand_fx_rate_bei_kauf` — mengen-gewichtete Mittelung
  des Ø-Einstands-FX-Kurses bei Nachkauf (AC5-Analogie).
- `berechne_fx_split_realisiert` — realisierter Split je Verkauf(-santeil).
- `berechne_fx_split_unrealisiert` — unrealisierter Split je offener
  Position.
- `aggregiere_fx_split` — Summe mehrerer je-Lot ermittelter Splits (FIFO-
  Multi-Lot-Verkauf, A2).

Jeder Test prüft zusätzlich, dass `kapital_gv_chf + waehrungs_gv_chf`
exakt dem direkt berechneten Gesamt-G/V in CHF entspricht (kein
unattribuierter Rest, siehe Moduldocstring)."""

from __future__ import annotations

from decimal import Decimal

from app.domain.portfolio.fx_attribution import (
    FxSplit,
    aggregiere_fx_split,
    berechne_fx_split_realisiert,
    berechne_fx_split_unrealisiert,
    berechne_neuen_einstand_fx_rate_bei_kauf,
)


def test_berechne_neuen_einstand_fx_rate_bei_kauf_erster_kauf() -> None:
    """@trace depot#AC6 — der erste Kauf (`bisherige_menge == 0`) übernimmt
    den FX-Kurs des Fills unverändert."""
    ergebnis = berechne_neuen_einstand_fx_rate_bei_kauf(
        bisherige_menge=Decimal("0"),
        bisheriger_fx_rate=None,
        kauf_menge=Decimal("10"),
        kauf_fx_rate=Decimal("0.90"),
    )
    assert ergebnis == Decimal("0.90")


def test_berechne_neuen_einstand_fx_rate_bei_kauf_nachkauf_mittelt_gewichtet() -> None:
    """@trace depot#AC6 — ein Nachkauf mittelt den FX-Kurs mengen-gewichtet
    mit dem bisherigen (identisches Muster zu
    `position_booking.berechne_neuen_einstand_bei_kauf` für den Preis)."""
    ergebnis = berechne_neuen_einstand_fx_rate_bei_kauf(
        bisherige_menge=Decimal("10"),
        bisheriger_fx_rate=Decimal("0.90"),
        kauf_menge=Decimal("10"),
        kauf_fx_rate=Decimal("1.00"),
    )
    # (10*0.90 + 10*1.00) / 20 = 0.95
    assert ergebnis == Decimal("0.95")


def test_berechne_fx_split_realisiert_summe_entspricht_gesamt_gv_chf() -> None:
    """@trace depot#AC6 — die Summe aus Kapital- und Währungsgewinn
    entspricht exakt dem gesamten realisierten G/V in CHF
    (`erloes_netto_chf - kostenbasis_chf`)."""
    einstand_preis = Decimal("100")
    einstand_fx_rate = Decimal("0.90")
    verkauf_preis = Decimal("120")
    verkauf_fx_rate = Decimal("0.95")
    verkaufte_menge = Decimal("10")
    kosten = Decimal("5")

    split = berechne_fx_split_realisiert(
        einstand_preis=einstand_preis,
        einstand_fx_rate=einstand_fx_rate,
        verkauf_preis=verkauf_preis,
        verkauf_fx_rate=verkauf_fx_rate,
        verkaufte_menge=verkaufte_menge,
        kosten=kosten,
    )

    erloes_netto = verkaufte_menge * verkauf_preis - kosten
    erwartetes_kapital = (erloes_netto - einstand_preis * verkaufte_menge) * einstand_fx_rate
    erwartete_waehrung = erloes_netto * (verkauf_fx_rate - einstand_fx_rate)
    gesamt_chf_direkt = erloes_netto * verkauf_fx_rate - einstand_preis * verkaufte_menge * (
        einstand_fx_rate
    )

    assert split.kapital_gv_chf == erwartetes_kapital
    assert split.waehrungs_gv_chf == erwartete_waehrung
    assert split.kapital_gv_chf + split.waehrungs_gv_chf == gesamt_chf_direkt
    # Konkrete Werte (siehe Moduldocstring-Beispiel):
    assert split.kapital_gv_chf == Decimal("175.5")
    assert split.waehrungs_gv_chf == Decimal("59.75")


def test_berechne_fx_split_realisiert_bei_unveraendertem_fx_kurs_ist_waehrungsgewinn_null() -> None:
    """@trace depot#AC6 — bewegt sich der FX-Kurs zwischen Einstand und
    Verkauf nicht, ist der Währungsgewinn 0 und der Kapitalgewinn
    entspricht dem lokalen G/V, umgerechnet zum konstanten Kurs."""
    split = berechne_fx_split_realisiert(
        einstand_preis=Decimal("100"),
        einstand_fx_rate=Decimal("0.90"),
        verkauf_preis=Decimal("120"),
        verkauf_fx_rate=Decimal("0.90"),
        verkaufte_menge=Decimal("10"),
        kosten=Decimal("0"),
    )
    assert split.waehrungs_gv_chf == Decimal("0")
    assert split.kapital_gv_chf == Decimal("180")  # (1200-1000) * 0.90


def test_berechne_fx_split_unrealisiert_summe_entspricht_gesamt_gv_chf() -> None:
    """@trace depot#AC6 — die Summe aus Kapital- und Währungsgewinn
    entspricht exakt dem gesamten unrealisierten G/V in CHF (aktueller
    Marktwert CHF − Kostenbasis CHF)."""
    aktueller_preis = Decimal("130")
    einstand_preis = Decimal("100")
    aktueller_fx_rate = Decimal("0.92")
    einstand_fx_rate = Decimal("0.90")
    menge = Decimal("10")

    split = berechne_fx_split_unrealisiert(
        aktueller_preis=aktueller_preis,
        einstand_preis=einstand_preis,
        aktueller_fx_rate=aktueller_fx_rate,
        einstand_fx_rate=einstand_fx_rate,
        menge=menge,
    )

    gesamt_chf_direkt = (
        aktueller_preis * menge * aktueller_fx_rate - einstand_preis * menge * einstand_fx_rate
    )
    assert split.kapital_gv_chf + split.waehrungs_gv_chf == gesamt_chf_direkt
    assert split.kapital_gv_chf == Decimal("270")
    assert split.waehrungs_gv_chf == Decimal("26")


def test_berechne_fx_split_unrealisiert_negativer_kapitalgewinn_bei_kursverlust() -> None:
    """@trace depot#AC6 — ein aktueller Preis unter dem Einstand ergibt
    einen negativen Kapitalgewinn, kein struktureller Fehler."""
    split = berechne_fx_split_unrealisiert(
        aktueller_preis=Decimal("90"),
        einstand_preis=Decimal("100"),
        aktueller_fx_rate=Decimal("0.90"),
        einstand_fx_rate=Decimal("0.90"),
        menge=Decimal("10"),
    )
    assert split.kapital_gv_chf == Decimal("-90")
    assert split.waehrungs_gv_chf == Decimal("0")


def test_aggregiere_fx_split_summiert_mehrere_lot_splits() -> None:
    """@trace depot#AC6 — mehrere je-Lot ermittelte FX-Splits (FIFO-
    Multi-Lot-Verkauf, A2) werden zu einem Gesamt-Split summiert."""
    splits = [
        FxSplit(kapital_gv_chf=Decimal("100"), waehrungs_gv_chf=Decimal("10")),
        FxSplit(kapital_gv_chf=Decimal("-20"), waehrungs_gv_chf=Decimal("5")),
    ]
    gesamt = aggregiere_fx_split(splits)
    assert gesamt.kapital_gv_chf == Decimal("80")
    assert gesamt.waehrungs_gv_chf == Decimal("15")


def test_aggregiere_fx_split_leere_liste_ergibt_null_split() -> None:
    """@trace depot#AC6 — keine Lot-Splits (z. B. kein Fremdwährungs-Anteil)
    ergibt einen Null-Split, keinen Fehler."""
    gesamt = aggregiere_fx_split([])
    assert gesamt.kapital_gv_chf == Decimal("0")
    assert gesamt.waehrungs_gv_chf == Decimal("0")
