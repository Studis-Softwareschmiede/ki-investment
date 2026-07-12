"""Analyse-Framework — Score-Engine (architecture.md §4 `domain/scoring/`, C-007).

Kategorie-Score, Gesamtscore, Sanity-Cap, Signal-Schwellen. Diese Story
(S-009) deckt den Berechnungskern ab (`score_engine.py`): Kategorie-Score
(AC1/AC2/AC9), Gesamtscore (AC3), Referenz-Verifikation (AC4) und
Determinismus (AC11). Signal-Schwellen (AC5/AC6), Risiko-Sanity-Cap (AC7),
No-Evidence-No-Trade-Skip (AC8) und Spinnennetz-Output (AC10) folgen in
S-010/S-011.
"""

from __future__ import annotations
