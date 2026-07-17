"""Tests für das konkrete Krypto-Suchprofil & die MVP-Profilabdeckung
(Story S-031).

Covers (kandidatensuche): AC5, AC11

`app.domain.kandidatensuche.krypto_profile` liefert die AC5-Profil-Inhalte
(Klasse 7 Krypto, RVOL non-negotiable + Social-/On-Chain-/Funding-Rate-
Signale) auf dem generischen Suchprofil-Framework aus S-029 sowie
(`baue_mvp_suchprofil_registry`) die AC11-MVP-Registry (Aktien/ETF/Krypto),
ohne die S-030-Aktien-/ETF-Profile zu verändern."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.anlageklassen_config import ToggleZustand
from app.contracts.kandidatensuche import QuerschnittFilter, VolatilitaetsFenster
from app.domain.kandidatensuche.aktien_profile import (
    AKTIEN_LARGE_CAP_PROFIL,
    AKTIEN_SMALL_MID_PROFIL,
    ETF_PROFIL,
)
from app.domain.kandidatensuche.kandidatensuche import erstelle_filterkriterien
from app.domain.kandidatensuche.krypto_profile import (
    KRYPTO_PROFIL,
    KRYPTO_RVOL_SCHWELLEN_KEY,
    baue_mvp_suchprofil_registry,
)


def test_krypto_profil_gehoert_zu_klasse_7() -> None:
    """@trace kandidatensuche#AC5 — Krypto-Profil ist Klasse 7 zugeordnet."""
    assert KRYPTO_PROFIL.anlageklasse == 7


def test_krypto_profil_rvol_ist_pflichtbedingung() -> None:
    """@trace kandidatensuche#AC5 — relatives Volumen > 2x Durchschnitt ist
    Pflichtbedingung, nicht nur ein zusätzlich berücksichtigtes Signal."""
    assert "rvol_ueber_2x" in KRYPTO_PROFIL.pflicht_bedingungen


def test_krypto_profil_rvol_schwelle_ist_2x_default() -> None:
    """@trace kandidatensuche#AC5 — die RVOL-Schwelle ist ein konfigurierbarer
    Default von 2x (provisorisch, AC10-Muster)."""
    schwelle = KRYPTO_PROFIL.schwellen[KRYPTO_RVOL_SCHWELLEN_KEY]
    assert schwelle == Decimal("2")


def test_krypto_profil_beruecksichtigt_social_on_chain_und_funding_signale() -> None:
    """@trace kandidatensuche#AC5 — Social-/Kommentar-Volumen, On-Chain-Signale
    (Whale-Bewegungen, Exchange-Flows, Smart-Money) und Funding-Rates werden
    als optionale Signale berücksichtigt."""
    optionale = set(KRYPTO_PROFIL.optionale_signale)
    assert optionale == {
        "social_volumen",
        "on_chain_whale_bewegungen",
        "on_chain_exchange_flows",
        "on_chain_smart_money",
        "funding_rate",
    }


def test_krypto_profil_rvol_ist_keine_optionale_signal() -> None:
    """@trace kandidatensuche#AC5 — die RVOL-Pflichtbedingung ist
    ausschliesslich in `pflicht_bedingungen` geführt, nicht (auch) als
    optionales Signal."""
    assert "rvol_ueber_2x" not in KRYPTO_PROFIL.optionale_signale


def test_krypto_profil_wirkt_durch_die_s029_fassade() -> None:
    """@trace kandidatensuche#AC5 — `KRYPTO_PROFIL` ist ohne Änderung an der
    S-029-Fassade
    (`app.domain.kandidatensuche.kandidatensuche.erstelle_filterkriterien`)
    nutzbar: Klasse 7, aktiv, liefert Filterkriterien mit den AC5-Signalen
    und der RVOL-Schwelle."""
    querschnitt_filter = QuerschnittFilter(
        liquiditaets_mindestschwelle=Decimal("1"),
        volatilitaets_fenster=VolatilitaetsFenster(min=Decimal("0"), max=Decimal("100")),
    )

    kriterien = erstelle_filterkriterien(
        registry={7: KRYPTO_PROFIL},
        anlageklasse=7,
        zustand=ToggleZustand(aktiv=True),
        querschnitt_filter=querschnitt_filter,
    )

    assert kriterien is not None
    assert "rvol_ueber_2x" in kriterien.signale
    assert "funding_rate" in kriterien.signale
    assert kriterien.schwellen[KRYPTO_RVOL_SCHWELLEN_KEY] == Decimal("2")


def test_mvp_registry_enthaelt_aktien_etf_und_krypto_klasse_1_2_7() -> None:
    """@trace kandidatensuche#AC11 — die MVP-Registry enthält mindestens die
    Profile für Aktien (Klasse 1), ETFs (Klasse 2) und Krypto (Klasse 7)."""
    registry = baue_mvp_suchprofil_registry("small_mid")

    assert registry[1] is AKTIEN_SMALL_MID_PROFIL
    assert registry[2] is ETF_PROFIL
    assert registry[7] is KRYPTO_PROFIL


def test_mvp_registry_large_cap_segment() -> None:
    """@trace kandidatensuche#AC11 — die MVP-Registry funktioniert für beide
    Aktien-Marktkapitalisierungs-Segmente (S-030) unverändert mit dem
    Krypto-Profil zusammen."""
    registry = baue_mvp_suchprofil_registry("large_cap")

    assert registry[1] is AKTIEN_LARGE_CAP_PROFIL
    assert registry[2] is ETF_PROFIL
    assert registry[7] is KRYPTO_PROFIL


def test_mvp_registry_veraendert_bestehende_aktien_und_etf_profile_nicht() -> None:
    """@trace kandidatensuche#AC11 — "optional ergänzbar, ohne die
    bestehenden Profile zu verändern": das Krypto-Profil hinzuzufügen lässt
    die Objekt-Identität der Aktien-/ETF-Profile unangetastet, und ein
    zweiter Aufruf liefert ein unabhängiges Dict (keine gemeinsame
    veränderbare Registry-Instanz)."""
    erste_registry = baue_mvp_suchprofil_registry("small_mid")
    zweite_registry = baue_mvp_suchprofil_registry("small_mid")

    assert erste_registry is not zweite_registry
    assert erste_registry[1] is zweite_registry[1]
    assert AKTIEN_SMALL_MID_PROFIL.anlageklasse == 1
    assert set(AKTIEN_SMALL_MID_PROFIL.pflicht_bedingungen) == {
        "rvol_ueber_2x",
        "katalysator_vorhanden",
    }


def test_mvp_registry_wirkt_durch_die_s029_fassade_fuer_krypto() -> None:
    """@trace kandidatensuche#AC5,AC11 — die MVP-Registry ist ohne Änderung
    an der S-029-Fassade für Klasse 7 nutzbar."""
    registry = baue_mvp_suchprofil_registry("small_mid")
    querschnitt_filter = QuerschnittFilter(
        liquiditaets_mindestschwelle=Decimal("1"),
        volatilitaets_fenster=VolatilitaetsFenster(min=Decimal("0"), max=Decimal("100")),
    )

    kriterien = erstelle_filterkriterien(
        registry=registry,
        anlageklasse=7,
        zustand=ToggleZustand(aktiv=True),
        querschnitt_filter=querschnitt_filter,
    )

    assert kriterien is not None
    assert kriterien.anlageklasse == 7
    assert "on_chain_smart_money" in kriterien.signale
