"""Tests für die reinen TCA-Formel-Bausteine (Story S-035, AC7).

Covers (depot): AC7

`app.domain.portfolio.transaction_historie` liefert nur die reine Formel
(`berechne_slippage`) + Aggregation (`aggregiere_slippage`) — das
eigentliche Schreiben/Lesen der Transaktionshistorie ist Repository-Sache
(siehe `tests/adapters/repositories/test_position_repository.py` und
`tests/domain/portfolio/test_position_booking.py` für die Verdrahtung über
`verbuche_fill`).
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.portfolio.transaction_historie import aggregiere_slippage, berechne_slippage


def test_berechne_slippage_positiv_wenn_fill_teurer_als_arrival() -> None:
    """@trace depot#AC7 — Fill-Preis über Arrival-Price ergibt eine
    positive (nachteilige) Slippage."""
    ergebnis = berechne_slippage(Decimal("101.5"), Decimal("100"))
    assert ergebnis == Decimal("1.5")


def test_berechne_slippage_negativ_wenn_fill_guenstiger_als_arrival() -> None:
    """@trace depot#AC7 — Fill-Preis unter Arrival-Price ergibt eine
    negative (vorteilhafte) Slippage."""
    ergebnis = berechne_slippage(Decimal("98"), Decimal("100"))
    assert ergebnis == Decimal("-2")


def test_berechne_slippage_null_bei_identischem_preis() -> None:
    """@trace depot#AC7 — kein Unterschied zwischen Fill- und
    Arrival-Price ergibt Slippage 0."""
    assert berechne_slippage(Decimal("100"), Decimal("100")) == Decimal("0")


def test_aggregiere_slippage_summiert_mehrere_je_trade_ermittelte_werte() -> None:
    """@trace depot#AC7 — mehrere je-Trade ermittelte Slippage-Werte sind
    aggregiert (Summe, analog `position_booking.aggregiere_gv`, AC2)
    abrufbar."""
    werte = [Decimal("1.5"), Decimal("-2"), Decimal("0.25")]
    assert aggregiere_slippage(werte) == Decimal("-0.25")


def test_aggregiere_slippage_leere_liste_ergibt_null() -> None:
    """@trace depot#AC7 — keine Trades ergeben ein neutrales
    Aggregat (0), keinen Fehler."""
    assert aggregiere_slippage([]) == Decimal("0")
