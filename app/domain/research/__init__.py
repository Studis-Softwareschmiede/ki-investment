"""Research — Hypothesen-Erzeugung mit Mindest-Evidenz-Protokoll &
Marktlogik-Filter (architecture.md §4 `domain/research/`, C-012).

AC1/AC2 (`hypothesen_erzeugung.py`, S-058): Research liefert ausschliesslich
Hypothesen ans Validierungs-Gate (nie ein direkter Eingriff in die
Suchkriteria) und filtert dabei rein statistische Zufallsmuster ohne
marktlogische Begründung aus. Die eigentliche Muster-Erkennung (Vergleich
Tagesgewinner/-verlierer gegen aktuelle Suchkriteria) sowie die Gate-
Anbindung (Trial-Registry, Stufe A/B, Ampel) folgen in eigenen Stories
(S-059-S-062)."""

from __future__ import annotations
