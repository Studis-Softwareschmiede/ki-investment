"""Tests fuer den Bronze-Store `app.db.bronze` (Story S-022).

Covers (datenqualitaet): AC1, AC2, AC9, AC10

- AC1 (immutabel/append-only): `record_observation()`/`replay()` sind die
  einzigen Zugriffsfunktionen des Moduls — keine Update-/Delete-Funktion
  existiert; jeder Test, der eine Revision auslöst, prüft zusätzlich, dass
  die urspruengliche Zeile unveraendert in der DB verbleibt (kein Update).
  Die DB-seitige zweite Sicherung (BEFORE-UPDATE/DELETE-Trigger, BR-121) ist
  nur unter Postgres ausfuehrbar und wurde manuell gegen die lokale
  Compose-Postgres-Instanz verifiziert (Coder-Self-Test, siehe Handoff) —
  hier strukturell durch die App-Layer-Enthaltsamkeit (keine Update-API)
  abgedeckt.
- AC2 (Point-in-Time + Replay "Stand X"): `replay()` liefert je
  (data_source_id, source_event_id) die Version, deren `ingested_at` zu
  einem gegebenen `stand_zeitpunkt` bereits bekannt war; ein Replay auf ein
  frueheres Datum bleibt nach einer spaeteren Revision stabil.
- AC9 (Idempotenz, deckt E2): identischer Inhalt (gleicher `payload` +
  gleicher `beobachtungs_zeitpunkt`) zur selben Event-ID -> kein Duplikat.
  Iteration-2-Regressionsschutz (Reviewer-Befund, empirisch gegen Postgres 17
  gemessen — siehe `.claude/lessons/coder.md`):
  `test_dedupe_lock_is_noop_under_sqlite` belegt, dass
  `_erwirke_dedupe_lock()` unter SQLite (kein `pg_advisory_xact_lock`)
  folgenlos bleibt; `test_flush_conflict_from_db_layer_reloads_authoritative_row_not_crash`
  belegt, dass ein von der DB-seitigen Sicherung abgelehnter Insert
  (`IntegrityError` statt stillem `RETURN NULL`) sauber abgefangen wird und
  die tatsaechlich massgebliche Zeile zurueckgegeben wird (nie ein
  verwaistes ORM-Objekt, nie ein Crash). Die echte Nebenlaeufigkeit (zwei
  offene Postgres-Transaktionen, `pg_advisory_xact_lock` schliesst die Race-
  Luecke) ist nur unter Postgres real pruefbar — manuell gegen die lokale
  Docker-Postgres-Instanz verifiziert (Coder-Self-Test, siehe Handoff):
  ohne Lock erzeugten zwei ueberlappende, noch nicht committete
  `record_observation()`-Aufrufe fuer dieselbe Event-ID zwei Duplikat-Zeilen
  (reproduzierter Iteration-1-Befund); mit Lock genau eine Zeile, derselbe
  ID in beiden Rueckgabewerten, kein `ObjectDeletedError` nach `commit()`.
- AC10 (Revision, deckt A1): abweichender Inhalt zur selben Event-ID -> neue
  Point-in-Time-Version statt Ueberschreiben; alte Version bleibt abfragbar.

SQLite (in-memory) reicht fuer diese App-Layer-Logik vollstaendig aus — sie
ist dialektunabhaengiger reiner SQLAlchemy-/Python-Code (kein
Postgres-spezifisches Konstrukt wie Partitionierung/Trigger involviert). Der
DB-seitige Trigger-Reject (IntegrityError statt `RETURN NULL`) wird hier per
SQLAlchemy-`before_flush`-Event simuliert (kein echter Postgres-Trigger
unter SQLite verfuegbar) — die reale Trigger-/Lock-Interaktion ist zusaetzlich
manuell gegen Postgres verifiziert (siehe oben).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.bronze import _erwirke_dedupe_lock, record_observation, replay
from app.db.models import AssetClass, DataSource, MarketDataBronze


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add(
            AssetClass(
                id=3, name="Cash/Geldmarkt", prio_stufe="MVP", aktiv=True, retail_driven=False
            )
        )
        db_session.add(
            DataSource(
                id=uuid.uuid4(),
                name="FRED - Federal Reserve Economic Data",
                kategorie="makro_anleihen",
                qualitaet="sehr_hoch",
                frequenz_sekunden=86400,
                aktiv=True,
            )
        )
        db_session.commit()
        yield db_session


def _fred_source_id(session: Session) -> uuid.UUID:
    return session.query(DataSource).one().id


def test_first_observation_is_stored_as_new_row(session: Session) -> None:
    """@trace datenqualitaet#AC1 — ein bislang unbekannter Datenpunkt wird
    unveraendert als neue Bronze-Zeile abgelegt."""
    source_id = _fred_source_id(session)

    zeile = record_observation(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
        anlageklassen_tag=3,
    )

    assert session.query(MarketDataBronze).count() == 1
    assert zeile.payload == {"value": "3.1"}
    assert zeile.observed_at == datetime(2026, 1, 1, tzinfo=UTC)


def test_identical_redelivery_is_idempotent_no_duplicate(session: Session) -> None:
    """@trace datenqualitaet#AC9 — dasselbe Ereignis (gleiche Event-ID,
    identischer Inhalt) erneut eintreffend erzeugt keine zweite Zeile und
    keine doppelte Verarbeitung (deckt E2)."""
    source_id = _fred_source_id(session)
    beobachtet = datetime(2026, 1, 1, tzinfo=UTC)

    erste = record_observation(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=beobachtet,
    )
    zweite = record_observation(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=beobachtet,
    )

    assert session.query(MarketDataBronze).count() == 1
    assert zweite.id == erste.id


def test_dedupe_lock_is_noop_under_sqlite(session: Session) -> None:
    """@trace datenqualitaet#AC9 — `_erwirke_dedupe_lock()` (Iteration-2-
    Nebenlaeufigkeits-Haertung) darf unter SQLite (Test-Backend, kein
    `pg_advisory_xact_lock`) keine Ausnahme werfen und keine SQL-Anweisung
    ausfuehren — die Funktion muss dialektbedingt ein reiner No-Op sein."""
    source_id = _fred_source_id(session)

    _erwirke_dedupe_lock(session, data_source_id=source_id, source_event_id="beliebig")

    # Kein Fehler ausgeloest, Session bleibt normal nutzbar.
    assert session.query(MarketDataBronze).count() == 0


def test_flush_conflict_from_db_layer_reloads_authoritative_row_not_crash(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC9 — Iteration-2-Regressionsschutz (Reviewer-
    Befund, siehe `.claude/lessons/coder.md`): lehnt die DB-seitige zweite
    Sicherung (Trigger) einen Insert als Duplikat ab, MUSS `record_observation()`
    dies als `IntegrityError` abfangen und die tatsaechlich massgebliche
    (bereits vorhandene) Zeile zurueckgeben — NIE das eigene, nicht
    persistierte ORM-Objekt und NIE mit unbehandelter Exception crashen. Der
    echte Postgres-Trigger wirft seit Iteration 2 statt eines stillen
    `RETURN NULL` genau diese abfangbare Exception (SQLSTATE
    `unique_violation`); hier per `before_flush`-Event simuliert, da SQLite
    keinen echten Trigger ausfuehren kann."""
    source_id = _fred_source_id(session)
    beobachtet = datetime(2026, 1, 1, tzinfo=UTC)

    massgebliche_zeile = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="evt-simulierter-trigger-konflikt",
        payload={"value": "vom-trigger-als-massgeblich-erkannt"},
        observed_at=beobachtet,
    )
    session.add(massgebliche_zeile)
    session.commit()

    def _simuliere_trigger_reject(sess, _flush_context, _instances) -> None:
        for objekt in sess.new:
            if (
                isinstance(objekt, MarketDataBronze)
                and objekt.source_event_id == "evt-simulierter-trigger-konflikt"
            ):
                raise IntegrityError(
                    "INSERT INTO market_data_bronze ...",
                    {},
                    Exception("simulierter Trigger-Reject (unique_violation)"),
                )

    event.listen(session, "before_flush", _simuliere_trigger_reject)
    try:
        ergebnis = record_observation(
            session,
            data_source_id=source_id,
            source_event_id="evt-simulierter-trigger-konflikt",
            # Abweichender Inhalt ggue. massgeblicher Zeile -> App-Layer haelt
            # dies faelschlich fuer eine neue Revision und versucht den
            # Insert (simuliert: der Aufrufer sah die massgebliche Zeile
            # nicht rechtzeitig, analog zur Race-Luecke aus Iteration 1).
            payload={"value": "veraltete-sicht-des-aufrufers"},
            beobachtungs_zeitpunkt=beobachtet,
        )
    finally:
        event.remove(session, "before_flush", _simuliere_trigger_reject)

    assert ergebnis.id == massgebliche_zeile.id
    assert ergebnis.payload == {"value": "vom-trigger-als-massgeblich-erkannt"}
    # Kein Duplikat entstanden -- der abgelehnte Insert hat keine Zeile angelegt.
    assert session.query(MarketDataBronze).count() == 1


