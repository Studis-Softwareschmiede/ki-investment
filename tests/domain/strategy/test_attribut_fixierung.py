"""Tests für die Attribut-Bündel-Fixierung / annotierte Kauf-Order
(Story S-040).

Covers (strategie-exit-regeln): AC1, AC11

- AC1: `fixiere_attribut_buendel()` fasst Ordergrösse, Strategie,
  Zeithorizont, Exit-Regeln und These zu einer `AnnotierteKaufOrder`
  zusammen (`fixiert_am` gesetzt, `unveraenderlich=True`).
- AC11: ein unvollständiges Exit-Regel-Bündel (Stop-Parameter unbestimmt,
  fehlende Thesis-Invalidierung) oder eine fehlende These verhindert die
  Erzeugung der `AnnotierteKaufOrder` (`UnvollstaendigesAttributBuendelError`,
  Edge-Case „Fehlende oder unvollständige Exit-Regeln … verhindern die
  Weitergabe an das Risikomanagement").
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.contracts.strategie_exit_regeln import AnnotierteKaufOrder, ExitDefaultVorschlag
from app.domain.strategy.attribut_fixierung import (
    UnvollstaendigesAttributBuendelError,
    fixiere_attribut_buendel,
)

_JETZT = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)


def _vollstaendiger_vorschlag(**overrides: object) -> ExitDefaultVorschlag:
    kwargs = {
        "kategorie": "value_aktien",
        "stop_typ": "fundamental",
        "stop_hinweis": "Fundamentaler Stop (These bricht).",
        "stop_parameter": None,
        "stop_unbestimmt": False,
        "take_profit_hinweis": "Zielwert erreicht.",
        "time_box": None,
        "thesis_invalidierung": "Marktanteil < 10%.",
    }
    kwargs.update(overrides)
    return ExitDefaultVorschlag(**kwargs)


def test_ac1_fixiert_vollstaendiges_attribut_buendel() -> None:
    """@trace strategie-exit-regeln#AC1 — Ordergrösse, Strategie,
    Zeithorizont, Exit-Regeln und These werden zu EINER
    `AnnotierteKaufOrder` zusammengefasst, `unveraenderlich=True`."""
    vorschlag = _vollstaendiger_vorschlag()

    order = fixiere_attribut_buendel(
        titel_id="AAPL",
        ordergroesse=Decimal("1000"),
        strategie="Value",
        zeithorizont=7,
        exit_regeln=vorschlag,
        these="Unterbewertet gegenüber Peer-Group.",
        jetzt=_JETZT,
    )

    assert isinstance(order, AnnotierteKaufOrder)
    assert order.titel_id == "AAPL"
    assert order.ordergroesse == Decimal("1000")
    assert order.strategie == "Value"
    assert order.zeithorizont == 7
    assert order.exit_regeln is vorschlag
    assert order.these == "Unterbewertet gegenüber Peer-Group."
    assert order.fixiert_am == _JETZT
    assert order.unveraenderlich is True


def test_ac1_ohne_jetzt_setzt_aktuellen_zeitstempel() -> None:
    """@trace strategie-exit-regeln#AC1 — ohne explizites `jetzt` wird
    `fixiert_am` auf den aktuellen (UTC-)Zeitpunkt gesetzt."""
    vor = datetime.now(UTC)

    order = fixiere_attribut_buendel(
        titel_id="AAPL",
        ordergroesse=Decimal("500"),
        strategie="Index",
        zeithorizont=8,
        exit_regeln=_vollstaendiger_vorschlag(),
        these="Langfristiger Index-Halter.",
    )

    nach = datetime.now(UTC)
    assert vor <= order.fixiert_am <= nach


def test_ac11_lehnt_unbestimmten_stop_parameter_ab() -> None:
    """@trace strategie-exit-regeln#AC11 — `stop_unbestimmt=True` (ATR
    nicht berechenbar) verhindert die Weitergabe an das Risikomanagement
    (Edge-Case), es entsteht keine `AnnotierteKaufOrder`."""
    vorschlag = _vollstaendiger_vorschlag(
        stop_typ="atr_trailing", stop_parameter=None, stop_unbestimmt=True
    )

    with pytest.raises(UnvollstaendigesAttributBuendelError):
        fixiere_attribut_buendel(
            titel_id="AAPL",
            ordergroesse=Decimal("1000"),
            strategie="Growth",
            zeithorizont=5,
            exit_regeln=vorschlag,
            these="Wachstumsstory intakt.",
            jetzt=_JETZT,
        )


@pytest.mark.parametrize("thesis_invalidierung", [None, "", "   "])
def test_ac11_lehnt_fehlende_thesis_invalidierung_ab(thesis_invalidierung: str | None) -> None:
    """@trace strategie-exit-regeln#AC11 — eine leere/fehlende Thesis-
    Invalidierung (kein Stop-Trigger im Sinne der Edge-Case-Regel)
    verhindert die Weitergabe."""
    vorschlag = _vollstaendiger_vorschlag(thesis_invalidierung=thesis_invalidierung)

    with pytest.raises(UnvollstaendigesAttributBuendelError):
        fixiere_attribut_buendel(
            titel_id="AAPL",
            ordergroesse=Decimal("1000"),
            strategie="Value",
            zeithorizont=7,
            exit_regeln=vorschlag,
            these="Unterbewertet.",
            jetzt=_JETZT,
        )


@pytest.mark.parametrize("these", [None, "", "  "])
def test_ac11_lehnt_fehlende_these_ab(these: str | None) -> None:
    """@trace strategie-exit-regeln#AC11 — eine leere/fehlende Kauf-These
    verhindert die Weitergabe an das Risikomanagement."""
    with pytest.raises(UnvollstaendigesAttributBuendelError):
        fixiere_attribut_buendel(
            titel_id="AAPL",
            ordergroesse=Decimal("1000"),
            strategie="Value",
            zeithorizont=7,
            exit_regeln=_vollstaendiger_vorschlag(),
            these=these,  # type: ignore[arg-type]
            jetzt=_JETZT,
        )
