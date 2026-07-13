"""Tests für die Positions-Grundgerüst-Migration (Story S-015 + S-053).

Covers (depot): AC1, AC10, AC6

S-053 (AC6, FX-Attribution) ergänzt Tests für die drei neuen, nullable
Spalten `einstand_fx_rate`/`fx_kapital_gv`/`fx_waehrungs_gv` (Migration
`f065be116c72`) — analog zur bestehenden Konvention werden nur die
strukturellen Constraints (hier: NULLable, kein CHECK) gegen SQLite
geprüft.

`instrument`/`strategy`/`time_horizon` sind leere FK-Voraussetzungen (kein
Seed — siehe Docstring von `app/db/migrations/versions/
36e7c473f4aa_create_position_grundgeruest.py` und `app.db.models.Instrument`
/`Strategy`/`TimeHorizon`), `position`/`exit_rule` sind das eigentliche
Positions-Grundgerüst (AC1: mindestens Titel-Identität, Menge,
Einstandspreis, Anlageklasse, GICS-Branche (`Instrument.gics_sector`),
Strategie, Zeithorizont, Exit-Regeln, These je Position).

Der reale `alembic upgrade head`-Lauf gegen eine lokale Compose-Postgres-
Instanz (inkl. `alembic check` ohne Model-Drift) wurde manuell verifiziert
(Coder-Self-Test, siehe Handoff) — die CHECK-Constraints/FKs werden hier
strukturell gegen eine SQLite-In-Memory-DB geprüft (Konvention aus
`test_asset_class_migration.py`).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, ExitRule, Instrument, Position, Strategy, TimeHorizon

# `id`-Spalten (UUID) tragen `server_default=gen_random_uuid()` (nur unter
# Postgres verfügbar) — unter SQLite (In-Memory-Strukturtests, Konvention
# aus `test_data_source_migration.py`) wird `id` daher immer explizit
# gesetzt, statt sich auf den Server-Default zu verlassen.


def _engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed_stammdaten(session: Session):
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    session.add(
        TimeHorizon(
            id=8,
            name="Buy-and-Hold",
            transaktionskosten_relevanz="MINIMAL",
            break_even_anforderung="Jahresrendite nach Kosten",
        )
    )
    strategy = Strategy(id=uuid.uuid4(), name="Index", cluster="passiv_regelbasiert", stufe="MVP")
    session.add(strategy)
    instrument = Instrument(
        id=uuid.uuid4(),
        symbol="ACME",
        name="Acme Corp",
        asset_class_id=1,
        gics_sector="Technology",
        currency="CHF",
    )
    session.add(instrument)
    session.commit()
    return instrument, strategy


def _valid_position(instrument, strategy, **overrides) -> Position:
    kwargs = {
        "id": uuid.uuid4(),
        "instrument_id": instrument.id,
        "asset_class_id": 1,
        "strategy_id": strategy.id,
        "time_horizon_id": 8,
        "these": "Langfristiger Index-Halter.",
        "menge": Decimal("10"),
        "einstand_preis": Decimal("100.50"),
        "mode": "simuliert",
        "status": "offen",
    }
    kwargs.update(overrides)
    return Position(**kwargs)


def test_position_traegt_alle_ac1_attribute() -> None:
    """@trace depot#AC1 — eine Position führt mindestens Titel-Identität,
    Menge, Einstandspreis, Anlageklasse, GICS-Branche (über `Instrument`),
    Strategie, Zeithorizont, Exit-Regeln und die These."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        position = _valid_position(instrument, strategy)
        session.add(position)
        session.commit()

        gespeicherte_position = session.get(Position, position.id)
        assert gespeicherte_position is not None
        assert gespeicherte_position.instrument_id == instrument.id
        assert gespeicherte_position.menge == Decimal("10")
        assert gespeicherte_position.einstand_preis == Decimal("100.50")
        assert gespeicherte_position.asset_class_id == 1
        assert gespeicherte_position.strategy_id == strategy.id
        assert gespeicherte_position.time_horizon_id == 8
        assert gespeicherte_position.these == "Langfristiger Index-Halter."

        gics_branche = session.get(Instrument, instrument.id).gics_sector
        assert gics_branche == "Technology"


