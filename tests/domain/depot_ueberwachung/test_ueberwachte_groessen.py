"""Tests für die je Anlageklasse überwachten Grössen (Story S-032).

Covers (depot-ueberwachung): AC3

`app.domain.depot_ueberwachung.ueberwachte_groessen
.ermittle_ueberwachte_groessen` bestimmt anhand der Anlageklasse, welche
Grössen überwacht werden — mindestens die vier Standard-Grössen, plus
On-Chain-Abflüsse ausschliesslich für Anlageklasse 7 (Krypto)."""

from __future__ import annotations

from app.domain.depot_ueberwachung.ueberwachte_groessen import (
    UEBERWACHTE_GROESSEN_STANDARD,
    ermittle_ueberwachte_groessen,
)


def test_aktien_erhalten_nur_die_vier_standard_groessen() -> None:
    """@trace depot-ueberwachung#AC3 — Anlageklasse 1 (Aktien) erhält
    genau die vier Standard-Grössen (News-Katalysatoren, relativer
    Kurssturz, Sentiment-Kippen, Momentum-Verlust), keine Krypto-Grösse."""
    groessen = ermittle_ueberwachte_groessen(1)
    assert groessen == UEBERWACHTE_GROESSEN_STANDARD
    assert "on_chain_abfluesse" not in groessen


def test_krypto_erhaelt_zusaetzlich_on_chain_abfluesse() -> None:
    """@trace depot-ueberwachung#AC3 — Anlageklasse 7 (Krypto) erhält
    zusätzlich On-Chain-Abflüsse, alle Standard-Grössen bleiben erhalten."""
    groessen = ermittle_ueberwachte_groessen(7)
    assert set(UEBERWACHTE_GROESSEN_STANDARD).issubset(groessen)
    assert "on_chain_abfluesse" in groessen


def test_nicht_krypto_klassen_bekommen_keine_krypto_zusatzgroesse() -> None:
    """@trace depot-ueberwachung#AC3 — "nicht zur Klasse passende Grössen
    werden nicht abgefragt": über alle Nicht-Krypto-Klassen bleibt die
    On-Chain-Grösse ausgeschlossen."""
    for anlageklasse in range(1, 12):
        if anlageklasse == 7:
            continue
        assert "on_chain_abfluesse" not in ermittle_ueberwachte_groessen(anlageklasse)
