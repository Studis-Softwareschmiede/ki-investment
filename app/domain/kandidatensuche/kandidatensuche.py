"""Einstiegspunkt Kandidatensuche-Framework (Story S-029) — kombiniert
Toggle-Disziplin (AC9), Suchprofil-Auswahl (AC1, inkl. AC7/AC10-Overrides)
und Querschnitt-Filter (AC6) zum Output-Vertrag `Filterkriterien` (Verträge
"Output an Datenquellen-Abfrage").

Reiner Domain-Kern (architecture.md §4 P1/P3, Modul 3 "Suchkriteria").
Konkrete Profil-Registrierung (welche `Suchprofil`-Instanzen für die
Klassen 1/2/7 in der `SuchprofilRegistry` stehen, AC2-AC5/AC11) sowie das
tatsächliche Auslösen der Suche (Main-Success-Scenario Schritt 1,
eventbasiert/periodisch) sind Sache der Folge-Stories (S-030/S-031/S-057)
bzw. der Scheduler-Integration — außerhalb des Scopes dieser Story.
"""

from __future__ import annotations

from app.contracts.anlageklassen_config import ToggleZustand
from app.contracts.kandidatensuche import (
    Filterkriterien,
    QuerschnittFilter,
    SuchprofilOverrides,
    SuchprofilRegistry,
)
from app.domain.kandidatensuche.querschnitt_filter import baue_filterkriterien
from app.domain.kandidatensuche.toggle_disziplin import lade_suchprofil_falls_erlaubt


def erstelle_filterkriterien(
    registry: SuchprofilRegistry,
    anlageklasse: int,
    zustand: ToggleZustand,
    querschnitt_filter: QuerschnittFilter,
    overrides: SuchprofilOverrides | None = None,
) -> Filterkriterien | None:
    """AC1+AC6+AC9+AC10 zusammengeführt: liefert `None`, wenn die Klasse
    per Toggle deaktiviert ist (AC9) ODER kein Profil für sie registriert
    ist (AC1: kein Fallback) — sonst die vollständigen Filterkriterien
    inkl. AC7/AC10-Overrides und Querschnitt-Filter-Schwellen (AC6)."""
    profil = lade_suchprofil_falls_erlaubt(registry, anlageklasse, zustand, overrides)
    if profil is None:
        return None
    return baue_filterkriterien(profil, querschnitt_filter)


__all__ = ["erstelle_filterkriterien"]
