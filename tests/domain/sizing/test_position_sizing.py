"""Tests für den Position-Sizing-Kern (Story S-039).

Covers (sizing): AC1, AC2, AC3, AC4, AC7

`app.domain.sizing.position_sizing` deckt die Fractional-Kelly-Formel
(AC1, inkl. E1 "negatives Kelly -> kein Trade"), die Half-/Quarter-Kelly-
Fraktionen (AC2, inkl. Quarter-Kelly als Obergrenze), das harte Cap auf
das Risiko je Trade (AC3, inkl. Cap-Wirkung auf beide Sizing-Zweige) und
die Kelly-Scharfschaltungs-Schwelle (AC4, deckt A2, Fixed-Fractional-
Rückfall) ab. AC7 (Mikro-Betrachtung, keine Portfolio-/Korrelations-
prüfung) wird strukturell geprüft: die Kern-Funktionen nehmen keine
Portfolio-/Depot-Daten entgegen.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

import pytest

from app.contracts.sizing import KellyFraktionsKonfiguration
from app.domain.sizing.position_sizing import (
    QUARTER_KELLY_OBERGRENZE,
    berechne_kelly_fraktion,
    berechne_positionsgroesse,
    bestimme_konfigurierte_fraktion,
    ist_volatile_anlageklasse,
)

_AKTIEN_ID = 1
_KRYPTO_ID = 7


def test_ac1_kelly_formel_referenzrechnung() -> None:
    """@trace sizing#AC1 — f* = (b*p - q)/b: p=0.6, b=2 ->
    (2*0.6 - 0.4)/2 = 0.8/2 = 0.4."""
    f_stern = berechne_kelly_fraktion(p=Decimal("0.6"), b=Decimal("2"))
    assert f_stern == Decimal("0.4")


def test_ac1_negatives_kelly_kein_trade() -> None:
    """@trace sizing#AC1 — f* <= 0 (hier < 0) erzeugt keinen Trade
    (deckt E1: "negatives Kelly -> kein Trade"), unabhängig von der
    Scharfschaltung (AC4, hier scharf)."""
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.3"),
        b=Decimal("1"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=100,
    )
    assert ergebnis.verworfen == "kelly-negativ"
    assert ergebnis.risiko_pct == Decimal(0)


def test_ac1_null_kelly_kein_trade() -> None:
    """@trace sizing#AC1 — f* == 0 (Grenzfall, "<= 0") erzeugt ebenfalls
    keinen Trade."""
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.5"),
        b=Decimal("1"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=100,
    )
    assert ergebnis.verworfen == "kelly-negativ"
    assert ergebnis.risiko_pct == Decimal(0)


def test_ac1_ungueltige_wahrscheinlichkeit_wirft() -> None:
    """@trace sizing#AC1 — p ausserhalb [0, 1] ist keine gültige
    Win-Wahrscheinlichkeit."""
    with pytest.raises(ValueError):
        berechne_kelly_fraktion(p=Decimal("1.5"), b=Decimal("2"))


def test_ac1_ungueltiges_gewinn_verlust_verhaeltnis_wirft() -> None:
    """@trace sizing#AC1 — b <= 0 ist kein gültiges
    Gewinn/Verlust-Verhältnis (Formel sonst undefiniert/Division durch
    0)."""
    with pytest.raises(ValueError):
        berechne_kelly_fraktion(p=Decimal("0.6"), b=Decimal("0"))


def test_ac2_half_kelly_ist_standard_fraktion_nicht_volatiler_klassen() -> None:
    """@trace sizing#AC2 — Standard-Fraktion ist Half-Kelly (0.5) für
    nicht-volatile Anlageklassen (hier Aktien)."""
    fraktion = bestimme_konfigurierte_fraktion(_AKTIEN_ID)
    assert fraktion == Decimal("0.5")


def test_ac2_quarter_kelly_fuer_volatile_anlageklasse() -> None:
    """@trace sizing#AC2 — für volatile Anlageklassen (Krypto = 7,
    C-006) gilt Quarter-Kelly (0.25) statt Half-Kelly."""
    fraktion = bestimme_konfigurierte_fraktion(_KRYPTO_ID)
    assert fraktion == Decimal("0.25")
    assert ist_volatile_anlageklasse(_KRYPTO_ID) is True
    assert ist_volatile_anlageklasse(_AKTIEN_ID) is False


def test_ac2_quarter_kelly_wirkt_als_obergrenze() -> None:
    """@trace sizing#AC2 — "Quarter-Kelly wirkt zugleich als Obergrenze
    der eingesetzten Fraktion": eine (fehlerhaft) höher konfigurierte
    `fraktion_volatil` wird auf Quarter-Kelly gedeckelt."""
    konfiguration = KellyFraktionsKonfiguration(fraktion_volatil=Decimal("0.4"))
    fraktion = bestimme_konfigurierte_fraktion(_KRYPTO_ID, konfiguration)
    assert fraktion == QUARTER_KELLY_OBERGRENZE


def test_ac2_fraktionen_sind_konfigurierbar() -> None:
    """@trace sizing#AC2 — "Die Fraktionen sind konfigurierbar": ein
    abweichender `fraktion_standard`-Wert wird für nicht-volatile
    Klassen übernommen."""
    konfiguration = KellyFraktionsKonfiguration(fraktion_standard=Decimal("0.3"))
    fraktion = bestimme_konfigurierte_fraktion(_AKTIEN_ID, konfiguration)
    assert fraktion == Decimal("0.3")


def test_ac2_eingesetzte_kelly_fraktion_im_ergebnis_nach_ac2_multipliziert() -> None:
    """@trace sizing#AC1,AC2 — `eingesetzte_kelly_fraktion` im Ergebnis
    ist f* * AC2-Fraktion (hier Half-Kelly, vor dem AC3-Cap, Cap hoch
    genug um nicht zu greifen)."""
    konfiguration = KellyFraktionsKonfiguration(trade_cap_pct=Decimal("1"))
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=100,
        konfiguration=konfiguration,
    )
    # f* = 0.4 (siehe test_ac1_kelly_formel_referenzrechnung), Half-Kelly:
    # 0.4 * 0.5 = 0.2
    assert ergebnis.eingesetzte_kelly_fraktion == Decimal("0.2")
    assert ergebnis.risiko_pct == Decimal("0.2")
    assert ergebnis.verworfen is None


def test_ac3_hartes_cap_begrenzt_kelly_wenn_kelly_groesser() -> None:
    """@trace sizing#AC3 — Kelly schlägt (0.4 * 0.5 = 0.2) mehr vor als
    das konfigurierte Cap (Default 0.02) -> das Cap gewinnt ("die
    kleinere der beiden Grössen gewinnt")."""
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=100,
    )
    assert ergebnis.eingesetzte_kelly_fraktion == Decimal("0.2")
    assert ergebnis.risiko_pct == Decimal("0.02")


