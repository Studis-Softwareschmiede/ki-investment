"""Depotmodul — Modul 16 (architecture.md §4 `domain/portfolio/`, C-013,
C-014, C-016, C-017).

Enthält aktuell `fill_booking` (S-015, AC1 + AC10 — Vollständigkeits-/
Konsistenz-Gate vor der Buchung eines Fills), `position_booking` (S-016,
AC2/AC3/AC5 — G/V-Berechnung, Gebühren-Netting, Einstand-Methode),
`transaction_historie` (S-035, AC4/AC7 — append-only Transaktionshistorie
& TCA) und den zugehörigen Repository-Port `ports.PositionRepository`.
Portfolio-Aggregate (S-036) folgen in einer Folge-Story.
"""

from __future__ import annotations
