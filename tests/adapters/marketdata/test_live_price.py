"""Tests für `NoOpLivePriceProvider` (`app.adapters.marketdata.live_price`,
Story S-054, `docs/specs/depot.md` AC11).

Covers (depot): AC11
"""

from __future__ import annotations

from app.adapters.marketdata.live_price import NoOpLivePriceProvider


def test_liefert_immer_none_kein_live_kurs_verfuegbar():
    """AC11: solange kein echter Live-Kurs-Socket-Adapter verdrahtet ist,
    liefert der Platzhalter für jeden Titel `None` ("nicht bewertbar",
    `depot.md` Edge-Cases) — kein fingierter Kurs."""
    provider = NoOpLivePriceProvider()

    assert provider.aktueller_preis("titel-1") is None
    assert provider.aktueller_preis("titel-2") is None