def test_exit_rule_ist_1_zu_1_an_position_gebunden() -> None:
    """@trace depot#AC1 — Exit-Regeln sind über `ExitRule.position_id`
    (PK, FK → position.id) 1:1 an die Position gebunden."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        position = _valid_position(instrument, strategy)
        session.add(position)
        session.commit()

        session.add(
            ExitRule(
                position_id=position.id,
                stop_typ="atr_trailing",
                atr_multiplikator=Decimal("2.5"),
                thesis_invalidation="These gebrochen, wenn Wachstum < 5%.",
            )
        )
        session.commit()

        exit_rule = session.get(ExitRule, position.id)
        assert exit_rule is not None
        assert exit_rule.stop_typ == "atr_trailing"


def test_position_default_einstand_methode_ist_gleitender_durchschnitt() -> None:
    """@trace depot#AC1 — `einstand_methode` (CH-Default, BR-112) wird bei
    Nicht-Angabe auf `gleitender_durchschnitt` gesetzt (Grundgerüst für
    S-016)."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        position = _valid_position(instrument, strategy)
        session.add(position)
        session.commit()
        session.refresh(position)
        assert position.einstand_methode == "gleitender_durchschnitt"


def test_position_rejects_negative_menge() -> None:
    """@trace depot#AC10 — `menge < 0` wird per CHECK-Constraint auf
    DB-Ebene zurückgewiesen (strukturelle Absicherung des AC10-Gates)."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        session.add(_valid_position(instrument, strategy, menge=Decimal("-1")))
        with pytest.raises(IntegrityError):
            session.commit()


def test_position_rejects_invalid_status() -> None:
    """@trace depot#AC1 — nur `offen`/`geschlossen` sind gültige
    Positions-Status."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        session.add(_valid_position(instrument, strategy, status="ungueltig"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_position_rejects_invalid_mode() -> None:
    """@trace depot#AC1 — `mode` nur `echt`/`simuliert` (→ BR-130)."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        session.add(_valid_position(instrument, strategy, mode="ungueltig"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_instrument_rejects_currency_not_3_chars() -> None:
    """@trace depot#AC1 — `currency` muss ein 3-stelliger ISO-Code sein
    (FX-Attribution-Voraussetzung, → BR-129)."""
    engine = _engine()
    with Session(engine) as session:
        session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True))
        session.commit()
        session.add(
            Instrument(
                id=uuid.uuid4(), symbol="ACME", name="Acme Corp", asset_class_id=1, currency="CH"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_time_horizon_rejects_id_outside_1_9() -> None:
    """@trace depot#AC1 — Zeithorizont-Stufen sind 1-9 (Voraussetzung für
    `position.time_horizon_id`; Katalog-Inhalt selbst ist S-037)."""
    engine = _engine()
    with Session(engine) as session:
        session.add(
            TimeHorizon(
                id=10,
                name="Ungültig",
                transaktionskosten_relevanz="MINIMAL",
                break_even_anforderung="n/a",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


# Kein `test_strategy_rejects_invalid_cluster` mehr hier: seit dem Merge von
# S-037 (Migration `ddaf9dcc6216`) ist `strategy.cluster` ein FK auf
# `strategy_cluster.code` (kein eigenständiges CHECK auf `strategy` mehr) —
# unter SQLite ohne aktiviertes `PRAGMA foreign_keys=ON` greift diese
# Ablehnung hier nicht. Die äquivalente, korrekt mit FK-Pragma aufgesetzte
# Prüfung lebt bereits in `tests/db/test_strategie_katalog_migration.py`
# (`test_model_rejects_strategy_with_unknown_cluster_fk`).


def test_position_fx_attribution_spalten_sind_nullable_und_default_none() -> None:
    """@trace depot#AC6 — `einstand_fx_rate`/`fx_kapital_gv`/
    `fx_waehrungs_gv` sind ohne Angabe `None` (CHF-Position, keine
    Attribution nötig, → BR-129) — kein NOT-NULL-Constraint."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        position = _valid_position(instrument, strategy)
        session.add(position)
        session.commit()
        session.refresh(position)

        assert position.einstand_fx_rate is None
        assert position.fx_kapital_gv is None
        assert position.fx_waehrungs_gv is None


def test_position_fx_attribution_spalten_persistieren_werte() -> None:
    """@trace depot#AC6 — die drei FX-Attribution-Spalten persistieren
    gesetzte Werte (Fremdwährungsposition)."""
    engine = _engine()
    with Session(engine) as session:
        instrument, strategy = _seed_stammdaten(session)
        position = _valid_position(
            instrument,
            strategy,
            einstand_fx_rate=Decimal("0.90"),
            fx_kapital_gv=Decimal("270"),
            fx_waehrungs_gv=Decimal("26"),
        )
        session.add(position)
        session.commit()
        session.refresh(position)

        assert position.einstand_fx_rate == Decimal("0.90")
        assert position.fx_kapital_gv == Decimal("270")
        assert position.fx_waehrungs_gv == Decimal("26")
