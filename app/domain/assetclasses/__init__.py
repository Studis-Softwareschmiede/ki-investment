"""Anlageklassen als Wertedomäne + Toggle-Auswertung (architecture.md §4
`domain/assetclasses/`, P6/ADR-008).

`toggle_guard.py` deckt Story S-019 (Spec `docs/specs/anlageklassen-config.md`
AC4/AC5): den geteilten Kontrakt, den jedes nachgelagerte Modul
(Kandidatensuche, Datenquellen-Abfrage, Analyse, Handelsplattformen,
Depotstrategie) vor jeder Aktion für eine Anlageklasse abfragt.
"""

from __future__ import annotations