def test_revision_creates_new_pit_version_without_overwriting_old_row(session: Session) -> None:
    """@trace datenqualitaet#AC10 — eine rueckwirkende Revision (z.B. FRED)
    erzeugt eine zusaetzliche Point-in-Time-Version statt die urspruengliche
    Zeile zu ueberschreiben; die alte Version bleibt unveraendert abfragbar
    (deckt A1)."""
    source_id = _fred_source_id(session)
    beobachtet = datetime(2026, 1, 1, tzinfo=UTC)

    original = record_observation(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=beobachtet,
    )
    revision = record_observation(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.4"},  # rueckwirkend korrigierter Wert
        beobachtungs_zeitpunkt=beobachtet,
    )

    assert session.query(MarketDataBronze).count() == 2
    assert revision.id != original.id

    # AC1: die urspruengliche Zeile ist nicht veraendert worden.
    unveraendert = session.get(
        MarketDataBronze, {"id": original.id, "ingested_at": original.ingested_at}
    )
    assert unveraendert is not None
    assert unveraendert.payload == {"value": "3.1"}


def test_replay_before_revision_returns_original_value(session: Session) -> None:
    """@trace datenqualitaet#AC2 — eine Replay-Abfrage "Stand X" (vor Eintreffen
    einer spaeteren Revision) liefert exakt die Datenlage, die zu X bekannt
    war; die spaetere Revision fliesst nicht rueckwirkend ein."""
    source_id = _fred_source_id(session)
    beobachtet = datetime(2026, 1, 1, tzinfo=UTC)

    original = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        observed_at=beobachtet,
        ingested_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    session.add(original)
    session.commit()

    revision = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.4"},
        observed_at=beobachtet,
        ingested_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    session.add(revision)
    session.commit()

    stand_vor_revision = replay(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        stand_zeitpunkt=datetime(2026, 1, 10, tzinfo=UTC),
    )
    stand_nach_revision = replay(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        stand_zeitpunkt=datetime(2026, 2, 15, tzinfo=UTC),
    )

    assert stand_vor_revision is not None
    assert stand_vor_revision.payload == {"value": "3.1"}
    assert stand_nach_revision is not None
    assert stand_nach_revision.payload == {"value": "3.4"}


def test_replay_returns_none_before_first_ingest(session: Session) -> None:
    """@trace datenqualitaet#AC2 — vor dem ersten Empfang eines Ereignisses
    liefert eine Replay-Abfrage `None` (keine Datenlage vorhanden)."""
    source_id = _fred_source_id(session)
    original = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    session.add(original)
    session.commit()

    stand_davor = replay(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        stand_zeitpunkt=datetime(2026, 1, 4, tzinfo=UTC),
    )

    assert stand_davor is None
