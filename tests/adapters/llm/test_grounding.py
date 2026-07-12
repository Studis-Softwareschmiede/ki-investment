"""Tests für das LLM-Grounding-Gate (Story S-012 + S-013).

Covers (llm-grounding): AC1, AC2, AC3, AC10

`app.adapters.llm.grounding.pruefe_grounding` ist der tatsächliche
Einstiegspunkt, der einen rohen (untrusted, dict-förmigen) Analyse-Output-
Kandidaten prüft — nicht nur ein bereits vertrauenswürdiges DTO. Diese
Tests decken den Gate-Aufruf End-to-End: AC1 (Grounding-Pflicht, hier über
einen rohen Output-Kandidaten ohne Timestamp), AC2 (Input-Bindung — eine
input-fremde Zahl wird abgelehnt), AC3 (Schema-Verletzung, deckt E1) —
inklusive des Happy-Path (`status="geerdet"`) — sowie AC10 (S-013): beide
Ablehnungspfade schreiben zusätzlich einen `ProtokollEintrag` ins
Audit-Protokoll (`app.core.audit_log`). Die reinen DTO-Grenzfälle
(Feld-für-Feld) liegen in `tests/contracts/test_llm_grounding.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.llm.grounding import pruefe_grounding
from app.contracts.llm_grounding import AnalyseFakt, AnalyseInput
from app.core.audit_log import alle_eintraege, reset_fuer_tests

FAKT_A = AnalyseFakt(
    kennzahl_typ="kgv",
    wert=12.5,
    quellen_id="sec-form4-123",
    timestamp=datetime(2026, 7, 1, tzinfo=UTC),
)


@pytest.fixture(autouse=True)
def _audit_log_isolieren():
    """Isoliert die in-memory Audit-Historie zwischen Testfällen (AC10)."""
    reset_fuer_tests()
    yield
    reset_fuer_tests()


def _eingabe(fakten: tuple[AnalyseFakt, ...] = (FAKT_A,)) -> AnalyseInput:
    return AnalyseInput(titel="Beispiel AG", anlageklasse=1, fakten=fakten)


def _valid_output_roh(fakten: list[dict] | None = None) -> dict:
    return {
        "scores": {
            "fundamental": 7.0,
            "technisch": 6.5,
            "qualitativ": "fehlt",
            "makro": 5.0,
            "risiko": 4.0,
        },
        "fakten": fakten
        if fakten is not None
        else [
            {
                "kennzahl_typ": "kgv",
                "wert": 12.5,
                "quellen_id": "sec-form4-123",
                "timestamp": "2026-07-01T00:00:00Z",
            }
        ],
        "begruendung": "Solide Fundamentaldaten, moderates Makro-Risiko.",
    }


def test_pruefe_grounding_akzeptiert_geerdeten_output() -> None:
    """@trace llm-grounding#AC1,AC2,AC3 — ein Output, der dem Schema
    entspricht und dessen Fakten exakt aus dem Input stammen, gilt als
    geerdet."""
    ergebnis = pruefe_grounding(_valid_output_roh(), _eingabe())

    assert ergebnis.status == "geerdet"
    assert ergebnis.grund is None
    assert ergebnis.output is not None
    assert ergebnis.output.fakten[0].quellen_id == "sec-form4-123"


def test_pruefe_grounding_lehnt_fakt_ohne_timestamp_ab() -> None:
    """@trace llm-grounding#AC1 — ein roher Output-Kandidat, dessen Fakt
    keinen Timestamp trägt, wird als Schema-Verletzung abgelehnt (die
    Grounding-Pflicht ist im Schema verankert)."""
    output_roh = _valid_output_roh(
        fakten=[
            {
                "kennzahl_typ": "kgv",
                "wert": 12.5,
                "quellen_id": "sec-form4-123",
                # kein "timestamp"
            }
        ]
    )

    ergebnis = pruefe_grounding(output_roh, _eingabe())

    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "schema_verletzung"
    assert ergebnis.output is None


def test_pruefe_grounding_lehnt_fakt_ohne_quellen_id_ab() -> None:
    """@trace llm-grounding#AC1 — ein roher Output-Kandidat, dessen Fakt
    keine Quellen-ID trägt, wird als Schema-Verletzung abgelehnt."""
    output_roh = _valid_output_roh(
        fakten=[
            {
                "kennzahl_typ": "kgv",
                "wert": 12.5,
                "quellen_id": "",
                "timestamp": "2026-07-01T00:00:00Z",
            }
        ]
    )

    ergebnis = pruefe_grounding(output_roh, _eingabe())

    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "schema_verletzung"


def test_pruefe_grounding_lehnt_input_fremde_zahl_ab() -> None:
    """@trace llm-grounding#AC2 — ein Fakt im Output, der exakt (kennzahl_typ,
    wert, quellen_id, timestamp) nicht im strukturierten Input vorkommt,
    führt zur Ablehnung, obwohl er für sich genommen schema-valide ist."""
    output_roh = _valid_output_roh(
        fakten=[
            {
                "kennzahl_typ": "kgv",
                "wert": 999.9,  # kommt im Input nicht vor
                "quellen_id": "sec-form4-123",
                "timestamp": "2026-07-01T00:00:00Z",
            }
        ]
    )

    ergebnis = pruefe_grounding(output_roh, _eingabe())

    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "input_fremde_zahl"
    assert "999.9" in (ergebnis.detail or "")


def test_pruefe_grounding_lehnt_schema_verletzung_ab() -> None:
    """@trace llm-grounding#AC3 — ein Output-Kandidat, der das feste
    JSON-Schema verletzt (Score außerhalb 0-10), wird abgelehnt (deckt E1)."""
    output_roh = _valid_output_roh()
    output_roh["scores"]["fundamental"] = 15.0

    ergebnis = pruefe_grounding(output_roh, _eingabe())

    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "schema_verletzung"
    assert ergebnis.output is None


def test_pruefe_grounding_ist_deterministisch() -> None:
    """@trace llm-grounding#AC1,AC2,AC3 — gleiche Eingaben liefern
    zweimal exakt dasselbe Ergebnis (kein LLM-Aufruf, keine Systemzeit-
    Abhängigkeit im Gate selbst)."""
    output_roh = _valid_output_roh()
    eingabe = _eingabe()

    erstes_ergebnis = pruefe_grounding(output_roh, eingabe)
    zweites_ergebnis = pruefe_grounding(output_roh, eingabe)

    assert erstes_ergebnis == zweites_ergebnis


def test_pruefe_grounding_protokolliert_schema_verletzung() -> None:
    """@trace llm-grounding#AC10 — eine Schema-Verletzung (AC3) erzeugt
    zusätzlich zum abgelehnten `GroundingErgebnis` einen Protokolleintrag
    im Audit-Log (Grund `schema_verletzung`)."""
    output_roh = _valid_output_roh()
    output_roh["scores"]["fundamental"] = 15.0

    pruefe_grounding(output_roh, _eingabe())

    eintraege = alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "schema_verletzung"
    assert eintraege[0].zeitpunkt is not None


def test_pruefe_grounding_protokolliert_input_fremde_zahl() -> None:
    """@trace llm-grounding#AC10 — eine input-fremde Zahl (AC2) erzeugt
    einen Protokolleintrag mit der betroffenen Kennzahl/Quelle (Grund
    `input_fremde_zahl`)."""
    output_roh = _valid_output_roh(
        fakten=[
            {
                "kennzahl_typ": "kgv",
                "wert": 999.9,
                "quellen_id": "sec-form4-123",
                "timestamp": "2026-07-01T00:00:00Z",
            }
        ]
    )

    pruefe_grounding(output_roh, _eingabe())

    eintraege = alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "input_fremde_zahl"
    assert eintraege[0].kennzahl_typ == "kgv"
    assert eintraege[0].quellen_id == "sec-form4-123"


def test_pruefe_grounding_protokolliert_nichts_bei_geerdetem_output() -> None:
    """@trace llm-grounding#AC10 — ein akzeptierter (geerdeter) Output
    erzeugt keinen Protokolleintrag (nur Ablehnungen sind auditierbar
    relevant, Spec AC10)."""
    pruefe_grounding(_valid_output_roh(), _eingabe())

    assert alle_eintraege() == ()
