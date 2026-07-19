"""Schema-/Constraint-Tests für `hybrid_entscheid` (Story S-080,
`docs/specs/frontend-cockpit.md` AC29/AC30; Migration `827b9dcc737c`;
→ BR-141).

Covers (frontend-cockpit): AC29, AC30

**BR-019/BR-141-Sperr-Test (MVP-Live-Sperre, AC30 "Die MVP-Live-Sperre
bleibt unangetastet — eine Bestätigung löst im MVP ausschliesslich
simulierte Orders aus"):** `test_mode_echt_wird_vom_db_check_abgelehnt`
belegt, dass `mode="echt"` bereits auf Schema-Ebene (DB-CHECK, nicht erst
Laufzeit-Prüfung) unmöglich ist — SQLite (in-memory) erzwingt `CHECK`
-Constraints identisch zu Postgres (anders als `PRAGMA foreign_keys`,
das explizit aktiviert werden müsste). Ergänzend: `richtung`/`status`
CHECK-Constraints; `groesse > 0` (`ck_hybrid_entscheid_groesse_positive`,
DBA-Review Iteration 2, Suggestion, analog `position.menge`)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import HybridEntscheid, Instrument

#: SQLite-Falle: eine rein numerische Hex-Zeichenkette bekommt unter
#: SQLite NUMERIC-Spalten-Affinität zugewiesen und wird beim Lesen
#: stillschweigend zu einem Float konvertiert — deshalb `uuid.uuid4()`
#: statt eines lesbaren Literals (siehe `tests/api/test_control_route.py`).
_TITEL_ID = uuid.uuid4()


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        Instrument(
            id=_TITEL_ID, symbol="ROG", name="Roche Holding AG", asset_class_id=1, currency="CHF"
        )
    )
    session.commit()
    return session


def _basis_werte() -> dict[str, object]:
    from datetime import UTC, datetime
    from decimal import Decimal

    return {
        "instrument_id": _TITEL_ID,
        "richtung": "kauf",
        "groesse": Decimal("5"),
        "vorgeschlagene_order": "Market-Buy 5 Stk. Roche Holding AG",
        "frist": datetime(2026, 7, 22, 16, 0, tzinfo=UTC),
        "begruendung": "Begründung",
    }


def test_mode_echt_wird_vom_db_check_abgelehnt() -> None:
    """@trace frontend-cockpit#AC30 — `mode="echt"` verletzt
    `ck_hybrid_entscheid_mode` (→ BR-141/BR-019): die MVP-Live-Sperre gilt
    bereits auf Schema-Ebene, nicht erst als Laufzeit-Prüfung."""
    session = _session()
    werte = _basis_werte() | {"mode": "echt"}

    with pytest.raises(IntegrityError):
        session.execute(insert(HybridEntscheid).values(**werte))
        session.commit()


def test_mode_simuliert_wird_akzeptiert() -> None:
    """@trace frontend-cockpit#AC30 — `mode="simuliert"` (der einzige laut
    Schema zulässige Wert) wird akzeptiert."""
    session = _session()
    werte = _basis_werte() | {"mode": "simuliert"}

    session.execute(insert(HybridEntscheid).values(**werte))
    session.commit()

    zeile = session.query(HybridEntscheid).one()
    assert zeile.mode == "simuliert"


def test_richtung_ausserhalb_kauf_verkauf_wird_abgelehnt() -> None:
    """@trace frontend-cockpit#AC29 — `richtung` ausserhalb {kauf,
    verkauf} verletzt `ck_hybrid_entscheid_richtung`."""
    session = _session()
    werte = _basis_werte() | {"mode": "simuliert", "richtung": "halten"}

    with pytest.raises(IntegrityError):
        session.execute(insert(HybridEntscheid).values(**werte))
        session.commit()


def test_status_ausserhalb_erlaubter_werte_wird_abgelehnt() -> None:
    """@trace frontend-cockpit#AC30 — `status` ausserhalb {offen,
    bestaetigt, abgelehnt} verletzt `ck_hybrid_entscheid_status`."""
    session = _session()
    werte = _basis_werte() | {"mode": "simuliert", "status": "unbekannt"}

    with pytest.raises(IntegrityError):
        session.execute(insert(HybridEntscheid).values(**werte))
        session.commit()


@pytest.mark.parametrize("groesse", ["0", "-1"])
def test_groesse_null_oder_negativ_wird_abgelehnt(groesse: str) -> None:
    """@trace frontend-cockpit#AC30 — `groesse <= 0` verletzt
    `ck_hybrid_entscheid_groesse_positive` (DBA-Review Iteration 2,
    Suggestion, analog `position.menge`/`ck_position_menge_non_negative`
    -Konvention, hier strikt positiv statt >= 0)."""
    from decimal import Decimal

    session = _session()
    werte = _basis_werte() | {"mode": "simuliert", "groesse": Decimal(groesse)}

    with pytest.raises(IntegrityError):
        session.execute(insert(HybridEntscheid).values(**werte))
        session.commit()


def test_status_default_ist_offen() -> None:
    """@trace frontend-cockpit#AC29 — ohne explizite Angabe ist der
    Default-Status `offen` (AC29 "offene ... Entscheide")."""
    session = _session()
    session.add(HybridEntscheid(**_basis_werte(), mode="simuliert"))
    session.commit()

    zeile = session.query(HybridEntscheid).one()
    assert zeile.status == "offen"
