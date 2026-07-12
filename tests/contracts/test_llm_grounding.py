"""Tests für die LLM-Grounding-Verträge (Story S-012).

Covers (llm-grounding): AC1, AC3

`app.contracts.llm_grounding` bildet die Verträge aus
`docs/specs/llm-grounding.md` ab. Diese Tests decken auf DTO-Ebene AC1
(`AnalyseFakt` verweigert die Instanziierung ohne Quellen-ID/Timestamp) und
AC3 (`AnalyseOutput` wird gegen ein festes JSON-Schema validiert — Score je
Kategorie 0–10 oder "fehlt", Pflichtfelder, kein unbekanntes Zusatzfeld).
Die End-to-End-Prüfung eines rohen (dict-)Analyse-Output-Kandidaten inkl.
AC2 (Input-Bindung) liegt in `tests/adapters/llm/test_grounding.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contracts.llm_grounding import (
    AnalyseFakt,
    AnalyseInput,
    AnalyseOutput,
    AnalyseScores,
)

VALID_FAKT_KWARGS = {
    "kennzahl_typ": "kgv",
    "wert": 12.5,
    "quellen_id": "sec-form4-123",
    "timestamp": datetime(2026, 7, 1, tzinfo=UTC),
}

VALID_SCORES_KWARGS = {
    "fundamental": 7.0,
    "technisch": 6.5,
    "qualitativ": "fehlt",
    "makro": 5.0,
    "risiko": 4.0,
}


def _valid_output_kwargs() -> dict:
    return {
        "scores": VALID_SCORES_KWARGS,
        "fakten": [VALID_FAKT_KWARGS],
        "begruendung": "Solide Fundamentaldaten, moderates Makro-Risiko.",
    }


def test_accepts_analysefakt_mit_quellen_id_und_timestamp() -> None:
    """@trace llm-grounding#AC1 — ein Fakt mit Quellen-ID UND Timestamp wird
    gebaut und behält exakt diese Felder."""
    fakt = AnalyseFakt(**VALID_FAKT_KWARGS)
    assert fakt.quellen_id == "sec-form4-123"
    assert fakt.timestamp == VALID_FAKT_KWARGS["timestamp"]
    assert fakt.wert == 12.5


@pytest.mark.parametrize("missing_field", ["quellen_id", "timestamp"])
def test_rejects_analysefakt_ohne_quellen_id_oder_timestamp(missing_field: str) -> None:
    """@trace llm-grounding#AC1 — fehlt Quellen-ID oder Timestamp, verweigert
    pydantic die Instanziierung des Fakts (Grounding-Pflicht)."""
    kwargs = dict(VALID_FAKT_KWARGS)
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        AnalyseFakt(**kwargs)


def test_rejects_analysefakt_mit_leerer_quellen_id() -> None:
    """@trace llm-grounding#AC1 — eine leere Quellen-ID zählt als fehlende
    Quellen-ID (nicht nur Schlüssel-Abwesenheit)."""
    with pytest.raises(ValidationError):
        AnalyseFakt(**dict(VALID_FAKT_KWARGS, quellen_id=""))


def test_accepts_analyseoutput_nach_festem_schema() -> None:
    """@trace llm-grounding#AC3 — ein Analyse-Output mit allen Pflichtfeldern
    (Scores 0-10/"fehlt" je Kategorie, Fakten, Begründung) wird gebaut."""
    output = AnalyseOutput(**_valid_output_kwargs())
    assert output.scores.fundamental == 7.0
    assert output.scores.qualitativ == "fehlt"
    assert len(output.fakten) == 1
    assert output.begruendung.startswith("Solide")


@pytest.mark.parametrize("missing_field", ["scores", "begruendung"])
def test_rejects_analyseoutput_mit_fehlendem_pflichtfeld(missing_field: str) -> None:
    """@trace llm-grounding#AC3 — fehlt ein Pflichtfeld des Analyse-Outputs,
    verweigert pydantic die Instanziierung (Schema-Verletzung, deckt E1)."""
    kwargs = _valid_output_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        AnalyseOutput(**kwargs)


@pytest.mark.parametrize("invalid_score", [-0.1, 10.1, 11, 100])
def test_rejects_analysescores_ausserhalb_0_bis_10(invalid_score: float) -> None:
    """@trace llm-grounding#AC3 — ein Kategorie-Score außerhalb 0-10 (und
    nicht der Platzhalter "fehlt") verletzt das feste Schema."""
    kwargs = dict(VALID_SCORES_KWARGS, fundamental=invalid_score)
    with pytest.raises(ValidationError):
        AnalyseScores(**kwargs)


def test_rejects_analyseoutput_mit_unbekanntem_zusatzfeld() -> None:
    """@trace llm-grounding#AC3 — ein Analyse-Output mit einem im Schema
    nicht vorgesehenen Zusatzfeld ist eine Schema-Verletzung ("festes"
    JSON-Schema, keine offene Struktur)."""
    kwargs = _valid_output_kwargs()
    kwargs["ueberraschungsfeld"] = "sollte nicht durchgehen"
    with pytest.raises(ValidationError):
        AnalyseOutput(**kwargs)


def test_rejects_analyseoutput_mit_fakt_ohne_quellen_id() -> None:
    """@trace llm-grounding#AC1 — ein Analyse-Output, dessen Fakten-Liste
    einen Fakt ohne Quellen-ID enthält, ist strukturell ungültig (die
    Grounding-Pflicht greift auch verschachtelt im Output-Schema)."""
    kwargs = _valid_output_kwargs()
    kwargs["fakten"] = [dict(VALID_FAKT_KWARGS, quellen_id="")]
    with pytest.raises(ValidationError):
        AnalyseOutput(**kwargs)


def test_analyseinput_akzeptiert_geerdete_fakten() -> None:
    """@trace llm-grounding#AC1 — der Analyse-Input trägt dieselben geerdeten
    Fakten (Quellen-ID + Timestamp Pflicht) wie der Output."""
    eingabe = AnalyseInput(
        titel="Beispiel AG",
        anlageklasse=1,
        fakten=[VALID_FAKT_KWARGS],
    )
    assert eingabe.fakten[0].quellen_id == "sec-form4-123"
