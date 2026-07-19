"""Tests für `app.db.hybrid_entscheide.entscheide` (Story S-080,
`docs/specs/frontend-cockpit.md` AC30).

Covers (frontend-cockpit): AC30

SQLite (in-memory) reicht aus — reiner SQLAlchemy-Schreibpfad (analog
`tests/db/test_asset_classes.py`). Belegt: Status-Übergang `offen` →
`bestaetigt`/`abgelehnt` + `entschieden_am` gesetzt; unbekannte/ungültige
`entscheid_id` → `None` (Router meldet 404); bereits entschiedene Zeile →
`EntscheidBereitsEntschiedenError` (Router meldet 409); `mode` bleibt
unverändert `"simuliert"` (BR-141, kein Aufrufer-Pfad ändert `mode`);
Lost-Update-Guard (DBA-Review Iteration 2) — der bedingte Lese-Pfad fordert
`with_for_update=True` an (SQLite selbst kennt kein echtes Zeilensperren,
siehe `test_position_repository.py`-Konvention: dort ebenfalls kein
Postgres-Nebenläufigkeitstest, da im Projekt keine Postgres-Testinfra
existiert — die Sperr-Anforderung wird deshalb hier als bedingter Pfad
(Aufruf-Parameter) belegt, nicht als echter Race)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.hybrid_entscheide import EntscheidBereitsEntschiedenError, entscheide
from app.db.models import HybridEntscheid, Instrument

#: SQLite-Falle: eine rein numerische Hex-Zeichenkette bekommt unter
#: SQLite NUMERIC-Spalten-Affinität zugewiesen und wird beim Lesen
#: stillschweigend zu einem Float konvertiert — deshalb `uuid.uuid4()`
#: statt eines lesbaren Literals (siehe `tests/api/test_control_route.py`).
_TITEL_ID = uuid.uuid4()
_ENTSCHEID_ID = uuid.uuid4()
_ENTSCHEID_ID_STR = str(_ENTSCHEID_ID)


def _session_mit_offenem_entscheid() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        Instrument(
            id=_TITEL_ID, symbol="ROG", name="Roche Holding AG", asset_class_id=1, currency="CHF"
        )
    )
    session.add(
        HybridEntscheid(
            id=_ENTSCHEID_ID,
            instrument_id=_TITEL_ID,
            richtung="kauf",
            groesse=Decimal("5"),
            vorgeschlagene_order="Market-Buy 5 Stk. Roche Holding AG",
            frist=datetime(2026, 7, 22, 16, 0, tzinfo=UTC),
            begruendung="Begründung",
            status="offen",
            mode="simuliert",
        )
    )
    session.commit()
    return session


def test_bestaetigen_setzt_status_und_entschieden_am():
    """@trace frontend-cockpit#AC30 — `offen` → `bestaetigt`,
    `entschieden_am` wird gesetzt."""
    session = _session_mit_offenem_entscheid()

    zeile = entscheide(session, _ENTSCHEID_ID_STR, neuer_status="bestaetigt")

    assert zeile is not None
    assert zeile.status == "bestaetigt"
    assert zeile.entschieden_am is not None
    assert zeile.mode == "simuliert"


def test_ablehnen_setzt_status_abgelehnt():
    """@trace frontend-cockpit#AC30 — `offen` → `abgelehnt`."""
    session = _session_mit_offenem_entscheid()

    zeile = entscheide(session, _ENTSCHEID_ID_STR, neuer_status="abgelehnt")

    assert zeile is not None
    assert zeile.status == "abgelehnt"


def test_unbekannte_entscheid_id_liefert_none():
    """@trace frontend-cockpit#AC30 — eine nicht existierende, aber
    gültige UUID liefert `None` (Router meldet 404)."""
    session = _session_mit_offenem_entscheid()

    zeile = entscheide(session, "99999999-9999-9999-9999-999999999999", neuer_status="bestaetigt")

    assert zeile is None


def test_ungueltige_uuid_liefert_none():
    """@trace frontend-cockpit#AC30 — eine syntaktisch ungültige
    `entscheid_id` liefert `None` (Router meldet 404), keinen Crash."""
    session = _session_mit_offenem_entscheid()

    zeile = entscheide(session, "nicht-eine-uuid", neuer_status="bestaetigt")

    assert zeile is None


def test_bereits_entschieden_wirft_fehler():
    """@trace frontend-cockpit#AC30 — ein zweiter Übergang auf einer
    bereits entschiedenen Zeile wirft `EntscheidBereitsEntschiedenError`
    (Router meldet 409), OHNE den Zustand zu verändern."""
    session = _session_mit_offenem_entscheid()
    entscheide(session, _ENTSCHEID_ID_STR, neuer_status="bestaetigt")

    with pytest.raises(EntscheidBereitsEntschiedenError):
        entscheide(session, _ENTSCHEID_ID_STR, neuer_status="abgelehnt")

    zeile = session.get(HybridEntscheid, _ENTSCHEID_ID)
    assert zeile.status == "bestaetigt"


def test_liest_gesperrt_gegen_lost_update():
    """@trace frontend-cockpit#AC30 — DBA-Review Iteration 2 (Important):
    `entscheide()` MUSS die Zeile mit `with_for_update=True` lesen (analog
    `PositionRepository.offene_positionen`), damit zwei parallele
    Bestätigen-/Ablehnen-Requests unter Postgres auf Row-Lock-Ebene
    serialisiert werden statt sich per Lost Update gegenseitig zu
    überschreiben. Belegt den bedingten Pfad direkt am Aufruf-Parameter,
    da SQLite (Testumgebung) kein echtes Zeilensperren unterstützt und im
    Projekt keine Postgres-Testinfra existiert (siehe Moduldocstring)."""
    session = _session_mit_offenem_entscheid()

    with patch.object(Session, "get", wraps=session.get) as spion:
        entscheide(session, _ENTSCHEID_ID_STR, neuer_status="bestaetigt")

    spion.assert_called_once_with(
        HybridEntscheid, uuid.UUID(_ENTSCHEID_ID_STR), with_for_update=True
    )
