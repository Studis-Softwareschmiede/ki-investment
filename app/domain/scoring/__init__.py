"""Analyse-Framework — Score-Engine (architecture.md §4 `domain/scoring/`, C-007).

Kategorie-Score, Gesamtscore, Sanity-Cap, Signal-Schwellen. `score_engine.py`
deckt den Berechnungskern ab: Kategorie-Score (AC1/AC2/AC9), Gesamtscore
(AC3), Referenz-Verifikation (AC4), Signal-Ableitung nach konfigurierbaren
Schwellen (AC5/AC6), Risiko-Sanity-Cap (AC7, S-010) und Determinismus
(AC11). No-Evidence-No-Trade-Skip (AC8) und Spinnennetz-Output (AC10)
folgen in S-011.
"""

from __future__ import annotations
