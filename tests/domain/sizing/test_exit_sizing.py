"""Tests für das dringlichkeitsbasierte Exit-Sizing (Story S-042).

Covers (sizing): AC8, AC12

`app.domain.sizing.exit_sizing.bestimme_exit_order` deckt AC8 (Hard-Exit
-> sofort/`stop_market`, Soft-Exit -> gestaffelt/`limit`, primär nach der
Dringlichkeit des `SellSignal`) sowie den Grenzfall einer ungültigen
`position_menge`. AC12 (kein Risikomanagement-Gate dazwischen) wird
strukturell geprüft: die Funktion nimmt keine Depotstrategie-/Limit-Daten
entgegen (Signatur-Introspektion) — der Import-Guard-Beleg (kein
`app.contracts.risikomanagement`-/`app.db.depotstrategie`-Import) liegt in
`tests/architecture/test_exit_sizing_umgeht_risikomanagement.py`.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.contracts.analyse_pipelines import Dringlichkeit, SellSignal
from app.domain.sizing.exit_sizing import bestimme_exit_order


def _sell_signal(dringlichkeit: Dringlichkeit) -> SellSignal:
    return SellSignal(
        titel_id="AAA",
        dringlichkeit=dringlichkeit,
        ausloeser="news_katalysator",
        rohwerte={},
        zeitstempel=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_ac8_hard_exit_verkauft_sofort_die_gesamte_position_per_stop_market() -> None:
    """@trace sizing#AC8 — Hard-Exit: sofort die gesamte Position, Order-
    Typ Stop-Market (Edge-Cases: kritischer Not-Ausstieg -> Stop-Market,
    nicht Stop-Limit)."""
    auftrag = bestimme_exit_order(_sell_signal("hard"), position_menge=Decimal("100"))

    assert auftrag.titel_id == "AAA"
    assert auftrag.menge == Decimal("100")
    assert auftrag.tranchen == (Decimal("100"),)
    assert auftrag.order_typ == "stop_market"
    assert auftrag.ausfuehrungsprofil == "sofort"
    assert auftrag.preis is None


def test_ac8_soft_exit_ist_gestaffelt_per_limit_default() -> None:
    """@trace sizing#AC8 — Soft-Exit: gestaffelt, Order-Typ Limit als
    Default."""
    auftrag = bestimme_exit_order(_sell_signal("soft"), position_menge=Decimal("100"))

    assert auftrag.titel_id == "AAA"
    assert auftrag.menge == Decimal("100")
    assert auftrag.order_typ == "limit"
    assert auftrag.ausfuehrungsprofil == "gestaffelt"
    assert auftrag.preis is None


@pytest.mark.parametrize("position_menge", [Decimal("0"), Decimal("-1")])
def test_ac8_ungueltige_position_menge_wirft(position_menge: Decimal) -> None:
    """@trace sizing#AC8 — `position_menge <= 0` ist keine gültige, noch
    offene Position zum Verkauf."""
    with pytest.raises(ValueError):
        bestimme_exit_order(_sell_signal("hard"), position_menge=position_menge)


def test_ac12_bestimme_exit_order_nimmt_keine_risikomanagement_daten_entgegen() -> None:
    """@trace sizing#AC12 — strukturell abgesichert: die Signatur von
    `bestimme_exit_order` enthält ausschliesslich `sell_signal` und
    `position_menge` — keine Depotstrategie-/Limit-/Risiko-Gate-Parameter,
    über die ein Risikomanagement-Ergebnis hereinkommen könnte."""
    parameter = set(inspect.signature(bestimme_exit_order).parameters)
    assert parameter == {"sell_signal", "position_menge"}