def test_ac3_cap_greift_nicht_wenn_kelly_kleiner_ist() -> None:
    """@trace sizing#AC3 — ist die AC2-Kelly-Grösse bereits kleiner als
    das Cap, gewinnt Kelly (Cap greift nicht zusätzlich verkleinernd)."""
    konfiguration = KellyFraktionsKonfiguration(trade_cap_pct=Decimal("0.5"))
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=100,
        konfiguration=konfiguration,
    )
    assert ergebnis.risiko_pct == Decimal("0.2")


def test_ac3_cap_ist_konfigurierbar() -> None:
    """@trace sizing#AC3 — "Default, provisorisch, konfigurierbar": ein
    abweichendes `trade_cap_pct` wird als Grenze übernommen."""
    konfiguration = KellyFraktionsKonfiguration(trade_cap_pct=Decimal("0.01"))
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=100,
        konfiguration=konfiguration,
    )
    assert ergebnis.risiko_pct == Decimal("0.01")


def test_ac3_cap_greift_auch_beim_fixed_fractional_rueckfall() -> None:
    """@trace sizing#AC3,AC4 — das harte Cap gilt "unabhängig davon, was
    Kelly vorschlägt"; konsistent dazu begrenzt es auch den
    konservativeren Fixed-Fractional-Rückfall (AC4/A2), falls dieser
    (fehlerhaft) über dem Cap konfiguriert wäre."""
    konfiguration = KellyFraktionsKonfiguration(
        fixed_fractional_pct=Decimal("0.05"), trade_cap_pct=Decimal("0.02")
    )
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=0,
        konfiguration=konfiguration,
    )
    assert ergebnis.kelly_scharf is False
    assert ergebnis.risiko_pct == Decimal("0.02")


