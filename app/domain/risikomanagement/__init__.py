"""Risikomanagement-Gate — Modul (architecture.md §4 `domain/risikomanagement/`,
BR-014, Spec `docs/specs/risikomanagement.md`).

Enthält `gate.py` (Story S-044, AC2/AC5/AC6/AC12): den Drei-Wege-Entscheid
(durchwinken/deckeln/blockieren) für geplante Kauf-Orders inkl.
Sektor-Konzentrations-Prüfung (AC2) und Fail-safe bei fehlendem
Depot-Stand (AC12). Klumpenrisiko je Anlageklasse, Korrelation, Drawdown
und der portfolio-weite Kelly-Cap (AC8-AC10) sowie die Warteliste bei
Blockade (AC7) folgen in Folge-Storys.
"""

from __future__ import annotations
