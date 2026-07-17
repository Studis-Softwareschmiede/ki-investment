"""Analyse bestehende Titel — Sell-Pfad (architecture.md §4
`domain/analysis_existing/`, Modul 8, C-011, Spec
`docs/specs/analyse-pipelines.md`).

Wiederbewertung gehaltener Positionen AUSSCHLIESSLICH gegen die beim Kauf
fixierten Exit-Regeln (S-034, AC5-AC7): `sell_pfad
.bewerte_bestehenden_titel` nimmt ein bereits über die Depot-Überwachung
geschwellenwertete `app.contracts.depot_ueberwachung.UeberwachungsEreignis`
entgegen und liefert immer ein `app.contracts.analyse_pipelines.SellSignal`
mit Dringlichkeit (Hard/Soft).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM-Aufruf,
kein FastAPI, kein SQLAlchemy.

Der Buy-Pfad (Modul 7, `domain/analysis_new/`, S-028) ist bewusst ein
eigenständiges Paket — dieser Sell-Pfad kennt keinen Buy-Signal-Typ und
erzeugt strukturell nie eines (AC2, "die beiden Analysepfade sind
getrennt").
"""

from __future__ import annotations
