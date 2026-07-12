"""Tests für das Audit-Protokoll des LLM-Grounding-Querschnitts (Story S-013).

Covers (llm-grounding): AC10

`app.core.audit_log.protokolliere`/`alle_eintraege` sind der gemeinsame
Sammelpunkt für Ablehnungen entlang des Grounding-Pfads (Grund, Zeitpunkt,
betroffene Kennzahl/Quelle, AC10) — genutzt sowohl vom Grounding-Gate
(S-012-Ablehnungspfade, `tests/adapters/llm/test_grounding.py`) als auch
vom Cross-Check-Modul (S-013, `tests/adapters/llm/test_cross_check.py`).
Diese Tests decken das Modul isoliert.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contracts.llm_grounding import ProtokollEintrag
from app.core.audit_log import alle_eintraege, protokolliere, reset_fuer_tests


@pytest.fixture(autouse=True)
def _audit_log_isolieren():
    """Isoliert die in-memory Audit-Historie zwischen Testfällen."""
    reset_fuer_tests()
    yield
    reset_fuer_tests()


def _eintrag(**overrides: object) -> ProtokollEintrag:
    kwargs: dict[str, object] = {
        "zeitpunkt": datetime(2026, 7, 1, tzinfo=UTC),
        "grund": "schema_verletzung",
        "kennzahl_typ": "kgv",
        "quellen_id": "sec-form4-123",
        "detail": "Testfall.",
    }
    kwargs.update(overrides)
    return ProtokollEintrag(**kwargs)


def test_protokolliere_nimmt_eintrag_in_die_historie_auf() -> None:
    """@trace llm-grounding#AC10 — ein protokollierter Eintrag erscheint
    unverändert in `alle_eintraege()`."""
    eintrag = _eintrag()

    protokolliere(eintrag)

    assert alle_eintraege() == (eintrag,)


def test_protokolliere_haengt_mehrere_eintraege_in_reihenfolge_an() -> None:
    """@trace llm-grounding#AC10 — mehrere Protokolleinträge (z.B. aus
    verschiedenen Ablehnungsgründen) werden alle behalten, in der
    Reihenfolge ihres Eintreffens."""
    erster = _eintrag(grund="schema_verletzung")
    zweiter = _eintrag(grund="cross_check_abweichung", kennzahl_typ="kurs")

    protokolliere(erster)
    protokolliere(zweiter)

    assert alle_eintraege() == (erster, zweiter)


def test_eintrag_enthaelt_grund_zeitpunkt_kennzahl_und_quelle() -> None:
    """@trace llm-grounding#AC10 — ein Protokolleintrag trägt genau die von
    der Spec geforderten Auditierbarkeits-Felder: Grund, Zeitpunkt,
    betroffene Kennzahl, betroffene Quelle."""
    eintrag = _eintrag(
        grund="quelle_nicht_verfuegbar", kennzahl_typ="marktkapitalisierung", quellen_id="fred-xyz"
    )

    protokolliere(eintrag)

    (gespeichert,) = alle_eintraege()
    assert gespeichert.grund == "quelle_nicht_verfuegbar"
    assert gespeichert.kennzahl_typ == "marktkapitalisierung"
    assert gespeichert.quellen_id == "fred-xyz"
    assert gespeichert.zeitpunkt is not None


def test_alle_eintraege_liefert_unveraenderliche_kopie() -> None:
    """@trace llm-grounding#AC10 — `alle_eintraege()` liefert ein Tupel
    (nicht die interne Liste) — Aufrufer können die Audit-Historie nicht
    von außen mutieren."""
    protokolliere(_eintrag())

    ergebnis = alle_eintraege()

    assert isinstance(ergebnis, tuple)
