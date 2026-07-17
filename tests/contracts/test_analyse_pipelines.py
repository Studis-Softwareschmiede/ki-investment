"""Tests für die Analyse-Pipelines-Verträge — Buy-/Sell-Signal (Story
S-028/S-034).

Covers (analyse-pipelines): AC2, AC6

`app.contracts.analyse_pipelines` bildet die Output-Verträge aus
`docs/specs/analyse-pipelines.md` ab: `BuySignal` ("(a) Output neue
Titel") enthält mindestens Titel + Gesamtscore (AC2) plus Kategorie-Scores,
geerdete Fakten und Zeitstempel; `SellSignal` ("(b) Output bestehende
Titel", S-034) enthält mindestens Titel + Dringlichkeit (AC6) plus
Auslöser, Rohwerte und Zeitstempel. Diese Tests decken auf DTO-Ebene die
Struktur (Pflichtfelder, Wertebereich, Immutabilität); die eigentliche
Buy-Signal-Erzeugung (AC1, AC3, AC4) liegt in
`tests/domain/analysis_new/test_buy_pfad.py`, die Sell-Signal-Erzeugung
(AC5, AC6, AC7) in `tests/domain/analysis_existing/test_sell_pfad.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.analyse_framework import KategorieScores
from app.contracts.analyse_pipelines import BuySignal, SellSignal
from app.contracts.llm_grounding import AnalyseFakt

_FAKT = AnalyseFakt(
    kennzahl_typ="kgv",
    wert=Decimal("12.5"),
    quellen_id="sec-form4-123",
    timestamp=datetime(2026, 7, 1, tzinfo=UTC),
)

_KATEGORIE_SCORES = KategorieScores(
    fundamental=8.0, technisch=8.0, qualitativ=8.0, makro=8.0, risiko=8.0
)


def _valid_kwargs() -> dict:
    return {
        "titel_id": "acme-corp",
        "gesamtscore": 8.0,
        "kategorie_scores": _KATEGORIE_SCORES,
        "fakten_mit_quellen": (_FAKT,),
        "zeitstempel": datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
    }


def test_ac2_buy_signal_enthaelt_titel_und_gesamtscore_mindestens() -> None:
    """@trace analyse-pipelines#AC2 — ein `BuySignal` enthält mindestens
    Titel (`titel_id`) und Gesamtscore (`gesamtscore`), plus die volle
    Output-Form der Verträge (Kategorie-Scores, geerdete Fakten,
    Zeitstempel)."""
    signal = BuySignal(**_valid_kwargs())

    assert signal.titel_id == "acme-corp"
    assert signal.gesamtscore == 8.0
    assert signal.kategorie_scores == _KATEGORIE_SCORES
    assert signal.fakten_mit_quellen == (_FAKT,)
    assert signal.zeitstempel == datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def test_ac2_buy_signal_ist_unveraenderlich() -> None:
    """@trace analyse-pipelines#AC2 — `BuySignal` ist frozen (P2, explizite
    Modul-Verträge über unveränderliche DTOs statt gemeinsam mutiertem
    Zustand)."""
    signal = BuySignal(**_valid_kwargs())

    with pytest.raises(ValidationError):
        signal.gesamtscore = 5.0  # type: ignore[misc]


def test_ac2_buy_signal_verweigert_titel_id_leer() -> None:
    """@trace analyse-pipelines#AC2 — `titel_id` ist Pflicht (min_length=1);
    ein Buy-Signal ohne Titel ist strukturell ungültig."""
    kwargs = _valid_kwargs()
    kwargs["titel_id"] = ""

    with pytest.raises(ValidationError):
        BuySignal(**kwargs)


def test_ac2_buy_signal_verweigert_gesamtscore_ausserhalb_0_bis_10() -> None:
    """@trace analyse-pipelines#AC2 — `gesamtscore` liegt im Bereich 0–10
    (analog `analyse-framework`-Vertrag)."""
    kwargs = _valid_kwargs()
    kwargs["gesamtscore"] = 10.5

    with pytest.raises(ValidationError):
        BuySignal(**kwargs)


def test_ac2_buy_signal_verweigert_unbekanntes_zusatzfeld() -> None:
    """@trace analyse-pipelines#AC2 — kein unbekanntes Zusatzfeld
    (`extra="forbid"`), damit der Vertrag exakt der Spec-Output-Form
    entspricht."""
    kwargs = _valid_kwargs()
    kwargs["dringlichkeit"] = "hard"

    with pytest.raises(ValidationError):
        BuySignal(**kwargs)


def test_ac2_buy_signal_fakten_mit_quellen_default_leer() -> None:
    """@trace analyse-pipelines#AC2 — `fakten_mit_quellen` ist optional
    (Default leeres Tupel), falls eine Analyse keine referenzierten Fakten
    trägt."""
    kwargs = _valid_kwargs()
    del kwargs["fakten_mit_quellen"]

    signal = BuySignal(**kwargs)

    assert signal.fakten_mit_quellen == ()


def _valid_sell_kwargs() -> dict:
    return {
        "titel_id": "acme-corp",
        "dringlichkeit": "hard",
        "ausloeser": "news_katalysator",
        "rohwerte": {"anzahl_treffer": "1"},
        "zeitstempel": datetime(2026, 7, 17, 12, 0, tzinfo=UTC),
    }


def test_ac6_sell_signal_enthaelt_titel_und_dringlichkeit_mindestens() -> None:
    """@trace analyse-pipelines#AC6 — ein `SellSignal` enthält mindestens
    Titel (`titel_id`) und Dringlichkeit (`dringlichkeit`), plus die volle
    Output-Form der Verträge (Auslöser, Rohwerte, Zeitstempel)."""
    signal = SellSignal(**_valid_sell_kwargs())

    assert signal.titel_id == "acme-corp"
    assert signal.dringlichkeit == "hard"
    assert signal.ausloeser == "news_katalysator"
    assert signal.rohwerte == {"anzahl_treffer": "1"}
    assert signal.zeitstempel == datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def test_ac6_sell_signal_ist_unveraenderlich() -> None:
    """@trace analyse-pipelines#AC6 — `SellSignal` ist frozen (P2, explizite
    Modul-Verträge über unveränderliche DTOs statt gemeinsam mutiertem
    Zustand), analog `BuySignal`."""
    signal = SellSignal(**_valid_sell_kwargs())

    with pytest.raises(ValidationError):
        signal.dringlichkeit = "soft"  # type: ignore[misc]


def test_ac6_sell_signal_verweigert_titel_id_leer() -> None:
    """@trace analyse-pipelines#AC6 — `titel_id` ist Pflicht (min_length=1);
    ein Sell-Signal ohne Titel ist strukturell ungültig."""
    kwargs = _valid_sell_kwargs()
    kwargs["titel_id"] = ""

    with pytest.raises(ValidationError):
        SellSignal(**kwargs)


def test_ac6_sell_signal_verweigert_unbekannte_dringlichkeit() -> None:
    """@trace analyse-pipelines#AC7 — `dringlichkeit` ist auf `"hard"`/
    `"soft"` beschränkt (Verträge: "dringlichkeit: hard|soft")."""
    kwargs = _valid_sell_kwargs()
    kwargs["dringlichkeit"] = "medium"

    with pytest.raises(ValidationError):
        SellSignal(**kwargs)


def test_ac6_sell_signal_verweigert_unbekanntes_zusatzfeld() -> None:
    """@trace analyse-pipelines#AC6 — kein unbekanntes Zusatzfeld
    (`extra="forbid"`), damit der Vertrag exakt der Spec-Output-Form
    entspricht (analog `BuySignal`)."""
    kwargs = _valid_sell_kwargs()
    kwargs["gesamtscore"] = 8.0

    with pytest.raises(ValidationError):
        SellSignal(**kwargs)


def test_ac6_sell_signal_rohwerte_default_leer() -> None:
    """@trace analyse-pipelines#AC6 — `rohwerte` ist optional (Default
    leeres Dict), analog `UeberwachungsEreignis.rohwerte`."""
    kwargs = _valid_sell_kwargs()
    del kwargs["rohwerte"]

    signal = SellSignal(**kwargs)

    assert signal.rohwerte == {}
