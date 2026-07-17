"""Tests für die konkreten Aktien-Suchprofile (Story S-030).

Covers (kandidatensuche): AC2, AC3, AC4

`app.domain.kandidatensuche.aktien_profile` liefert die AC2/AC3-Profil-
Inhalte (Small-/Mid-Cap, RVOL non-negotiable + Katalysator-UND-Kombination)
und die AC4-Profil-Inhalte (Large-Cap/ETF, Fundamentaldaten/Revisionen/
Flows, kein Reddit-Selektor) auf dem generischen Suchprofil-Framework aus
S-029."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.anlageklassen_config import ToggleZustand
from app.contracts.kandidatensuche import QuerschnittFilter, VolatilitaetsFenster
from app.domain.kandidatensuche.aktien_profile import (
    AKTIEN_LARGE_CAP_PROFIL,
    AKTIEN_SMALL_MID_PROFIL,
    AKTIEN_SMALL_MID_RVOL_SCHWELLEN_KEY,
    ETF_PROFIL,
    baue_aktien_suchprofil_registry,
    lade_aktien_suchprofil,
)
from app.domain.kandidatensuche.kandidatensuche import erstelle_filterkriterien

REDDIT_SIGNALNAMEN = {"reddit", "reddit_sentiment", "social_sentiment"}


def test_small_mid_profil_gehoert_zu_klasse_1() -> None:
    """@trace kandidatensuche#AC2 — Small-/Mid-Cap-Profil ist Klasse 1
    (Aktien) zugeordnet."""
    assert AKTIEN_SMALL_MID_PROFIL.anlageklasse == 1


def test_small_mid_profil_rvol_ist_pflichtbedingung() -> None:
    """@trace kandidatensuche#AC2 — RVOL > 2x Durchschnitt ist non-negotiable
    (Pflichtbedingung), nicht nur ein zusätzlich berücksichtigtes Signal."""
    assert "rvol_ueber_2x" in AKTIEN_SMALL_MID_PROFIL.pflicht_bedingungen


def test_small_mid_profil_rvol_schwelle_ist_2x_default() -> None:
    """@trace kandidatensuche#AC2 — die RVOL-Schwelle ist ein konfigurierbarer
    Default von 2x (provisorisch, AC10-Muster)."""
    schwelle = AKTIEN_SMALL_MID_PROFIL.schwellen[AKTIEN_SMALL_MID_RVOL_SCHWELLEN_KEY]
    assert schwelle == Decimal("2")


def test_small_mid_profil_beruecksichtigt_zusaetzliche_signale() -> None:
    """@trace kandidatensuche#AC2 — zusätzlich zur RVOL-Pflichtbedingung
    werden Kurs-Änderung am Tag/Gap-up, Low Float, RSI und Breakout über
    Widerstand als optionale Signale berücksichtigt."""
    optionale = set(AKTIEN_SMALL_MID_PROFIL.optionale_signale)
    assert optionale == {
        "kursaenderung_tag",
        "gap_up",
        "low_float",
        "rsi",
        "breakout_widerstand",
    }


def test_small_mid_profil_rvol_und_katalysator_sind_beide_pflicht() -> None:
    """@trace kandidatensuche#AC3 — RVOL UND Katalysator/News-Signal müssen
    als Kombination erfüllt sein: beide stehen in `pflicht_bedingungen`
    (Main-Success-Scenario Schritt 5: "ALLE Pflicht-Bedingungen" — die Liste
    ist bereits UND-verknüpft)."""
    pflicht = AKTIEN_SMALL_MID_PROFIL.pflicht_bedingungen
    assert "rvol_ueber_2x" in pflicht
    assert "katalysator_vorhanden" in pflicht


def test_small_mid_profil_katalysator_ist_keine_optionale_signal() -> None:
    """@trace kandidatensuche#AC3 — deckt E1: ein Titel mit hohem RVOL aber
    ohne Katalysator erfüllt das Profil NICHT — der Katalysator darf deshalb
    nicht (auch) als bloss optionales Signal geführt sein, sondern
    ausschliesslich als Pflichtbedingung."""
    assert "katalysator_vorhanden" not in AKTIEN_SMALL_MID_PROFIL.optionale_signale


def test_large_cap_profil_gehoert_zu_klasse_1() -> None:
    """@trace kandidatensuche#AC4 — Large-Cap-Profil ist (auch) Klasse 1
    (Aktien) zugeordnet."""
    assert AKTIEN_LARGE_CAP_PROFIL.anlageklasse == 1


def test_etf_profil_gehoert_zu_klasse_2() -> None:
    """@trace kandidatensuche#AC4 — ETF-Profil ist Klasse 2 zugeordnet."""
    assert ETF_PROFIL.anlageklasse == 2


