"""Tests für die Toggle-Ausnahme gehaltener Titel (Story S-032).

Covers (depot-ueberwachung): AC8

`app.domain.depot_ueberwachung.toggle.ist_ueberwachung_erlaubt` deckt
A1: "Ist die Anlageklasse eines gehaltenen Titels per Feature-Toggle
deaktiviert, bleibt die Überwachung dieses Titels trotzdem aktiv" — die
Funktion delegiert an den bestehenden Toggle-Guard
(`app.domain.assetclasses.toggle_guard`) statt die Regel selbst
nachzubauen."""

from __future__ import annotations

from app.domain.depot_ueberwachung.toggle import ist_ueberwachung_erlaubt


def test_ueberwachung_bleibt_erlaubt_bei_deaktivierter_anlageklasse() -> None:
    """@trace depot-ueberwachung#AC8 — deckt A1: eine deaktivierte
    Anlageklasse (`aktiv=False`) schaltet die Überwachung eines bereits
    gehaltenen Titels NICHT ab."""
    assert ist_ueberwachung_erlaubt(aktiv=False) is True


def test_ueberwachung_bleibt_erlaubt_bei_aktiver_anlageklasse() -> None:
    """@trace depot-ueberwachung#AC8 — Normalbetrieb: eine aktive
    Anlageklasse überwacht einen gehaltenen Titel ebenfalls."""
    assert ist_ueberwachung_erlaubt(aktiv=True) is True
