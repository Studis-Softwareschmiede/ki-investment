"""Depot-Überwachung — Monitoring-Zyklus-Domain-Kern (architecture.md §4
`domain/`, Story S-032, Spec `docs/specs/depot-ueberwachung.md`).

Reine Domain-Bausteine (P1: kein I/O, kein SQLAlchemy) für AC1
(Input-Vollständigkeit, `vollstaendigkeit.py`), AC3 (je Anlageklasse
überwachte Grössen, `ueberwachte_groessen.py`), AC8 (Toggle-Ausnahme für
gehaltene Titel, `toggle.py`) und AC9 (Frische-Fenster, `frische.py`). Die
I/O-seitige Orchestrierung (Depot-Read, geteilte Datenquellen-Abfrage,
Protokollierung) lebt in `app.orchestration.depot_ueberwachung`.
"""

from __future__ import annotations
