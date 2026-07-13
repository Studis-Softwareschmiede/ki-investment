"""Querschnitt-Filter der Kandidatensuche (Story S-029, Spec
`docs/specs/kandidatensuche.md` AC6).

Reiner Domain-Kern. Zwei Bausteine:

- `erfuellt_querschnitt_filter` — die Ausschluss-Entscheidung (AC6: "ein
  Titel, der die Liquiditäts-Mindestschwelle unterschreitet oder ausserhalb
  des Volatilitäts-Fensters liegt, wird ausgeschlossen"), anwendbar auf ein
  bereits von der geteilten Datenquellen-Abfrage geliefertes `SignalBuendel`
  (`app.contracts.dateneingang.SignalBuendel`, S-021/`hole_signal_buendel`).
- `baue_filterkriterien` — vereinigt ein Suchprofil (AC1) MIT dem
  Querschnitt-Filter (AC6) zum Output-Vertrag `Filterkriterien`
  ("an die Datenquellen-Abfrage übergeben", Main-Success-Scenario
  Schritt 4).
"""

from __future__ import annotations

from app.contracts.dateneingang import SignalBuendel
from app.contracts.kandidatensuche import (
    QUERSCHNITT_SCHWELLEN_KEY_LIQUIDITAET,
    QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MAX,
    QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MIN,
    Filterkriterien,
    QuerschnittFilter,
    Suchprofil,
)


def erfuellt_querschnitt_filter(signal_buendel: SignalBuendel, filter_: QuerschnittFilter) -> bool:
    """AC6: `True`, wenn `signal_buendel.liquiditaet` die Mindestschwelle
    erreicht (`>=`) UND `signal_buendel.volatilitaet` innerhalb des
    Volatilitäts-Fensters liegt (inklusive Grenzen).

    Fehlt einer der beiden Werte (keine aggregierbare Quelle — siehe
    `app.orchestration.datasource_query`-Nicht-Ziel "kein Wert wird
    geschätzt"), gilt der Kandidat als NICHT erfüllt (Fail-Closed, analog
    dem dateneingang-AC2-Prinzip "fehlend kennzeichnen statt schätzen" —
    siehe `docs/specs/kandidatensuche.md` Edge-Cases-Präzisierung)."""
    if signal_buendel.liquiditaet is None or signal_buendel.volatilitaet is None:
        return False
    if signal_buendel.liquiditaet < filter_.liquiditaets_mindestschwelle:
        return False
    fenster = filter_.volatilitaets_fenster
    return fenster.min <= signal_buendel.volatilitaet <= fenster.max


def baue_filterkriterien(profil: Suchprofil, filter_: QuerschnittFilter) -> Filterkriterien:
    """Main-Success-Scenario Schritt 4: "Aus Profil + Querschnitt-Filtern
    werden Filterkriterien gebildet und an die Datenquellen-Abfrage
    übergeben."

    `signale` = `pflicht_bedingungen + optionale_signale` des Profils
    (welche Signal-Typen für diese Klasse relevant sind); `schwellen` =
    die zwei Querschnitt-Filter-Schwellen (AC6, unter den
    `QUERSCHNITT_SCHWELLEN_KEY_*`-Keys) VEREINIGT mit den Profil-Schwellen
    (inkl. etwaiger AC10-Overrides) — Profil-Schwellen haben bei einer
    Namenskollision Vorrang."""
    schwellen = {
        QUERSCHNITT_SCHWELLEN_KEY_LIQUIDITAET: filter_.liquiditaets_mindestschwelle,
        QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MIN: filter_.volatilitaets_fenster.min,
        QUERSCHNITT_SCHWELLEN_KEY_VOLATILITAET_MAX: filter_.volatilitaets_fenster.max,
    }
    schwellen.update(profil.schwellen)
    return Filterkriterien(
        anlageklasse=profil.anlageklasse,
        signale=[*profil.pflicht_bedingungen, *profil.optionale_signale],
        schwellen=schwellen,
    )


__all__ = ["baue_filterkriterien", "erfuellt_querschnitt_filter"]
