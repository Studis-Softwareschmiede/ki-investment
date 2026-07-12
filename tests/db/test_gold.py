"""Tests fuer den Gold-Store `app.db.gold` (Story S-051).

Covers (datenqualitaet): AC4

- AC4 (Anreicherung, Konsumenten-Sicht, Bronze/Silver bleiben unangetastet):
  `test_record_gold_observation_derives_row_from_valid_silber_zeile` belegt
  die Kern-Ableitung eines Gold-Datensatzes aus einer konkreten Silver-Zeile
  (Spec-Vertrag "Gold-Datensatz": event_id, angereicherter_wert,
  qualitaetsindikator, herkunft: silver_version).
  `test_record_gold_observation_rejects_mismatched_bronze_silber_pair` belegt
  die Integritaetspruefung `SilberBronzeMismatchError`.
  `test_record_gold_observation_is_idempotent_for_same_silver_version` belegt
  Reproduzierbarkeit: derselbe Silber-Zeile-Aufruf dupliziert keinen
  Gold-Datensatz.
  `test_record_gold_observation_does_not_modify_bronze_or_silver` belegt die
  Kern-Invariante "keine Anreicherung veraendert/ersetzt Bronze-Rohdaten"
  (und Silver bleibt ebenfalls unveraendert).
  `test_gold_excludes_data_with_no_corresponding_silver_row` belegt den
  AC8-Anschluss: ein ungueltiger Bronze-Kandidat, der nie eine Silver-Zeile
  erreicht (AC7/AC8-Gate), erscheint strukturell auch nie in einem
  Gold-Rebuild.
  `test_rebuild_gold_series_for_symbol_rebuilds_from_current_silver` belegt
  die AC4-NFR-Reproduzierbarkeit (Gold jederzeit aus Silver/Bronze
  ableitbar).
  `test_rebuild_gold_series_for_symbol_does_not_delete_other_data_source_rows`
  belegt die Cross-Data-Source-Sicherheit (vorab angewandte Iteration-2-Lehre
  aus S-024): ein Rebuild fuer Quelle A loescht keine Gold-Zeile einer
  anderen Quelle B.
  `test_gold_dedupe_lock_is_noop_under_sqlite` belegt, dass
  `_erwirke_gold_dedupe_lock()` unter SQLite (kein `pg_advisory_xact_lock`)
  folgenlos bleibt.
  `test_record_gold_observation_flush_conflict_reloads_authoritative_row_not_crash`
  belegt die Nebenlaeufigkeits-Haertung: ein von der DB-seitigen zweiten
  Sicherung (`uq_market_data_gold_silver_version`) abgelehnter Insert wird
  als `IntegrityError` abgefangen und die tatsaechlich massgebliche Zeile
  zurueckgegeben, statt eines Duplikats oder Crashs.
  Iteration-2-Regressionsschutz (Critical, DBA-Befund):
  `test_rebuild_silver_series_for_symbol_cascades_delete_of_dependent_gold_rows`
  belegt den `ON DELETE CASCADE`-Fix: `app.db.silver.
  rebuild_silver_series_for_symbol()` loescht bei einer Corporate-Actions-
  Neuableitung Silver-Zeilen, zu denen bereits eine Gold-Zeile existiert,
  OHNE Fremdschluesselverletzung — die abhaengige Gold-Zeile wird
  automatisch mitgeloescht (kaskadiert), statt das `DELETE` zu blockieren.
  Nutzt eine dedizierte SQLite-Fixture mit `PRAGMA foreign_keys=ON`
  (Standard-Fixture dieser Datei hat FK-Erzwingung bewusst NICHT aktiv, um
  bestehende Tests nicht zu beeinflussen), gegen echtes Postgres 17
  zusaetzlich manuell verifiziert (Coder-Self-Test, siehe Handoff).

SQLite (in-memory) reicht aus (reiner SQLAlchemy-/Python-Code, kein
Postgres-spezifisches Konstrukt wie Partitionierung involviert), analog
`tests/db/test_silver.py`. Die reale Nebenlaeufigkeit ist nur unter Postgres
real pruefbar — der DB-seitige Unique-Index-Reject wird hier per
SQLAlchemy-`before_flush`-Event simuliert (analog `tests/db/test_silver.py`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.gold import (
    SilberBronzeMismatchError,
    _erwirke_gold_dedupe_lock,
    rebuild_gold_series_for_symbol,
    record_gold_observation,
)
from app.db.models import AssetClass, DataSource, MarketDataBronze, MarketDataGold
from app.db.silver import (
    UngueltigerBronzeKandidatError,
    rebuild_silver_series_for_symbol,
    record_silver_observation,
)


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


def _bronze_zeile(
    session: Session,
    *,
    source_event_id: str,
    symbol: str = "AAPL",
    preis: str = "400.00000000",
    observed_at: datetime,
    asset_class_tag: int | None = 1,
    quality_indicator: str | None = "hoch",
    data_source_id: uuid.UUID | None = None,
) -> MarketDataBronze:
    zeile = MarketDataBronze(
        data_source_id=data_source_id if data_source_id is not None else _source_id(session),
        source_event_id=source_event_id,
        symbol=symbol,
        payload={"preis": preis},
        observed_at=observed_at,
        asset_class_tag=asset_class_tag,
        quality_indicator=quality_indicator,
    )
    session.add(zeile)
    session.commit()
    return zeile


def test_record_gold_observation_derives_row_from_valid_silber_zeile(session: Session) -> None:
    """@trace datenqualitaet#AC4 — aus einer validen Silver-Zeile (+ ihrer
    Bronze-Zeile) wird ein Gold-Datensatz gemaess Spec-Vertrag abgeleitet
    (event_id, angereicherter_wert, qualitaetsindikator,
    herkunft: silver_version)."""
    bronze_zeile = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        quality_indicator="hoch",
    )
    silber_zeile = record_silver_observation(
        session,
        bronze_zeile=bronze_zeile,
        normalisierter_wert=Decimal("400.00000000"),
        einheit="CHF",
    )

    gold_zeile = record_gold_observation(
        session, bronze_zeile=bronze_zeile, silber_zeile=silber_zeile
    )

    assert gold_zeile.source_event_id == "ibkr:AAPL:2026-01-01"
    assert gold_zeile.angereicherter_wert == Decimal("400.00000000")
    assert gold_zeile.qualitaetsindikator == "hoch"
    assert gold_zeile.silver_id == silber_zeile.id
    assert gold_zeile.silver_observed_at == silber_zeile.observed_at
    assert session.query(MarketDataGold).count() == 1


def test_record_gold_observation_rejects_mismatched_bronze_silber_pair(session: Session) -> None:
    """@trace datenqualitaet#AC4 — eine Silver-Zeile, die NICHT aus der
    uebergebenen Bronze-Zeile abgeleitet wurde, wird zurueckgewiesen
    (verhindert falsche herkunft/qualitaetsindikator)."""
    bronze_a = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    bronze_b = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-02",
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    silber_von_a = record_silver_observation(
        session, bronze_zeile=bronze_a, normalisierter_wert=Decimal("400"), einheit="CHF"
    )

    with pytest.raises(SilberBronzeMismatchError):
        record_gold_observation(session, bronze_zeile=bronze_b, silber_zeile=silber_von_a)

    assert session.query(MarketDataGold).count() == 0


def test_record_gold_observation_is_idempotent_for_same_silver_version(session: Session) -> None:
    """@trace datenqualitaet#AC4 — Reproduzierbarkeit: ein zweiter Aufruf
    fuer dieselbe Silver-Version legt keinen weiteren Gold-Datensatz an,
    sondern liefert den bestehenden zurueck."""
    bronze_zeile = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    silber_zeile = record_silver_observation(
        session, bronze_zeile=bronze_zeile, normalisierter_wert=Decimal("400"), einheit="CHF"
    )

    erste = record_gold_observation(session, bronze_zeile=bronze_zeile, silber_zeile=silber_zeile)
    zweite = record_gold_observation(session, bronze_zeile=bronze_zeile, silber_zeile=silber_zeile)

    assert zweite.id == erste.id
    assert session.query(MarketDataGold).count() == 1


def test_record_gold_observation_does_not_modify_bronze_or_silver(session: Session) -> None:
    """@trace datenqualitaet#AC4 — Kern-Invariante: keine Anreicherung
    veraendert/ersetzt die zugrunde liegenden Bronze-Rohdaten (Silver bleibt
    ebenfalls unveraendert)."""
    bronze_zeile = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    silber_zeile = record_silver_observation(
        session, bronze_zeile=bronze_zeile, normalisierter_wert=Decimal("400"), einheit="CHF"
    )
    urspruenglicher_payload = dict(bronze_zeile.payload)
    urspruenglicher_normalisierter_wert = silber_zeile.normalisierter_wert

    record_gold_observation(session, bronze_zeile=bronze_zeile, silber_zeile=silber_zeile)

    unveraenderte_bronze = session.execute(
        select(MarketDataBronze).where(MarketDataBronze.id == bronze_zeile.id)
    ).scalar_one()
    assert unveraenderte_bronze.payload == urspruenglicher_payload
    assert silber_zeile.normalisierter_wert == urspruenglicher_normalisierter_wert


def test_gold_excludes_data_with_no_corresponding_silver_row(session: Session) -> None:
    """@trace datenqualitaet#AC4 — AC8-Anschluss: ein ungueltiger
    Bronze-Kandidat erreicht nie eine Silver-Zeile (AC7/AC8-Gate) und
    erscheint deshalb strukturell nie in einem Gold-Rebuild."""
    source_id = _source_id(session)
    gueltig = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    record_silver_observation(
        session, bronze_zeile=gueltig, normalisierter_wert=Decimal("400"), einheit="CHF"
    )

    ungueltig = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="ibkr:AAPL:2026-01-02",
        symbol="AAPL",
        payload={"preis": "410"},
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
        asset_class_tag=99,  # ausserhalb 1..11 -> ungueltig (AC7)
    )
    session.add(ungueltig)
    session.commit()
    with pytest.raises(UngueltigerBronzeKandidatError):
        record_silver_observation(
            session, bronze_zeile=ungueltig, normalisierter_wert=Decimal("410"), einheit="CHF"
        )

    ergebnisse = rebuild_gold_series_for_symbol(session, data_source_id=source_id, symbol="AAPL")

    assert len(ergebnisse) == 1
    assert ergebnisse[0].source_event_id == "ibkr:AAPL:2026-01-01"


def test_rebuild_gold_series_for_symbol_rebuilds_from_current_silver(session: Session) -> None:
    """@trace datenqualitaet#AC4 — NFR "Gold jederzeit aus Bronze/Silver
    rekonstruierbar": ein Rebuild leitet die vollstaendige Gold-Reihe neu
    aus der aktuellen Silver-Historie ab."""
    source_id = _source_id(session)
    bronze_1 = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        preis="400",
        quality_indicator="hoch",
    )
    bronze_2 = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-02",
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
        preis="410",
        quality_indicator="mittel",
    )
    record_silver_observation(
        session, bronze_zeile=bronze_1, normalisierter_wert=Decimal("400"), einheit="CHF"
    )
    record_silver_observation(
        session, bronze_zeile=bronze_2, normalisierter_wert=Decimal("410"), einheit="CHF"
    )

    ergebnisse = rebuild_gold_series_for_symbol(session, data_source_id=source_id, symbol="AAPL")

    assert len(ergebnisse) == 2
    werte_je_qualitaet = {z.qualitaetsindikator: z.angereicherter_wert for z in ergebnisse}
    assert werte_je_qualitaet["hoch"] == Decimal("400")
    assert werte_je_qualitaet["mittel"] == Decimal("410")
    assert session.query(MarketDataGold).count() == 2

    # zweiter Rebuild ist idempotent (keine Duplikate).
    rebuild_gold_series_for_symbol(session, data_source_id=source_id, symbol="AAPL")
    assert session.query(MarketDataGold).count() == 2


def test_rebuild_gold_series_for_symbol_does_not_delete_other_data_source_rows(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC4 — Cross-Data-Source-Sicherheit (Iteration-
    2-Lehre aus S-024 vorab angewandt): ein Rebuild fuer Quelle A loescht
    keine Gold-Zeile einer anderen Quelle B, selbst wenn beide zufaellig
    dieselbe `source_event_id`-Zeichenkette fuer dasselbe Symbol
    verwenden."""
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

    bronze_a = _bronze_zeile(
        session,
        source_event_id="AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        preis="400",
        data_source_id=quelle_a,
    )
    bronze_b = _bronze_zeile(
        session,
        source_event_id="AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        preis="999",
        data_source_id=quelle_b,
    )
    silber_a = record_silver_observation(
        session, bronze_zeile=bronze_a, normalisierter_wert=Decimal("400"), einheit="CHF"
    )
    silber_b = record_silver_observation(
        session, bronze_zeile=bronze_b, normalisierter_wert=Decimal("999"), einheit="CHF"
    )
    gold_b_vorher = record_gold_observation(session, bronze_zeile=bronze_b, silber_zeile=silber_b)

    rebuild_gold_series_for_symbol(session, data_source_id=quelle_a, symbol="AAPL")
    # zweiter Rebuild NUR fuer Quelle A.
    rebuild_gold_series_for_symbol(session, data_source_id=quelle_a, symbol="AAPL")

    gold_b_nachher = session.execute(
        select(MarketDataGold).where(MarketDataGold.data_source_id == quelle_b)
    ).scalar_one()
    assert gold_b_nachher.id == gold_b_vorher.id
    assert gold_b_nachher.angereicherter_wert == Decimal("999")

    gold_a = session.execute(
        select(MarketDataGold).where(MarketDataGold.data_source_id == quelle_a)
    ).scalar_one()
    assert gold_a.angereicherter_wert == Decimal("400")
    assert silber_a.id != silber_b.id
    assert session.query(MarketDataGold).count() == 2


