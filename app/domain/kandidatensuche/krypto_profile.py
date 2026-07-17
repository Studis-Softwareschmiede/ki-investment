"""Konkretes Krypto-Suchprofil & MVP-Profilabdeckung (Story S-031, Spec
`docs/specs/kandidatensuche.md` AC5/AC11).

Reiner Domain-Kern (architecture.md §4 P1/P3, Modul 3 "Suchkriteria"),
liefert die konkreten Profil-INHALTE für Klasse 7 (Krypto) auf dem
generischen Suchprofil-Framework aus S-029
(`app.contracts.kandidatensuche`, `app.domain.kandidatensuche.suchprofil`)
— analog dem Muster von `app.domain.kandidatensuche.aktien_profile`
(S-030). Dieses Modul interpretiert die Signal-Namen selbst nicht
fachlich (keine Evaluations-/Scoring-Logik — das leistet die Analyse
neuer Titel, siehe Spec-Nicht-Ziele).

**AC11 (MVP-Profilabdeckung):** `baue_mvp_suchprofil_registry` vereinigt
das S-030-Aktien-/ETF-Profilpaar (Klassen 1, 2) mit `KRYPTO_PROFIL`
(Klasse 7) zu einer vollständigen MVP-`SuchprofilRegistry` — ohne die
bestehenden Aktien-/ETF-Profile zu verändern (`Suchprofil` ist `frozen`,
`baue_aktien_suchprofil_registry` liefert bei jedem Aufruf ein frisches
Dict). Weitere Klassen (Obligationen, FX, Rohstoffe, aktive Fonds,
Infrastruktur, Derivate) sind optional ergänzbar, indem eine Folge-Story
zusätzliche Einträge in die von hier zurückgegebene Registry aufnimmt,
ohne Klasse 1/2/7 anzufassen (deckt AC11 "sind optional ergänzbar, ohne
die bestehenden Profile zu verändern")."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.kandidatensuche import Suchprofil, SuchprofilRegistry
from app.domain.kandidatensuche.aktien_profile import (
    MarktkapitalisierungSegment,
    baue_aktien_suchprofil_registry,
)

#: AC5: RVOL-Schwelle (>2x Durchschnitt) als konfigurierbarer, provisorischer
#: Default (AC10) — Key konsistent mit dem Muster von
#: `app.domain.kandidatensuche.aktien_profile.AKTIEN_SMALL_MID_RVOL_SCHWELLEN_KEY`.
KRYPTO_RVOL_SCHWELLEN_KEY = "rvol_faktor"

#: AC5: Profil Krypto (Klasse 7).
#:
#: `pflicht_bedingungen` — AC5 "relatives Volumen > 2x Durchschnitt als
#: Pflichtbedingung": analog AC2 (Aktien Small/Mid) als non-negotiable
#: Bedingung geführt, nicht nur als optionales Signal.
#: `optionale_signale` — AC5 "Social-/Kommentar-Volumen, On-Chain-Signale
#: (Whale-Bewegungen, Exchange-Flows, Smart-Money) und Funding-Rates".
KRYPTO_PROFIL = Suchprofil(
    anlageklasse=7,
    pflicht_bedingungen=["rvol_ueber_2x"],
    optionale_signale=[
        "social_volumen",
        "on_chain_whale_bewegungen",
        "on_chain_exchange_flows",
        "on_chain_smart_money",
        "funding_rate",
    ],
    schwellen={KRYPTO_RVOL_SCHWELLEN_KEY: Decimal("2")},
)


def baue_mvp_suchprofil_registry(
    aktien_segment: MarktkapitalisierungSegment,
) -> SuchprofilRegistry:
    """AC11: baut die vollständige MVP-`SuchprofilRegistry` — das für
    `aktien_segment` gewählte Klasse-1-Aktien-Profil (S-030) PLUS das
    Klasse-2-ETF-Profil (S-030) PLUS `KRYPTO_PROFIL` unter Klasse 7 —, ohne
    eines der bestehenden Aktien-/ETF-Profile zu verändern
    (`baue_aktien_suchprofil_registry` liefert bereits ein frisches Dict,
    das hier lediglich um den Klasse-7-Eintrag erweitert wird)."""
    registry = baue_aktien_suchprofil_registry(aktien_segment)
    registry[7] = KRYPTO_PROFIL
    return registry


__all__ = [
    "KRYPTO_PROFIL",
    "KRYPTO_RVOL_SCHWELLEN_KEY",
    "baue_mvp_suchprofil_registry",
]
