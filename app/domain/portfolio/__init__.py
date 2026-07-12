"""Depotmodul — Modul 16 (architecture.md §4 `domain/portfolio/`, C-013,
C-014, C-016, C-017).

Enthält aktuell `fill_booking` (S-015, AC1 + AC10 — Vollständigkeits-/
Konsistenz-Gate vor der Buchung eines Fills) und den zugehörigen
Repository-Port `ports.PositionRepository`. G/V-Berechnung, Gebühren-
Netting, Einstand-Methode (S-016), Transaktionshistorie/TCA (S-035) und
Portfolio-Aggregate (S-036) folgen in Folge-Storys.
"""

from __future__ import annotations
