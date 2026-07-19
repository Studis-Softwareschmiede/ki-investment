"""Tests für `SqlAlchemyGateErgebnisRepository` (Story S-068, Spec
`docs/specs/frontend-cockpit.md` AC8; erweitert um AC24, Story S-078).

Covers (frontend-cockpit): AC8, AC24

Deckt: Cold-Start (kein `gate_result` vorhanden → `None`, kein Absturz),
"neueste Zeile über ALLE Trials hinweg gewinnt" (nicht nur je Trial), die
korrekte Feld-Übernahme (`ampel`, `ermittelt_am`) sowie (AC24, S-078) die
`min_trl`-Durchreichung: gesetzt sobald ein Stufe-B-Report vorliegt, sonst
`None` (Stufe A allein)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.gate_result_repository import SqlAlchemyGateErgebnisRepository
from app.contracts.lernschleife import StufeAReport, StufeBReport
from app.db.base import Base
from app.db.gate_result import registriere_gate_ergebnis
from app.db.models import GateResult


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


def test_letztes_ergebnis_ohne_jede_gate_auswertung_ist_none() -> None:
    """@trace frontend-cockpit#AC8 — Cold-Start: keine `gate_result`-Zeile
    existiert (kein Trial ausgewertet) → `None`, kein Absturz."""
    repository = SqlAlchemyGateErgebnisRepository(_session())

    assert repository.letztes_ergebnis() is None


def test_letztes_ergebnis_liefert_die_neueste_zeile_ueber_alle_trials_hinweg() -> None:
    """@trace frontend-cockpit#AC8 — mehrere Trials mit je eigener
    Gate-Historie: `letztes_ergebnis()` liefert die zeitlich neueste Zeile
    insgesamt (nicht nur je Trial), unabhängig davon, zu welchem Trial sie
    gehört. `created_at` wird hier explizit gesetzt (statt über den
    `server_default`), damit der Test nicht von der Sekunden-Auflösung von
    SQLites `CURRENT_TIMESTAMP` abhängt (unter Postgres Mikrosekunden-
    genau — reines Test-Determinismus-Anliegen, kein Produktionsverhalten)."""
    session = _session()
    aelter = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    neuer = datetime(2026, 7, 15, 9, 0, tzinfo=UTC)
    session.add(
        GateResult(
            id=uuid.uuid4(),
            trial_id=uuid.uuid4(),
            stufe="A_historisch",
            ampel="gelb",
            created_at=aelter,
        )
    )
    session.add(
        GateResult(
            id=uuid.uuid4(),
            trial_id=uuid.uuid4(),
            stufe="B_paper",
            ampel="gruen",
            created_at=neuer,
        )
    )
    session.commit()

    repository = SqlAlchemyGateErgebnisRepository(session)
    ergebnis = repository.letztes_ergebnis()

    assert ergebnis is not None
    assert ergebnis.ampel == "gruen"
    # SQLite speichert `DateTime(timezone=True)` ohne tzinfo (Speicher-
    # Eigenheit, unter Postgres bleibt die Zeitzone erhalten) — Vergleich
    # daher naiv.
    assert ergebnis.ermittelt_am.replace(tzinfo=UTC) == neuer


def test_letztes_ergebnis_uebernimmt_rote_ampel_unverfaelscht() -> None:
    """@trace frontend-cockpit#AC8 — auch eine 🔴-Ampel (durchgefallen)
    wird unverändert durchgereicht (keine implizite Umdeutung)."""
    session = _session()
    registriere_gate_ergebnis(
        session,
        trial_id=uuid.uuid4(),
        ampel="rot",
        stufe_a_report=_stufe_a_report(ergebnis="durchgefallen"),
    )

    repository = SqlAlchemyGateErgebnisRepository(session)
    ergebnis = repository.letztes_ergebnis()

    assert ergebnis is not None
    assert ergebnis.ampel == "rot"


def test_letztes_ergebnis_ist_ohne_stufe_b_report_min_trl_none() -> None:
    """@trace frontend-cockpit#AC24 — nur Stufe A ausgewertet (kein
    `StufeBReport`): `min_trl` bleibt `None` (deckungsgleich mit "Stufe B
    nicht aktiv", AC24)."""
    session = _session()
    registriere_gate_ergebnis(
        session,
        trial_id=uuid.uuid4(),
        ampel="rot",
        stufe_a_report=_stufe_a_report(ergebnis="durchgefallen"),
    )

    repository = SqlAlchemyGateErgebnisRepository(session)
    ergebnis = repository.letztes_ergebnis()

    assert ergebnis is not None
    assert ergebnis.min_trl is None


def test_letztes_ergebnis_liefert_min_trl_wenn_stufe_b_report_vorliegt() -> None:
    """@trace frontend-cockpit#AC24 — liegt ein `StufeBReport` mit
    `mintrl_restlaufzeit` vor, reicht das Repository die persistierten
    Tage (`gate_result.min_trl`) unverändert durch (nicht-runder Wert,
    python/R14: 42 Tage + 8h ist kein binär-exakter Bruchteil eines
    Jahres)."""
    session = _session()
    registriere_gate_ergebnis(
        session,
        trial_id=uuid.uuid4(),
        ampel="gruen",
        stufe_a_report=_stufe_a_report(),
        stufe_b_report=_stufe_b_report(mintrl_restlaufzeit=timedelta(days=42, hours=8)),
    )

    repository = SqlAlchemyGateErgebnisRepository(session)
    ergebnis = repository.letztes_ergebnis()

    assert ergebnis is not None
    assert ergebnis.min_trl == Decimal("42.33")
