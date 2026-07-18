"""Lernschleife — Validierungs-Gate (architecture.md §4 `domain/lernschleife/`, C-012).

Stufe A (historisch): Mindest-Stichprobe, Walk-Forward mit Embargo,
Walk-Forward-Effizienz, Deflated Sharpe Ratio (`stage_a.py`, S-060, AC4-
AC7). Stufe B (Paper-Bewährung, AC8/AC9, `stage_b.py`, S-061). Ampel-
Ableitung + Regel-Promotion nur bei Grün (`gate.py`, S-062, AC10-AC12).
"""

from __future__ import annotations
