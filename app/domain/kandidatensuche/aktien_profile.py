"""Konkrete Aktien-Suchprofile: Small-/Mid-Cap & Large-Cap/ETF (Story
S-030, Spec `docs/specs/kandidatensuche.md` AC2/AC3/AC4).

Reiner Domain-Kern (architecture.md §4 P1/P3, Modul 3 "Suchkriteria"),
liefert die konkreten Profil-INHALTE (welche Namen in
`Suchprofil.pflicht_bedingungen`/`optionale_signale`/`schwellen` für Klasse
1 (Aktien) und Klasse 2 (ETFs) stehen) auf dem generischen
Suchprofil-Framework aus S-029 (`app.contracts.kandidatensuche`,
`app.domain.kandidatensuche.suchprofil`) — analog dem docstring-Auftrag von
`app.domain.kandidatensuche.kandidatensuche`: "Konkrete Profil-Registrierung
... sind Sache der Folge-Stories (S-030/S-031/S-057)". Dieses Modul
interpretiert die Signal-Namen selbst nicht fachlich (keine
Evaluations-/Scoring-Logik — das leistet die Analyse neuer Titel, siehe
Spec-Nicht-Ziele).

**Zwei Profil-Varianten für Klasse 1 (Aktien), ein Registry-Slot pro
Anlageklasse (S-029-Invariante):** AC2/AC3 (Small-/Mid-Cap) und AC4
(Large-Cap) beschreiben beide Klasse 1, brauchen aber unterschiedliche
Selektionsmechanismen (RVOL-Momentum vs. Fundamentaldaten) — die generische
`SuchprofilRegistry` aus S-029 (`dict[anlageklasse, Suchprofil]`) hält
strukturell genau EIN `Suchprofil` je Registry-Eintrag (AC1: "Ein Titel wird
nur gegen das Profil seiner Anlageklasse geprüft", keine Registry-Änderung
in dieser Story). Die Auswahl zwischen den beiden Klasse-1-Varianten
erfolgt daher über ein zusätzliches Marktkapitalisierungs-Segment
(`MarktkapitalisierungSegment`), das VOR dem eigentlichen
`SuchprofilRegistry`-Aufbau feststehen muss (`lade_aktien_suchprofil`/
`baue_aktien_suchprofil_registry`) — siehe Spec-Präzisierung in den
`Verträge` von `docs/specs/kandidatensuche.md`. ETFs (Klasse 2) teilen den
Large-Cap-Selektionsansatz (AC4 "Klassen 1, 2"), erhalten aber ein eigenes
`Suchprofil`-Objekt unter Klasse 2 (kein klassenübergreifendes Teilen einer
einzelnen Registry-Instanz, konsistent mit der AC1-Invariante)."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from app.contracts.kandidatensuche import Suchprofil, SuchprofilRegistry

#: Marktkapitalisierungs-Segment innerhalb der Anlageklasse 1 (Aktien) —
#: entscheidet, welche der beiden AC2/AC3- bzw. AC4-Suchprofil-Varianten für
#: Klasse 1 in die `SuchprofilRegistry` aufgenommen wird.
MarktkapitalisierungSegment = Literal["small_mid", "large_cap"]

#: AC2: RVOL-Schwelle (>2x Durchschnitt) als konfigurierbarer, provisorischer
#: Default (AC10) — Key konsistent mit dem Muster von
#: `app.domain.kandidatensuche.suchprofil`/`SuchprofilOverride.schwellen`.
AKTIEN_SMALL_MID_RVOL_SCHWELLEN_KEY = "rvol_faktor"

#: AC2/AC3: Profil Aktien Small-/Mid-Cap (Klasse 1).
#:
#: `pflicht_bedingungen` — AC2 "RVOL > 2x ... ist non-negotiable
#: (Pflichtbedingung)" UND AC3 "RVOL und Katalysator/News-Signal müssen als
#: Kombination (UND) erfüllt sein" (deckt E1): beide Namen stehen deshalb
#: gemeinsam in `pflicht_bedingungen` — laut Main-Success-Scenario Schritt 5
#: ("Kandidaten, die ALLE Pflicht-Bedingungen ... erfüllen") ist die Liste
#: bereits UND-verknüpft, ein Titel mit RVOL aber ohne Katalysator erfüllt
#: das Profil NICHT (AC3/E1).
#: `optionale_signale` — AC2 "zusätzlich ... berücksichtigt": Kurs-Änderung
#: am Tag, Gap-up, Low Float, RSI, Breakout über Widerstand.
AKTIEN_SMALL_MID_PROFIL = Suchprofil(
    anlageklasse=1,
    pflicht_bedingungen=["rvol_ueber_2x", "katalysator_vorhanden"],
    optionale_signale=[
        "kursaenderung_tag",
        "gap_up",
        "low_float",
        "rsi",
        "breakout_widerstand",
    ],
    schwellen={AKTIEN_SMALL_MID_RVOL_SCHWELLEN_KEY: Decimal("2")},
)

#: AC4: gemeinsame Signal-Liste "Aktien Large-Cap / ETFs" (Klassen 1, 2) —
#: Fundamentaldaten, Analysten-Revisionen (Earnings Revisions), Fund Flows.
#: Reddit/Social-Sentiment ist bewusst NICHT enthalten (AC4: "wird hier
#: NICHT als Selektor verwendet") — siehe Edge-Case "Reddit-Signal für
#: Large-Cap/ETF vorhanden → wird ignoriert (kein Selektor, AC4)".
_LARGE_CAP_SIGNALE = ["fundamentaldaten", "analysten_revisionen", "fund_flows"]

#: AC4: Profil Aktien Large-Cap (Klasse 1) — eigenes `Suchprofil`-Objekt
#: (kein Teilen einer Instanz über Klassen hinweg, AC1-Invariante).
AKTIEN_LARGE_CAP_PROFIL = Suchprofil(
    anlageklasse=1,
    optionale_signale=list(_LARGE_CAP_SIGNALE),
)

#: AC4: Profil ETFs (Klasse 2) — identischer Selektionsansatz wie
#: `AKTIEN_LARGE_CAP_PROFIL` (AC4 "Klassen 1, 2"), eigenes `Suchprofil`
#: unter Klasse 2.
ETF_PROFIL = Suchprofil(
    anlageklasse=2,
    optionale_signale=list(_LARGE_CAP_SIGNALE),
)


def lade_aktien_suchprofil(segment: MarktkapitalisierungSegment) -> Suchprofil:
    """Liefert die für `segment` zuständige Klasse-1-Suchprofil-Variante:
    `"small_mid"` → AC2/AC3-Profil (RVOL+Katalysator non-negotiable),
    `"large_cap"` → AC4-Profil (Fundamentaldaten/Revisionen/Flows, kein
    Reddit-Selektor)."""
    if segment == "small_mid":
        return AKTIEN_SMALL_MID_PROFIL
    return AKTIEN_LARGE_CAP_PROFIL


def baue_aktien_suchprofil_registry(
    aktien_segment: MarktkapitalisierungSegment,
) -> SuchprofilRegistry:
    """Baut eine `SuchprofilRegistry` (S-029) mit dem für `aktien_segment`
    gewählten Klasse-1-Profil PLUS dem Klasse-2-ETF-Profil — kompatibel mit
    `app.domain.kandidatensuche.kandidatensuche.erstelle_filterkriterien`
    (AC1/AC6/AC9/AC10), ohne dass die generische Registry-Struktur selbst
    verändert wird."""
    return {1: lade_aktien_suchprofil(aktien_segment), 2: ETF_PROFIL}


__all__ = [
    "AKTIEN_LARGE_CAP_PROFIL",
    "AKTIEN_SMALL_MID_PROFIL",
    "AKTIEN_SMALL_MID_RVOL_SCHWELLEN_KEY",
    "ETF_PROFIL",
    "MarktkapitalisierungSegment",
    "baue_aktien_suchprofil_registry",
    "lade_aktien_suchprofil",
]