def test_large_cap_und_etf_profil_nutzen_fundamentaldaten_revisionen_flows() -> None:
    """@trace kandidatensuche#AC4 — Selektion über Fundamentaldaten,
    Analysten-Revisionen (Earnings Revisions) und Fund Flows, identisch für
    Klasse 1 (Large-Cap) und Klasse 2 (ETFs)."""
    erwartete_signale = {"fundamentaldaten", "analysten_revisionen", "fund_flows"}
    assert set(AKTIEN_LARGE_CAP_PROFIL.optionale_signale) == erwartete_signale
    assert set(ETF_PROFIL.optionale_signale) == erwartete_signale


def test_large_cap_und_etf_profil_haben_keinen_reddit_selektor() -> None:
    """@trace kandidatensuche#AC4 — deckt den Edge-Case "Reddit-Signal für
    Large-Cap/ETF vorhanden → wird ignoriert (kein Selektor)": kein
    Reddit-/Social-Sentiment-Signalname in Pflicht- oder optionalen Signalen
    von Large-Cap- oder ETF-Profil."""
    for profil in (AKTIEN_LARGE_CAP_PROFIL, ETF_PROFIL):
        alle_signale = set(profil.pflicht_bedingungen) | set(profil.optionale_signale)
        assert alle_signale.isdisjoint(REDDIT_SIGNALNAMEN)


def test_lade_aktien_suchprofil_small_mid() -> None:
    """@trace kandidatensuche#AC2,AC3 — Segment "small_mid" liefert das
    AC2/AC3-Profil."""
    assert lade_aktien_suchprofil("small_mid") is AKTIEN_SMALL_MID_PROFIL


def test_lade_aktien_suchprofil_large_cap() -> None:
    """@trace kandidatensuche#AC4 — Segment "large_cap" liefert das
    AC4-Profil."""
    assert lade_aktien_suchprofil("large_cap") is AKTIEN_LARGE_CAP_PROFIL


def test_baue_aktien_suchprofil_registry_small_mid() -> None:
    """@trace kandidatensuche#AC2,AC4 — die gebaute Registry enthält für das
    Segment "small_mid" das AC2/AC3-Profil unter Klasse 1 UND unverändert
    das AC4-ETF-Profil unter Klasse 2 (kompatibel mit der S-029
    SuchprofilRegistry, dict[anlageklasse, Suchprofil])."""
    registry = baue_aktien_suchprofil_registry("small_mid")

    assert registry[1] is AKTIEN_SMALL_MID_PROFIL
    assert registry[2] is ETF_PROFIL


def test_baue_aktien_suchprofil_registry_large_cap() -> None:
    """@trace kandidatensuche#AC4 — für Segment "large_cap" enthält die
    Registry das AC4-Profil unter Klasse 1 (Large-Cap) UND das AC4-ETF-Profil
    unter Klasse 2."""
    registry = baue_aktien_suchprofil_registry("large_cap")

    assert registry[1] is AKTIEN_LARGE_CAP_PROFIL
    assert registry[2] is ETF_PROFIL


def test_small_mid_profil_wirkt_durch_die_s029_fassade() -> None:
    """@trace kandidatensuche#AC2,AC3 — die gebaute Registry ist ohne
    Änderung an der S-029-Fassade
    (`app.domain.kandidatensuche.kandidatensuche.erstelle_filterkriterien`)
    nutzbar: Klasse 1, aktiv, liefert Filterkriterien mit den
    AC2/AC3-Signalen und der RVOL-Schwelle."""
    registry = baue_aktien_suchprofil_registry("small_mid")
    querschnitt_filter = QuerschnittFilter(
        liquiditaets_mindestschwelle=Decimal("1"),
        volatilitaets_fenster=VolatilitaetsFenster(min=Decimal("0"), max=Decimal("100")),
    )

    kriterien = erstelle_filterkriterien(
        registry=registry,
        anlageklasse=1,
        zustand=ToggleZustand(aktiv=True),
        querschnitt_filter=querschnitt_filter,
    )

    assert kriterien is not None
    assert "rvol_ueber_2x" in kriterien.signale
    assert "katalysator_vorhanden" in kriterien.signale
    assert kriterien.schwellen[AKTIEN_SMALL_MID_RVOL_SCHWELLEN_KEY] == Decimal("2")