def test_gold_dedupe_lock_is_noop_under_sqlite(session: Session) -> None:
    """@trace datenqualitaet#AC4 — `_erwirke_gold_dedupe_lock()` darf unter
    SQLite (kein `pg_advisory_xact_lock`) keine Ausnahme werfen und keine
    SQL-Anweisung ausfuehren — reiner No-Op."""
    _erwirke_gold_dedupe_lock(
        session, silver_id=uuid.uuid4(), silver_observed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert session.query(MarketDataGold).count() == 0


def test_record_gold_observation_flush_conflict_reloads_authoritative_row_not_crash(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC4 — lehnt die DB-seitige zweite Sicherung
    (`uq_market_data_gold_silver_version`) einen Insert als Duplikat ab, MUSS
    `record_gold_observation()` dies als `IntegrityError` abfangen und die
    tatsaechlich massgebliche (bereits vorhandene) Zeile zurueckgeben — nie
    das eigene, nicht persistierte ORM-Objekt und nie mit unbehandelter
    Exception crashen. Hier per `before_flush`-Event simuliert (analog
    `tests/db/test_silver.py`), da SQLite keinen echten
    Postgres-Unique-Index-Reject unter Nebenlaeufigkeit ausfuehren kann."""
    bronze_zeile = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:race",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    silber_zeile = record_silver_observation(
        session, bronze_zeile=bronze_zeile, normalisierter_wert=Decimal("400"), einheit="CHF"
    )

    massgebliche_zeile = MarketDataGold(
        silver_id=silber_zeile.id,
        silver_observed_at=silber_zeile.observed_at,
        data_source_id=silber_zeile.data_source_id,
        source_event_id=silber_zeile.source_event_id,
        symbol=silber_zeile.symbol,
        angereicherter_wert=Decimal("400"),
        qualitaetsindikator="hoch",
        observed_at=silber_zeile.observed_at,
    )
    session.add(massgebliche_zeile)
    session.commit()

    def _simuliere_unique_index_reject(sess, _flush_context, _instances) -> None:
        for objekt in sess.new:
            if (
                isinstance(objekt, MarketDataGold)
                and objekt.silver_id == silber_zeile.id
                and objekt.silver_observed_at == silber_zeile.observed_at
            ):
                raise IntegrityError(
                    "INSERT INTO market_data_gold ...",
                    {},
                    Exception("simulierter Unique-Index-Reject (unique_violation)"),
                )

    event.listen(session, "before_flush", _simuliere_unique_index_reject)
    try:
        ergebnis = record_gold_observation(
            session, bronze_zeile=bronze_zeile, silber_zeile=silber_zeile
        )
    finally:
        event.remove(session, "before_flush", _simuliere_unique_index_reject)

    assert ergebnis.id == massgebliche_zeile.id
    assert ergebnis.angereicherter_wert == Decimal("400")
    assert session.query(MarketDataGold).count() == 1


@pytest.fixture()
def session_mit_fk_erzwingung():
    """Dedizierte Fixture mit `PRAGMA foreign_keys=ON` (SQLite erzwingt FK-
    Constraints sonst nicht) — nur für den Cascade-Regressionstest, damit
    die uebrigen Tests dieser Datei unveraendert ohne FK-Erzwingung laufen
    (Iteration-2-DBA-Befund: die fehlende Erzwingung war der Grund, warum
    das urspruengliche FK-Problem in den bisherigen Tests unbemerkt blieb)."""
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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


def test_rebuild_silver_series_for_symbol_cascades_delete_of_dependent_gold_rows(
    session_mit_fk_erzwingung: Session,
) -> None:
    """@trace datenqualitaet#AC4 — Iteration-2-Regressionsschutz (Critical,
    DBA-Befund): `app.db.silver.rebuild_silver_series_for_symbol()` loescht
    bei einer Corporate-Actions-Neuableitung ALLE bestehenden Silver-Zeilen
    fuer (data_source_id, symbol) — auch wenn zu einer davon bereits eine
    Gold-Zeile existiert. MIT `ON DELETE CASCADE` auf der Gold->Silver-FK
    darf dieses DELETE NICHT an einer Fremdschluesselverletzung scheitern;
    die abhaengige Gold-Zeile wird stattdessen automatisch mitgeloescht."""
    session = session_mit_fk_erzwingung
    source_id = session.query(DataSource).one().id
    bronze_zeile = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="ibkr:AAPL:2026-01-01",
        symbol="AAPL",
        payload={"preis": "400"},
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        asset_class_tag=1,
    )
    session.add(bronze_zeile)
    session.commit()
    silber_zeile = record_silver_observation(
        session, bronze_zeile=bronze_zeile, normalisierter_wert=Decimal("400"), einheit="CHF"
    )
    gold_zeile = record_gold_observation(
        session, bronze_zeile=bronze_zeile, silber_zeile=silber_zeile
    )
    assert session.query(MarketDataGold).count() == 1

    # Rueckwirkend gemeldeter Split -- loest eine vollstaendige
    # Silver-Neuableitung aus, die intern die alte Silver-Zeile (zu der die
    # Gold-Zeile oben zeigt) loescht und ersetzt.
    neue_silber_reihe = rebuild_silver_series_for_symbol(
        session,
        data_source_id=source_id,
        symbol="AAPL",
        wert_extraktor=lambda zeile: Decimal(zeile.payload["preis"]),
        einheit="CHF",
    )

    # Kein Crash/keine IntegrityError -- die alte Silver-Zeile (und damit die
    # abhaengige Gold-Zeile) wurde kaskadiert geloescht; eine neue
    # Silver-Zeile wurde angelegt (neue Identitaet), fuer die noch KEINE
    # Gold-Zeile existiert (Anschluss-Pflicht der Orchestrierungsschicht).
    assert len(neue_silber_reihe) == 1
    assert neue_silber_reihe[0].id != silber_zeile.id
    # `session.query(...).count()` erzwingt eine echte SQL-Abfrage gegen die
    # DB (im Unterschied zu `Session.get()`, das zuerst die lokale
    # Identity-Map prueft -- die den kaskadierten DB-seitigen Loesch-Effekt
    # NICHT sieht, weil `rebuild_silver_series_for_symbol()` per Core-`delete()`
    # arbeitet und SQLAlchemy von der DB-seitigen ON-DELETE-CASCADE-Wirkung
    # auf `gold_zeile` nichts weiss).
    assert session.query(MarketDataGold).count() == 0
    verwaiste_gold_zeile = session.get(
        MarketDataGold, (gold_zeile.id, gold_zeile.observed_at), populate_existing=True
    )
    assert verwaiste_gold_zeile is None
