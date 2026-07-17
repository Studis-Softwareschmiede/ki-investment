"""Tests für `app.db.trial_registry` (Story S-059).

Covers (lernschleife): AC3

AC3: „Jede an das Gate übergebene Regelvariante wird in einer
Trial-Registry gezählt — auch verworfene; ohne diese Zählung ist die
Deflated Sharpe Ratio ungültig. Abgelehnte Regeln werden archiviert, nie
gelöscht." `registriere_trial()`/`archiviere_trial()` sind der einzige
Schreibpfad — keine Delete-Funktion existiert im Modul (append-only,
App-Schicht). Der Postgres-spezifische `BEFORE DELETE`-Trigger (DB-Schicht,
BR-118) ist unter SQLite nicht abbildbar, siehe
`tests/db/test_trial_registry_migration.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.trial_registry import (
    anzahl_trials,
    archiviere_trial,
    registriere_trial,
    trials_fuer_hypothese,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_registriere_trial_persists_a_row() -> None:
    """@trace lernschleife#AC3 — eine an das Gate übergebene Regelvariante
    wird als Zeile in der Trial-Registry angelegt."""
    session = _session()
    hypothesis_id = uuid.uuid4()

    eintrag = registriere_trial(
        session,
        hypothesis_id=hypothesis_id,
        variant_hash="hash-1",
        params={"schwelle": 0.5},
    )

    assert eintrag.id is not None
    assert eintrag.hypothesis_id == hypothesis_id
    assert eintrag.variant_hash == "hash-1"
    assert eintrag.params == {"schwelle": 0.5}
    assert eintrag.archived is False


def test_registriere_trial_zaehlt_auch_mehrere_varianten_derselben_hypothese() -> None:
    """@trace lernschleife#AC3 — jede getestete Variante wird gezählt (Basis
    der künftigen DSR-Korrektur, AC7)."""
    session = _session()
    hypothesis_id = uuid.uuid4()

    registriere_trial(session, hypothesis_id=hypothesis_id, variant_hash="a", params={})
    registriere_trial(session, hypothesis_id=hypothesis_id, variant_hash="b", params={})
    registriere_trial(session, hypothesis_id=hypothesis_id, variant_hash="c", params={})

    assert anzahl_trials(session, hypothesis_id=hypothesis_id) == 3


def test_anzahl_trials_zaehlt_archivierte_varianten_mit() -> None:
    """@trace lernschleife#AC3 — „auch verworfene" wird gezählt; Archivieren
    entfernt die Variante nicht aus der Zählung."""
    session = _session()
    hypothesis_id = uuid.uuid4()
    verworfen = registriere_trial(
        session, hypothesis_id=hypothesis_id, variant_hash="verworfen", params={}
    )
    registriere_trial(session, hypothesis_id=hypothesis_id, variant_hash="laeuft", params={})

    archiviere_trial(session, trial_id=verworfen.id)

    assert anzahl_trials(session, hypothesis_id=hypothesis_id) == 2


def test_archiviere_trial_setzt_archived_ohne_die_zeile_zu_loeschen() -> None:
    """@trace lernschleife#AC3 — „Abgelehnte Regeln werden archiviert, nie
    gelöscht": die Zeile bleibt bestehen, nur `archived` wechselt."""
    session = _session()
    hypothesis_id = uuid.uuid4()
    eintrag = registriere_trial(
        session, hypothesis_id=hypothesis_id, variant_hash="hash-1", params={"x": 1}
    )

    archiviere_trial(session, trial_id=eintrag.id)

    gefunden = trials_fuer_hypothese(session, hypothesis_id=hypothesis_id)
    assert len(gefunden) == 1
    assert gefunden[0].id == eintrag.id
    assert gefunden[0].archived is True
    assert gefunden[0].variant_hash == "hash-1"


def test_archiviere_trial_unbekannte_id_wirft_value_error() -> None:
    """@trace lernschleife#AC3 — kein stilles No-Op bei nicht existierendem
    Trial (Programmierfehler-Schutz)."""
    session = _session()

    with pytest.raises(ValueError):
        archiviere_trial(session, trial_id=uuid.uuid4())


def test_trials_fuer_hypothese_liefert_nur_die_eigene_hypothese_aeltestes_zuerst() -> None:
    """@trace lernschleife#AC3 — Varianten sind je Hypothese isoliert und
    chronologisch (älteste zuerst) lesbar (Audit-Historie)."""
    session = _session()
    hypothesis_id = uuid.uuid4()
    andere_hypothesis_id = uuid.uuid4()

    erste = registriere_trial(
        session,
        hypothesis_id=hypothesis_id,
        variant_hash="a",
        params={},
        getestet_am=datetime(2026, 1, 1, tzinfo=UTC),
    )
    zweite = registriere_trial(
        session,
        hypothesis_id=hypothesis_id,
        variant_hash="b",
        params={},
        getestet_am=datetime(2026, 1, 2, tzinfo=UTC),
    )
    registriere_trial(session, hypothesis_id=andere_hypothesis_id, variant_hash="c", params={})

    ergebnis = trials_fuer_hypothese(session, hypothesis_id=hypothesis_id)

    assert [eintrag.id for eintrag in ergebnis] == [erste.id, zweite.id]
