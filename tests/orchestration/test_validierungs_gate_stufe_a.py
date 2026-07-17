"""Tests für `app.orchestration.validierungs_gate_stufe_a` (Story S-060).

Covers (lernschleife): AC4, AC7

Belegt die Verdrahtung zwischen der Trial-Registry (S-059,
`app.db.trial_registry`) und dem reinen Stufe-A-Berechnungskern
(`app.domain.lernschleife.stage_a`): `pruefe_stufe_a` liest `n_trials`
tatsächlich aus der DB statt einen festen Wert anzunehmen (AC7 "korrigiert
um die aus der Trial-Registry bekannte Anzahl aller getesteten
Regelvarianten"), und reicht eine zu kleine Stichprobe unverändert durch
(AC4, keine eigene Zweit-Logik in der Orchestration-Schicht).

SQLite (in-memory) reicht aus — reine Lese-Aggregation über bereits
persistierte `TrialRegistry`-Zeilen, kein Postgres-spezifisches Konstrukt
involviert (analog `tests/orchestration/test_datasource_query.py`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.lernschleife import TradeErgebnis
from app.db.base import Base
from app.db.trial_registry import registriere_trial
from app.orchestration.validierungs_gate_stufe_a import pruefe_stufe_a

_START = datetime(2024, 1, 1, tzinfo=UTC)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _trades(n: int) -> list[TradeErgebnis]:
    # Deutliche Streuung (±4.0) um Basis 1.0: bei sehr niedriger Streuung
    # sättigt die DSR bei T=150 nahe 1.0 und wird unempfindlich gegenüber
    # `n_trials` (siehe `test_stage_a.py::_stabile_trades_mit_streuung`).
    return [
        TradeErgebnis(
            datum=_START + timedelta(days=i * 5),
            rendite_pct=Decimal("5.0") if i % 2 == 0 else Decimal("-3.0"),
        )
        for i in range(n)
    ]


def test_pruefe_stufe_a_liest_n_trials_aus_der_trial_registry() -> None:
    """@trace lernschleife#AC7 — `n_trials` kommt aus der Trial-Registry
    (registrierte Varianten dieser Hypothese), nicht aus einem
    Konstanten-Default."""
    session = _session()
    hypothesis_id = uuid.uuid4()
    for variant_hash in ("a", "b", "c"):
        registriere_trial(
            session, hypothesis_id=hypothesis_id, variant_hash=variant_hash, params={}
        )

    report_mit_registry = pruefe_stufe_a(session, hypothesis_id=hypothesis_id, trades=_trades(150))

    # dieselbe Hypothese, aber ohne Registry-Einträge -> weniger Trials ->
    # (bei sonst identischen Renditen) eine höhere DSR.
    andere_session = _session()
    andere_hypothesis_id = uuid.uuid4()
    registriere_trial(
        andere_session,
        hypothesis_id=andere_hypothesis_id,
        variant_hash="einzige",
        params={},
    )
    report_wenig_registry = pruefe_stufe_a(
        andere_session, hypothesis_id=andere_hypothesis_id, trades=_trades(150)
    )

    assert report_mit_registry.dsr is not None
    assert report_wenig_registry.dsr is not None
    assert report_mit_registry.dsr < report_wenig_registry.dsr


def test_pruefe_stufe_a_reicht_kleine_stichprobe_unveraendert_durch() -> None:
    """@trace lernschleife#AC4 — die Orchestration-Schicht dupliziert die
    Stichproben-Gate-Logik nicht neu, sondern reicht das Ergebnis des
    Berechnungskerns durch."""
    session = _session()
    hypothesis_id = uuid.uuid4()
    registriere_trial(session, hypothesis_id=hypothesis_id, variant_hash="a", params={})

    report = pruefe_stufe_a(session, hypothesis_id=hypothesis_id, trades=_trades(10))

    assert report.ergebnis == "nicht_bewertet"
    assert report.dsr is None
