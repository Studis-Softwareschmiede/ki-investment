"""Tests für `app.db.gate_result` (Story S-062).

Covers (lernschleife): AC10, AC11, AC12

`registriere_gate_ergebnis` persistiert die vom reinen Domain-Kern
(`app.domain.lernschleife.gate.leite_ampel_ab`) abgeleitete Ampel samt
Stufe-A-/Stufe-B-Metriken (AC10); `gate_ergebnisse_fuer_trial` liest die
volle Audit-Historie eines Trials (NFR „Nachvollziehbarkeit"). AC11/AC12
selbst sind reine Domain-Logik (`tests/domain/lernschleife/test_gate.py`)
— hier wird nur belegt, dass die dort abgeleiteten Werte unverfälscht in
`gate_result` ankommen (inkl. `min_trl`-Umrechnung von `timedelta` in Tage,
→ BR-120)."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.lernschleife import StufeAReport, StufeBReport
from app.db.base import Base
from app.db.gate_result import gate_ergebnisse_fuer_trial, registriere_gate_ergebnis


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _stufe_a_report(**overrides) -> StufeAReport:
    defaults = dict(
        hypothesis_id=uuid.uuid4(),
        n_trades=150,
        embargo_tage=30,
        walk_forward_effizienz=Decimal("0.9"),
        dsr=Decimal("0.8"),
        ergebnis="bestanden",
        begruendung="Stufe A bestanden.",
    )
    defaults.update(overrides)
    return StufeAReport(**defaults)


def _stufe_b_report(**overrides) -> StufeBReport:
    defaults = dict(
        hypothesis_id=uuid.uuid4(),
        n_trades=200,
        psr=Decimal("0.97"),
        psr_schwelle=Decimal("0.95"),
        psr_bestanden=True,
        mintrl_restlaufzeit=timedelta(days=42),
        begruendung="Stufe B bestanden.",
    )
    defaults.update(overrides)
    return StufeBReport(**defaults)


def test_registriere_gate_ergebnis_nach_stufe_a_speichert_a_historisch_ohne_psr() -> None:
    """@trace lernschleife#AC10 — eine Auswertung ohne `stufe_b_report`
    (Stufe A allein, 🟡- oder 🔴-Fall) wird als `"A_historisch"` gespeichert;
    `psr`/`min_trl` bleiben `NULL`."""
    session = _session()
    trial_id = uuid.uuid4()
    stufe_a = _stufe_a_report(ergebnis="bestanden")

    eintrag = registriere_gate_ergebnis(
        session, trial_id=trial_id, ampel="gelb", stufe_a_report=stufe_a
    )

    assert eintrag.trial_id == trial_id
    assert eintrag.stufe == "A_historisch"
    assert eintrag.ampel == "gelb"
    assert eintrag.sample_size == 150
    assert eintrag.wfe == Decimal("0.9")
    assert eintrag.dsr == Decimal("0.8")
    assert eintrag.psr is None
    assert eintrag.min_trl is None
    assert eintrag.begruendung == "Stufe A bestanden."


def test_registriere_gate_ergebnis_nach_stufe_b_speichert_b_paper_mit_psr_und_min_trl() -> None:
    """@trace lernschleife#AC10,AC9 — sobald ein `stufe_b_report` vorliegt,
    wird `"B_paper"` gespeichert; `min_trl` ist die in Tage umgerechnete
    `mintrl_restlaufzeit` (→ BR-120)."""
    session = _session()
    trial_id = uuid.uuid4()
    stufe_a = _stufe_a_report(ergebnis="bestanden")
    stufe_b = _stufe_b_report(psr_bestanden=True, mintrl_restlaufzeit=timedelta(days=42))

    eintrag = registriere_gate_ergebnis(
        session,
        trial_id=trial_id,
        ampel="gruen",
        stufe_a_report=stufe_a,
        stufe_b_report=stufe_b,
    )

    assert eintrag.stufe == "B_paper"
    assert eintrag.ampel == "gruen"
    assert eintrag.psr == Decimal("0.97")
    assert eintrag.min_trl == Decimal("42")
    assert eintrag.begruendung == "Stufe B bestanden."


def test_registriere_gate_ergebnis_min_trl_none_wenn_bereits_erreicht() -> None:
    """@trace lernschleife#AC9 — `mintrl_restlaufzeit=None` (MinTRL bereits
    erreicht/überschritten, S-061-Konvention `timedelta(0)` bzw. `None` bei
    degenerierter Verteilung) bleibt als `NULL` erhalten, kein Absturz."""
    session = _session()
    stufe_a = _stufe_a_report(ergebnis="bestanden")
    stufe_b = _stufe_b_report(mintrl_restlaufzeit=None)

    eintrag = registriere_gate_ergebnis(
        session,
        trial_id=uuid.uuid4(),
        ampel="gruen",
        stufe_a_report=stufe_a,
        stufe_b_report=stufe_b,
    )

    assert eintrag.min_trl is None


def test_gate_ergebnisse_fuer_trial_liefert_die_volle_historie_aeltestes_zuerst() -> None:
    """@trace lernschleife#AC10 — NFR „Nachvollziehbarkeit": alle
    Gate-Auswertungen eines Trials (A- und spätere B-Auswertung) sind
    chronologisch lesbar."""
    session = _session()
    trial_id = uuid.uuid4()
    stufe_a = _stufe_a_report(ergebnis="bestanden")
    stufe_b = _stufe_b_report(psr_bestanden=True)

    erste = registriere_gate_ergebnis(
        session, trial_id=trial_id, ampel="gelb", stufe_a_report=stufe_a
    )
    zweite = registriere_gate_ergebnis(
        session,
        trial_id=trial_id,
        ampel="gruen",
        stufe_a_report=stufe_a,
        stufe_b_report=stufe_b,
    )
    registriere_gate_ergebnis(
        session, trial_id=uuid.uuid4(), ampel="rot", stufe_a_report=_stufe_a_report()
    )

    ergebnis = gate_ergebnisse_fuer_trial(session, trial_id=trial_id)

    assert [e.id for e in ergebnis] == [erste.id, zweite.id]
