"""Tests für die No-Evidence-No-Trade-Prüfung (Story S-014).

Covers (llm-grounding): AC6, AC10

`app.domain.no_evidence_no_trade.pruefe_evidenzlage` prüft die 5
Analysekategorien eines bereits geerdeten `AnalyseScores`-DTOs (Ergebnis
von Grounding + Cross-Check, S-012/S-013): fehlt einer Kategorie die
Datengrundlage (Score `"fehlt"`), wird der gesamte Titel übersprungen —
der fehlende Score wird NIE durch eine LLM-Schätzung ersetzt (AC6) — und
der Übersprung protokolliert (AC10, geprüft über
`app.core.audit_log.alle_eintraege`).
"""

from __future__ import annotations

import pytest

from app.contracts.llm_grounding import AnalyseScores
from app.core.audit_log import alle_eintraege, reset_fuer_tests
from app.domain.no_evidence_no_trade import pruefe_evidenzlage


@pytest.fixture(autouse=True)
def _audit_log_isolieren():
    """Isoliert die in-memory Audit-Historie zwischen Testfällen."""
    reset_fuer_tests()
    yield
    reset_fuer_tests()


def _vollstaendige_scores(**overrides: float | str) -> AnalyseScores:
    basis: dict[str, float | str] = {
        "fundamental": 7.0,
        "technisch": 6.0,
        "qualitativ": 5.0,
        "makro": 8.0,
        "risiko": 4.0,
    }
    basis.update(overrides)
    return AnalyseScores(**basis)


def test_pruefe_evidenzlage_akzeptiert_vollstaendige_scores() -> None:
    """@trace llm-grounding#AC6 — trägt jede der 5 Kategorien einen echten
    Score (kein "fehlt"), gilt die Evidenzlage als vollständig; der Titel
    wird NICHT übersprungen und es entsteht kein Protokolleintrag."""
    scores = _vollstaendige_scores()

    ergebnis = pruefe_evidenzlage(scores, titel="Acme Corp")

    assert ergebnis.status == "vollstaendig"
    assert ergebnis.fehlende_kategorien == ()
    assert ergebnis.protokoll_eintrag is None
    assert alle_eintraege() == ()


def test_pruefe_evidenzlage_ueberspringt_titel_bei_fehlender_kategorie() -> None:
    """@trace llm-grounding#AC6,AC10 — fehlt einer Kategorie die
    Datengrundlage (Score "fehlt"), wird der Titel übersprungen statt die
    Kategorie zu schätzen; der Übersprung wird protokolliert (AC10)."""
    scores = _vollstaendige_scores(risiko="fehlt")

    ergebnis = pruefe_evidenzlage(scores, titel="Acme Corp")

    assert ergebnis.status == "uebersprungen"
    assert ergebnis.fehlende_kategorien == ("risiko",)
    assert ergebnis.protokoll_eintrag is not None
    assert ergebnis.protokoll_eintrag.grund == "keine_evidenz"

    eintraege = alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "keine_evidenz"
    assert eintraege[0].kennzahl_typ == "risiko"
    assert "Acme Corp" in eintraege[0].detail


def test_pruefe_evidenzlage_ueberspringt_bei_mehreren_fehlenden_kategorien() -> None:
    """@trace llm-grounding#AC6 — fehlen mehrere Kategorien gleichzeitig,
    listet das Ergebnis ALLE fehlenden Kategorien (nicht nur die erste) —
    der Titel wird trotzdem nur einmal übersprungen/protokolliert."""
    scores = _vollstaendige_scores(technisch="fehlt", makro="fehlt")

    ergebnis = pruefe_evidenzlage(scores)

    assert ergebnis.status == "uebersprungen"
    assert ergebnis.fehlende_kategorien == ("technisch", "makro")
    assert len(alle_eintraege()) == 1


def test_pruefe_evidenzlage_ohne_titel_bleibt_auditierbar() -> None:
    """@trace llm-grounding#AC10 — auch ohne optionalen `titel`-Parameter
    entsteht ein vollständiger, auditierbarer Protokolleintrag (Grund,
    Zeitpunkt, betroffene Kategorie)."""
    scores = _vollstaendige_scores(fundamental="fehlt")

    ergebnis = pruefe_evidenzlage(scores)

    eintrag = ergebnis.protokoll_eintrag
    assert eintrag is not None
    assert eintrag.grund == "keine_evidenz"
    assert eintrag.kennzahl_typ == "fundamental"
    assert eintrag.zeitpunkt is not None
