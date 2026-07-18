"""Tests für die Konfigurations-Query-Funktionen `app/api/queries/config.py`
(Story S-069, `docs/specs/frontend-cockpit.md` AC9/AC10).

Covers (frontend-cockpit): AC9, AC10

Reine Funktionstests (kein HTTP): belegen, dass die Query-Funktionen exakt
den vom Lese-Callable gelieferten Wert durchreichen — keinen zweiten
Datenzusammenbau (AC10) — und den `None`-Fall der Depotstrategie (noch kein
Preset aktiviert) unverändert weitergeben. Der HTTP-/Router-Ebenen-Test
(coder/R06) liegt in `tests/api/test_config_route.py`."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.api.queries.config import (
    lade_anlageklassen_konfiguration,
    lade_depotstrategie_konfiguration,
)
from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.contracts.risikomanagement import DepotstrategieKonfiguration


def test_lade_anlageklassen_konfiguration_reicht_callable_ergebnis_durch() -> None:
    erwartet = [
        AnlageklasseEintrag(id=1, name="Aktien", aktiv=True, prio_stufe="MVP"),
        AnlageklasseEintrag(id=10, name="FX", aktiv=False, prio_stufe="Stufe3"),
    ]

    ergebnis = lade_anlageklassen_konfiguration(lambda: erwartet)

    assert ergebnis == erwartet


def test_lade_depotstrategie_konfiguration_reicht_none_durch() -> None:
    ergebnis = lade_depotstrategie_konfiguration(lambda: None)

    assert ergebnis is None


def test_lade_depotstrategie_konfiguration_reicht_konfiguration_durch() -> None:
    erwartet = DepotstrategieKonfiguration(
        portfolio_strategy_id=uuid.uuid4(),
        risk_profile_name="ausgewogen",
        max_einzelposition_pct=Decimal("5"),
        max_sektor_pct=Decimal("20"),
        cash_quote_ziel_pct=Decimal("5"),
        gesamt_exposure_cap_pct=Decimal("25"),
        max_anlageklasse_pct={7: Decimal("10")},
    )

    ergebnis = lade_depotstrategie_konfiguration(lambda: erwartet)

    assert ergebnis == erwartet
