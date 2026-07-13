"""Modul-Verträge Kandidatensuche — Suchprofil-Framework, Querschnitt-Filter
& Toggle-Disziplin (Story S-029, Spec `docs/specs/kandidatensuche.md`,
Modul 3 "Suchkriteria", architecture.md §3 — Layer `domain`).

Deckt exakt die dieser Story zugewiesenen Acceptance-Kriterien (AC1, AC6,
AC7, AC9, AC10) — NICHT die konkreten Profil-INHALTE (RVOL-Schwelle,
Katalysator-Pflicht, Fundamentaldaten-Selektoren etc., AC2-AC5/AC11), die
eigene Folge-Stories (S-030/S-031/S-057) liefern. Diese Contracts bilden
die generische STRUKTUR eines Suchprofils ab; welche konkreten Einträge
`pflicht_bedingungen`/`optionale_signale`/`schwellen` für eine Klasse
tragen, entscheidet die registrierende Folge-Story — dieses Modul
interpretiert sie nicht fachlich, es transportiert sie nur.

- `Suchprofil` — je Anlageklasse (Verträge "Suchprofil (je Anlageklasse)").
- `SuchprofilRegistry` — `dict[anlageklasse, Suchprofil]`; die einzige
  Nachschlagestruktur, die `app.domain.kandidatensuche.suchprofil.
  lade_suchprofil` (AC1) befragt — es existiert bewusst KEIN Fallback-/
  Default-Profil, das mehrere Klassen teilen würde (kein "einheitlicher
  Filter über alle Klassen").
- `SuchprofilOverride`/`SuchprofilOverrides` — Konfig-Override je Klasse
  (AC7 `modus`, AC10 `schwellen`), ohne Codeänderung aus
  `app.config.Settings` befüllbar (Muster von `TOLERANZ_CONFIG`, S-013).
- `QuerschnittFilter`/`VolatilitaetsFenster` — Querschnitt-Filter (AC6),
  auf jedes Profil/jeden Kandidaten angewandt.
- `Filterkriterien` — Output an die Datenquellen-Abfrage (Verträge "Output
  an Datenquellen-Abfrage", Main-Success-Scenario Schritt 4).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Suchmodus (AC7): eventbasiert ist der bevorzugte, provisorische Default;
#: periodisch ist der Fallback, wenn der eventbasierte Scanner für eine
#: Klasse nicht verfügbar/nicht sinnvoll ist (deckt A2).
Suchmodus = Literal["eventbasiert", "periodisch"]


class Suchprofil(BaseModel):
    """Suchprofil je Anlageklasse (Verträge "Suchprofil (je Anlageklasse)").

    `pflicht_bedingungen`/`optionale_signale` sind reine Namenslisten —
    Inhalt/Bedeutung je Klasse ist Sache der registrierenden Folge-Story
    (AC2-AC5); dieses Modul interpretiert sie nicht fachlich (AC1-Rahmen)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anlageklasse: int = Field(ge=1, le=11)
    pflicht_bedingungen: list[str] = Field(default_factory=list)
    optionale_signale: list[str] = Field(default_factory=list)
    schwellen: dict[str, Decimal] = Field(default_factory=dict)
    modus: Suchmodus = "eventbasiert"


class SuchprofilOverride(BaseModel):
    """Konfig-Override eines einzelnen Suchprofils (AC7 `modus`, AC10
    `schwellen`) — ohne Codeänderung aus `app.config.Settings` befüllbar.

    `schwellen` MERGED in die bestehenden Schwellen des Profils (nur die
    genannten Keys werden ersetzt, alle anderen bleiben unverändert) — im
    Unterschied zum Full-Replace-Muster von `TOLERANZ_CONFIG` (S-013), weil
    ein Override i.d.R. nur einen einzelnen kalibrierten Schwellenwert
    anpasst, nicht das gesamte Profil neu spezifiziert."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    modus: Suchmodus | None = None
    schwellen: dict[str, Decimal] = Field(default_factory=dict)


#: Registry-Typ: die EINZIGE Nachschlagestruktur für AC1 ("Ein Titel wird
#: nur gegen das Profil seiner Anlageklasse geprüft") — kein Default-/
#: Fallback-Wert für unbekannte Klassen.
SuchprofilRegistry = dict[int, Suchprofil]

#: Override-Registry, korrespondiert mit
#: `app.config.Settings.kandidatensuche_profil_overrides`.
SuchprofilOverrides = dict[int, SuchprofilOverride]


class VolatilitaetsFenster(BaseModel):
    """Volatilitäts-Fenster des Querschnitt-Filters (AC6): `min`/`max` sind
    inklusive Grenzen ("nicht zu tot, nicht zu wild")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min: Decimal
    max: Decimal


class QuerschnittFilter(BaseModel):
    """Querschnitt-Filter (AC6) — auf jedes Suchprofil/jeden Kandidaten
    angewandt, unabhängig von dessen Anlageklasse. Beide Schwellen sind
    konfigurierbar (AC10, `app.config.Settings`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    liquiditaets_mindestschwelle: Decimal
    volatilitaets_fenster: VolatilitaetsFenster


#: Schwellen-Keys, mit denen `QuerschnittFilter` in `Filterkriterien.schwellen`
#: eingemischt wird (AC6, Verträge "Output an Datenquellen-Abfrage") — als
#: Konstanten, damit Profil-`schwellen` diese Namen nicht versehentlich
#: kollisionsfrei überschreiben können, ohne dass es dokumentiert ist.
QUERSCHNITT_SCHWELLEN_KEY_LIQUIDITAET = "liquiditaets_mindestschwelle"
QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MIN = "volatilitaets_fenster_min"
QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MAX = "volatilitaets_fenster_max"


class Filterkriterien(BaseModel):
    """Output an die Datenquellen-Abfrage (Verträge "Output an
    Datenquellen-Abfrage"): `{ anlageklasse, signale, schwellen }`.

    `signale` = `pflicht_bedingungen + optionale_signale` des Profils
    (welche Signal-Typen für diese Klasse relevant sind); `schwellen` =
    Profil-Schwellen (inkl. AC10-Overrides) VEREINIGT mit den zwei
    Querschnitt-Filter-Schwellen (AC6, unter den
    `QUERSCHNITT_SCHWELLEN_KEY_*`-Keys — Profil-Schwellen haben bei einer
    Namenskollision Vorrang)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anlageklasse: int = Field(ge=1, le=11)
    signale: list[str]
    schwellen: dict[str, Decimal]


__all__ = [
    "QUERSCHNITT_SCHWELLEN_KEY_LIQUIDITAET",
    "QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MAX",
    "QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MIN",
    "Filterkriterien",
    "QuerschnittFilter",
    "Suchmodus",
    "Suchprofil",
    "SuchprofilOverride",
    "SuchprofilOverrides",
    "SuchprofilRegistry",
    "VolatilitaetsFenster",
]
