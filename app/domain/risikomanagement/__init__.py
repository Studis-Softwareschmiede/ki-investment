"""Risikomanagement-Gate — Modul (architecture.md §4 `domain/risikomanagement/`,
BR-014, Spec `docs/specs/risikomanagement.md`).

Enthält `gate.py` (Storys S-044 AC2/AC5/AC6/AC12, S-045 AC8/AC9/AC10 und
S-056 AC7): den Drei-Wege-Entscheid (durchwinken/deckeln/blockieren) für
geplante Kauf-Orders inkl. voller Prüfmatrix (Sektor/Klasse/
Einzelposition/Korrelations-Cluster/portfolio-weiter Kelly-Cap), Fail-safe
bei fehlendem Depot-Stand (AC12) und der optionalen Warteliste-Markierung
beim Blockieren (AC7, `warteliste_bei_blockade`-Parameter). Die eigentliche
Warteliste-Mechanik (Persistenz, Re-Prüfung/Ablauf) ist laut Spec weiterhin
offen (Folge-Story).
"""

from __future__ import annotations
