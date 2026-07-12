"""Tests für die LLM-Grounding-Verträge (Story S-012 + S-013).

Covers (llm-grounding): AC1, AC3, AC4, AC5, AC10

`app.contracts.llm_grounding` bildet die Verträge aus
`docs/specs/llm-grounding.md` ab. Diese Tests decken auf DTO-Ebene AC1
(`AnalyseFakt` verweigert die Instanziierung ohne Quellen-ID/Timestamp),
AC3 (`AnalyseOutput` wird gegen ein festes JSON-Schema validiert — Score je
Kategorie 0–10 oder "fehlt", Pflichtfelder, kein unbekanntes Zusatzfeld)
sowie die S-013-Cross-Check-/Audit-Verträge: AC4 (`Abweichung`,
`CrossCheckErgebnis`), AC5 (`ToleranzKonfig`) und AC10 (`ProtokollEintrag`).
Die End-to-End-Prüfung eines rohen (dict-)Analyse-Output-Kandidaten inkl.
AC2 (Input-Bindung) liegt in `tests/adapters/llm/test_grounding.py`; das
tatsächliche Verhalten des Cross-Checks (AC4/AC5) und des Audit-Protokolls
(AC10) liegt in `tests/adapters/llm/test_cross_check.py` und
`tests/core/test_audit_log.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.llm_grounding import (
    Abweichung,
    AnalyseFakt,
    AnalyseInput,
    AnalyseOutput,
    AnalyseScores,
    CrossCheckErgebnis,
    GroundingErgebnis,
    Originalquelle,
    ProtokollEintrag,
    ToleranzKonfig,
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
    assert fakt.wert == Decimal("12.5")


def test_analysefakt_wert_ist_decimal_ohne_float_drift() -> None:
    """@trace llm-grounding#AC1 — `wert` ist `Decimal` (architecture.md P7);
    ein nicht binär-exakter Float-Input wird verlustfrei über seine
    String-Repräsentation koerziert, nicht über den Binärwert."""
    fakt = AnalyseFakt(**dict(VALID_FAKT_KWARGS, wert=0.1))
    assert isinstance(fakt.wert, Decimal)
    assert fakt.wert == Decimal("0.1")


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


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": "geerdet"},  # geerdet ohne output
        {"status": "geerdet", "grund": "schema_verletzung"},  # geerdet mit grund
        {"status": "abgelehnt"},  # abgelehnt ohne grund
    ],
)
def test_groundingergebnis_erzwingt_status_invariante(kwargs: dict) -> None:
    """@trace llm-grounding#AC3 — das Ergebnis-DTO des Gates gehört zum festen
    Ergebnisvertrag: 'geerdet' verlangt output (kein grund), 'abgelehnt'
    verlangt grund (kein output) — erzwungen im Modell, nicht nur im
    Aufrufer (`pruefe_grounding`)."""
    if kwargs["status"] == "geerdet" and "grund" in kwargs:
        kwargs = dict(kwargs, output=AnalyseOutput(**_valid_output_kwargs()))
    with pytest.raises(ValidationError):
        GroundingErgebnis(**kwargs)


def test_toleranzkonfig_akzeptiert_absolut_und_relativ() -> None:
    """@trace llm-grounding#AC5 — eine Toleranzschwelle je Kennzahl-Typ
    unterscheidet absolute und relative Abweichung."""
    absolut = ToleranzKonfig(kennzahl_typ="kurs", typ="absolut", schwelle=2.0)
    relativ = ToleranzKonfig(kennzahl_typ="kgv", typ="relativ", schwelle=0.02)
    assert absolut.typ == "absolut"
    assert relativ.typ == "relativ"


def test_toleranzkonfig_lehnt_negative_schwelle_ab() -> None:
    """@trace llm-grounding#AC5 — eine negative Toleranzschwelle ist keine
    sinnvolle Konfiguration und wird strukturell abgelehnt."""
    with pytest.raises(ValidationError):
        ToleranzKonfig(kennzahl_typ="kgv", typ="relativ", schwelle=-0.01)


def test_originalquelle_traegt_kennzahl_typ_und_wert() -> None:
    """@trace llm-grounding#AC4 — die Originalquelle für den Cross-Check
    trägt Kennzahl-Typ, Quellen-ID und den tatsächlichen Wert."""
    quelle = Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=12.4)
    assert isinstance(quelle.wert, Decimal)
    assert quelle.wert == Decimal("12.4")


def test_abweichung_traegt_output_quelle_abweichung_und_toleranz() -> None:
    """@trace llm-grounding#AC4 — eine Abweichung dokumentiert Output-Wert,
    Quellwert, gemessene Abweichung und die angewendete Toleranz."""
    abweichung = Abweichung(
        kennzahl_typ="kgv", wert_output=12.5, wert_quelle=12.4, abweichung=0.1, toleranz=0.02
    )
    assert abweichung.wert_output == Decimal("12.5")
    assert abweichung.wert_quelle == Decimal("12.4")
    assert abweichung.abweichung == Decimal("0.1")  # Decimal, keine Float-Drift (P7)
    assert isinstance(abweichung.toleranz, Decimal)


def test_crosscheckergebnis_verworfen_traegt_protokoll_eintrag() -> None:
    """@trace llm-grounding#AC4,AC10 — ein verworfenes Cross-Check-Ergebnis
    trägt einen Protokolleintrag mit Grund, Zeitpunkt und betroffener
    Kennzahl/Quelle."""
    ergebnis = CrossCheckErgebnis(
        status="verworfen",
        abweichungen=[
            Abweichung(
                kennzahl_typ="kgv",
                wert_output=100.0,
                wert_quelle=50.0,
                abweichung=1.0,
                toleranz=0.05,
            )
        ],
        protokoll_eintrag=ProtokollEintrag(
            zeitpunkt=datetime(2026, 7, 1, tzinfo=UTC),
            grund="cross_check_abweichung",
            kennzahl_typ="kgv",
            quellen_id="sec-form4-123",
            detail="Abweichung über Toleranz.",
        ),
    )
    assert ergebnis.status == "verworfen"
    assert ergebnis.protokoll_eintrag is not None
    assert ergebnis.protokoll_eintrag.grund == "cross_check_abweichung"


def test_protokolleintrag_erlaubt_kennzahl_typ_und_quellen_id_optional() -> None:
    """@trace llm-grounding#AC10 — ein Protokolleintrag ohne bekannte
    Kennzahl/Quelle (z.B. eine schema-weite Ablehnung) ist trotzdem
    gültig — Grund, Zeitpunkt und Detail bleiben Pflicht."""
    eintrag = ProtokollEintrag(
        zeitpunkt=datetime(2026, 7, 1, tzinfo=UTC),
        grund="schema_verletzung",
        detail="Pflichtfeld fehlt.",
    )
    assert eintrag.kennzahl_typ is None
    assert eintrag.quellen_id is None


def test_protokolleintrag_lehnt_unbekannten_grund_ab() -> None:
    """@trace llm-grounding#AC10 — `grund` ist auf das feste
    `ProtokollGrund`-Vokabular beschränkt (kein freier String)."""
    with pytest.raises(ValidationError):
        ProtokollEintrag(
            zeitpunkt=datetime(2026, 7, 1, tzinfo=UTC),
            grund="irgendwas-unbekanntes",
            detail="x",
        )
