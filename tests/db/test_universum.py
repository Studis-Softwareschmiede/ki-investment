"""Tests fuer das survivorship-bias-freie historische Titel-Universum
`app.db.universum` (Story S-051).

Covers (datenqualitaet): AC5

- AC5 (Survivorship-Bias-Vermeidung):
  `test_historisches_universum_includes_symbol_observed_before_stand_zeitpunkt`
  belegt den Basisfall: ein Symbol mit einer Beobachtung bis zum
  `stand_zeitpunkt` ist Teil des Universums.
  `test_historisches_universum_excludes_symbol_first_observed_after_stand_zeitpunkt`
  belegt die zeitliche Abgrenzung: ein Symbol, das ERST nach dem
  `stand_zeitpunkt` erstmals beobachtet wurde, ist (noch) nicht Teil des zu
  X gueltigen Universums.
  `test_historisches_universum_keeps_delisted_symbol_for_query_after_its_last_observation`
  belegt den Kern der AC5 + den Edge-Case "Delisting eines gehaltenen
  Titels": ein Symbol, das NACH seiner letzten Beobachtung keine weiteren
  Daten mehr erhaelt (delisted), bleibt in einer Universums-Abfrage mit
  einem `stand_zeitpunkt` NACH dem Delisting weiterhin enthalten — es gibt
  keinen "aktuell aktiv"-Filter, der es stillschweigend ausschliessen
  wuerde (der klassische Survivorship-Bias-Fehler).
  `test_historisches_universum_scopes_by_data_source_id` belegt die
  optionale Quellen-Einschraenkung.
  `test_historisches_universum_excludes_rows_without_symbol` belegt, dass
  Zeilen ohne Symbol (kein Titel-Bezug) nicht ins Universum aufgenommen
  werden.

SQLite (in-memory) reicht aus (reine SELECT-DISTINCT-Abfrage, kein
Postgres-spezifisches Konstrukt involviert), analog `tests/db/test_silver.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AssetClass, DataSource, MarketDataBronze
from app.db.silver import record_silver_observation
from app.db.universum import historisches_universum


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add(
            AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True)
        )
        db_session.add(
            DataSource(
                id=uuid.uuid4(),
                name="IBKR - Kursdaten",
                kategorie="equity_fundamentals",
                qualitaet="hoch",
                frequenz_sekunden=60,
                aktiv=True,
            )
        )
        db_session.commit()
        yield db_session


def _source_id(session: Session) -> uuid.UUID:
    return session.query(DataSource).one().id


def _lege_silber_zeile_an(
    session: Session,
    *,
    symbol: str,
    source_event_id: str,
    observed_at: datetime,
    data_source_id: uuid.UUID | None = None,
) -> None:
    quelle = data_source_id if data_source_id is not None else _source_id(session)
    bronze_zeile = MarketDataBronze(
        data_source_id=quelle,
        source_event_id=source_event_id,
        symbol=symbol,
        payload={"preis": "100"},
        observed_at=observed_at,
        asset_class_tag=1,
    )
    session.add(bronze_zeile)
    session.commit()
    record_silver_observation(
        session, bronze_zeile=bronze_zeile, normalisierter_wert=Decimal("100"), einheit="CHF"
    )


def test_historisches_universum_includes_symbol_observed_before_stand_zeitpunkt(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC5 — ein Symbol mit einer Beobachtung bis zum
    stand_zeitpunkt ist Teil des Universums."""
    _lege_silber_zeile_an(
        session,
        symbol="AAPL",
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    universum = historisches_universum(session, stand_zeitpunkt=datetime(2026, 6, 1, tzinfo=UTC))

    assert universum == ["AAPL"]


def test_historisches_universum_excludes_symbol_first_observed_after_stand_zeitpunkt(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC5 — ein Symbol, das ERST nach dem
    stand_zeitpunkt erstmals beobachtet wurde, ist (noch) nicht Teil des zu
    X gueltigen Universums."""
    _lege_silber_zeile_an(
        session,
        symbol="NEWCO",
        source_event_id="ibkr:NEWCO:2026-12-01",
        observed_at=datetime(2026, 12, 1, tzinfo=UTC),
    )

    universum = historisches_universum(session, stand_zeitpunkt=datetime(2026, 6, 1, tzinfo=UTC))

    assert universum == []


def test_historisches_universum_keeps_delisted_symbol_for_query_after_its_last_observation(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC5 — Kern-Invariante + Edge-Case "Delisting
    eines gehaltenen Titels": ein Symbol, das nach seiner letzten
    Beobachtung delisted wird (keine weiteren Daten mehr erhaelt), bleibt in
    einer Universums-Abfrage mit einem stand_zeitpunkt NACH dem Delisting
    weiterhin enthalten (kein "aktuell aktiv"-Filter, kein
    Survivorship-Bias)."""
    _lege_silber_zeile_an(
        session,
        symbol="DELISTED",
        source_event_id="ibkr:DELISTED:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    # DELISTED erhaelt danach keine weiteren Beobachtungen mehr (Delisting) --
    # ein zweites, weiterhin aktives Symbol dient als Kontrast.
    _lege_silber_zeile_an(
        session,
        symbol="ACTIVE",
        source_event_id="ibkr:ACTIVE:2026-06-01",
        observed_at=datetime(2026, 6, 1, tzinfo=UTC),
    )

    universum_nach_delisting = historisches_universum(
        session, stand_zeitpunkt=datetime(2026, 12, 1, tzinfo=UTC)
    )

    assert universum_nach_delisting == ["ACTIVE", "DELISTED"]


def test_historisches_universum_scopes_by_data_source_id(session: Session) -> None:
    """@trace datenqualitaet#AC5 — optionale Einschraenkung auf eine
    einzelne Quelle."""
    quelle_a = _source_id(session)
    quelle_b = uuid.uuid4()
    session.add(
        DataSource(
            id=quelle_b,
            name="Yahoo Finance - Kursdaten",
            kategorie="equity_fundamentals",
            qualitaet="mittel_hoch",
            frequenz_sekunden=60,
            aktiv=True,
        )
    )
    session.commit()

    _lege_silber_zeile_an(
        session,
        symbol="AAPL",
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        data_source_id=quelle_a,
    )
    _lege_silber_zeile_an(
        session,
        symbol="MSFT",
        source_event_id="yahoo:MSFT:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        data_source_id=quelle_b,
    )

    universum_nur_a = historisches_universum(
        session, stand_zeitpunkt=datetime(2026, 6, 1, tzinfo=UTC), data_source_id=quelle_a
    )

    assert universum_nur_a == ["AAPL"]


def test_historisches_universum_excludes_rows_without_symbol(session: Session) -> None:
    """@trace datenqualitaet#AC5 — Zeilen ohne Symbol (kein Titel-Bezug)
    werden nicht ins Universum aufgenommen."""
    source_id = _source_id(session)
    bronze_ohne_symbol = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="fred:CPI:2026-01-01",
        symbol=None,
        payload={"wert": "3.2"},
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        asset_class_tag=None,
    )
    session.add(bronze_ohne_symbol)
    session.commit()
    record_silver_observation(
        session,
        bronze_zeile=bronze_ohne_symbol,
        normalisierter_wert=Decimal("3.2"),
        einheit="pct",
    )

    universum = historisches_universum(session, stand_zeitpunkt=datetime(2026, 6, 1, tzinfo=UTC))

    assert universum == []
