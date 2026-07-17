"""Sizing — Position-/Exit-Sizing (architecture.md §4 `domain/sizing/`,
Modul 9 + 10, Spec `docs/specs/sizing.md`).

`position_sizing.py` (Story S-039, AC1/AC2/AC3/AC4/AC7) deckt den
**Position-Sizing-Kern**: Fractional-Kelly-Formel, Half-/Quarter-Kelly-
Fraktionen, hartes Risiko-Cap je Trade und die Scharfschaltungs-Schwelle
für Kelly (vs. Fixed-Fractional-Rückfall). Exit-Sizing (AC8–AC12,
Verkaufsseite) folgt in einer späteren Story.

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB — der Ausschnitt "Position-Sizing betrachtet nur den einzelnen Titel
(Mikro); es nimmt keine Portfolio-/Korrelationsprüfung vor" (AC7) ist
strukturell dadurch abgebildet, dass dieses Paket keine Portfolio-/Depot-
Daten entgegennimmt.
"""

from __future__ import annotations