def test_ac4_kelly_nicht_scharf_unter_der_mindestzahl_trades() -> None:
    """@trace sizing#AC4 — unterhalb der konfigurierten Mindestzahl
    abgeschlossener Sim-Trades (Default 100) bleibt Kelly ausgeschaltet
    (deckt A2): die konservative Fixed-Fractional-Regel greift, kein
    `eingesetzte_kelly_fraktion`-Wert."""
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.9"),
        b=Decimal("5"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=99,
    )
    assert ergebnis.kelly_scharf is False
    assert ergebnis.eingesetzte_kelly_fraktion is None
    assert ergebnis.verworfen is None
    # Fixed-Fractional-Default (0.01) < Cap-Default (0.02) -> Cap greift nicht.
    assert ergebnis.risiko_pct == Decimal("0.01")


def test_ac4_kelly_scharf_ab_der_mindestzahl_trades() -> None:
    """@trace sizing#AC4 — ab genau der konfigurierten Mindestzahl (hier
    Default 100) wird Kelly scharf geschaltet."""
    ergebnis = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=100,
    )
    assert ergebnis.kelly_scharf is True
    assert ergebnis.eingesetzte_kelly_fraktion is not None


def test_ac4_mindestzahl_trades_ist_konfigurierbar() -> None:
    """@trace sizing#AC4 — "Default, provisorisch, konfigurierbar": eine
    abweichende `kelly_min_trades`-Schwelle wird übernommen."""
    konfiguration = KellyFraktionsKonfiguration(kelly_min_trades=50)
    unter_schwelle = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=49,
        konfiguration=konfiguration,
    )
    ab_schwelle = berechne_positionsgroesse(
        titel_id="AAA",
        p=Decimal("0.6"),
        b=Decimal("2"),
        anlageklasse=_AKTIEN_ID,
        abgeschlossene_sim_trades=50,
        konfiguration=konfiguration,
    )
    assert unter_schwelle.kelly_scharf is False
    assert ab_schwelle.kelly_scharf is True


def test_ac7_kern_funktionen_nehmen_keine_portfolio_depot_daten_entgegen() -> None:
    """@trace sizing#AC7 — "Position-Sizing betrachtet nur den einzelnen
    Titel (Mikro); es nimmt keine Portfolio-/Korrelationsprüfung vor":
    strukturell geprüft, dass `berechne_positionsgroesse` keinen
    Portfolio-/Depot-/Korrelations-Parameter kennt (das nachgelagerte
    Risikomanagement, `app.db.depotstrategie`, ist dafür zuständig)."""
    parameter_namen = set(inspect.signature(berechne_positionsgroesse).parameters)
    verbotene_stichworte = ("portfolio", "depot", "korrelation", "positionen", "bestand")
    for name in parameter_namen:
        for stichwort in verbotene_stichworte:
            assert stichwort not in name.lower(), (
                f"Parameter {name!r} deutet auf Portfolio-/Depot-Zugriff hin (AC7-Verstoss)."
            )
