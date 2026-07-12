"""Tests fuer den Silver-Store `app.db.silver` (Story S-024).

Covers (datenqualitaet): AC3, AC6

- AC3 (Normalisierung, reproduzierbar aus Bronze):
  `test_record_silver_observation_derives_row_from_valid_bronze_zeile`
  belegt die Kern-Ableitung eines Silver-Datensatzes aus einer konkreten
  Bronze-Zeile (Spec-Vertrag "Silver-Datensatz").
  `test_record_silver_observation_rejects_invalid_bronze_kandidat` belegt
  die NFR "nur valide Kandidaten duerfen nach Silver"
  (`validate_bronze_kandidat`-Gate).
  `test_record_silver_observation_is_idempotent_for_same_bronze_version`
  belegt Reproduzierbarkeit: derselbe Bronze-Zeile-Aufruf dupliziert keinen
  Silver-Datensatz.
  `test_rebuild_silver_series_uses_latest_version_per_event_id` belegt, dass
  bei mehreren Bronze-Versionen desselben Ereignisses (Revision, AC10) nur
  die zuletzt bekannte Version in die Silver-Reihe einfliesst
  (Point-in-Time-Konsistenz).
  `test_rebuild_silver_series_for_symbol_skips_invalid_bronze_candidates`
  belegt, dass ungueltige Bronze-Kandidaten bei der Reihen-Ableitung
  uebersprungen werden (NFR), ohne den gesamten Lauf abzubrechen.
  Iteration-2-Regressionsschutz (Reviewer-Befund, empirisch gegen Postgres 17
  gemessen — siehe `.claude/lessons/coder.md`):
  `test_rebuild_silver_series_for_symbol_does_not_delete_other_data_source_rows`
  belegt den Critical-Fix (Cross-Data-Source-Datenverlust): ein Rebuild fuer
  Quelle A loescht/beruehrt keine Silver-Zeilen einer anderen Quelle B, auch
  wenn beide dieselbe `source_event_id`-Zeichenkette fuer dasselbe Symbol
  verwenden.
  `test_silver_dedupe_lock_is_noop_under_sqlite` belegt, dass
  `_erwirke_silver_dedupe_lock()` unter SQLite (kein `pg_advisory_xact_lock`)
  folgenlos bleibt.
  `test_record_silver_observation_flush_conflict_reloads_authoritative_row_not_crash`
  belegt den Important-Fix (Nebenlaeufigkeits-Haertung): ein von der
  DB-seitigen zweiten Sicherung (`uq_market_data_silver_bronze_version`)
  abgelehnter Insert wird als `IntegrityError` abgefangen und die
  tatsaechlich massgebliche Zeile zurueckgegeben, statt eines Duplikats oder
  Crashs.

- AC6 (Corporate-Actions-Adjustierung, deckt A2):
  `test_berechne_adjustierten_wert_returns_unchanged_value_without_relevant_action`
  belegt den Basisfall (keine Aktion -> kein Adjustment).
  `test_berechne_adjustierten_wert_applies_split_adjustment_without_artificial_jump`
  belegt die Kern-Invariante: ein 4-fuer-1-Split adjustiert den
  vorherigen Rohwert so, dass die adjustierte Reihe am Split-Datum keinen
  kuenstlichen Sprung zeigt.
  `test_berechne_adjustierten_wert_applies_cumulative_factor_for_multiple_actions`
  belegt die kumulative multiplikative Anwendung mehrerer nachfolgender
  Aktionen.
  `test_rebuild_silver_series_for_symbol_reflects_retroactive_corporate_action`
  belegt den Edge-Case "Corporate Action rueckwirkend gemeldet": die
  historische Silver-Reihe wird neu (adjustiert) abgeleitet, Bronze bleibt
  unveraendert.

SQLite (in-memory) reicht aus (reiner SQLAlchemy-/Python-Code, kein
Postgres-spezifisches Konstrukt wie Partitionierung involviert), analog
`tests/db/test_bronze.py`/`tests/db/test_validation.py`. Die reale
Nebenlaeufigkeit (zwei offene Postgres-Transaktionen, `pg_advisory_xact_lock`
schliesst die Race-Luecke) ist nur unter Postgres real pruefbar — der
DB-seitige Unique-Index-Reject wird hier per SQLAlchemy-`before_flush`-Event
simuliert (analog `tests/db/test_bronze.py`).
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
from app.db.models import AssetClass, DataSource, MarketDataBronze, MarketDataSilver
from app.db.silver import (
    CorporateAction,
    UngueltigerBronzeKandidatError,
    _erwirke_silver_dedupe_lock,
    berechne_adjustierten_wert,
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
    data_source_id: uuid.UUID | None = None,
) -> MarketDataBronze:
    zeile = MarketDataBronze(
        data_source_id=data_source_id if data_source_id is not None else _source_id(session),
        source_event_id=source_event_id,
        symbol=symbol,
        payload={"preis": preis},
        observed_at=observed_at,
        asset_class_tag=asset_class_tag,
    )
    session.add(zeile)
    session.commit()
    return zeile


def test_record_silver_observation_derives_row_from_valid_bronze_zeile(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC3 — aus einer validen Bronze-Zeile wird ein
    Silver-Datensatz gemaess Spec-Vertrag abgeleitet (event_id,
    normalisierter_wert, einheit, abgeleitet_aus: bronze_version)."""
    bronze_zeile = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    silber_zeile = record_silver_observation(
        session,
        bronze_zeile=bronze_zeile,
        normalisierter_wert=Decimal("400.00000000"),
        einheit="CHF",
    )

    assert silber_zeile.source_event_id == "ibkr:AAPL:2026-01-01"
    assert silber_zeile.normalisierter_wert == Decimal("400.00000000")
    assert silber_zeile.einheit == "CHF"
    assert silber_zeile.bronze_id == bronze_zeile.id
    assert silber_zeile.bronze_ingested_at == bronze_zeile.ingested_at
    assert silber_zeile.adjustierungs_info is None
    assert session.query(MarketDataSilver).count() == 1


def test_record_silver_observation_rejects_invalid_bronze_kandidat(session: Session) -> None:
    """@trace datenqualitaet#AC3 — NFR "nur valide Kandidaten duerfen nach
    Silver": ein Bronze-Kandidat mit ungueltigem anlageklassen_tag (ausserhalb
    1..11, AC7) wird zurueckgewiesen, es entsteht kein Silver-Datensatz."""
    ungueltige_zeile = MarketDataBronze(
        data_source_id=_source_id(session),
        source_event_id="ibkr:AAPL:invalid",
        symbol="AAPL",
        payload={"preis": "400"},
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        asset_class_tag=42,  # ausserhalb des Wertebereichs 1..11
    )

    with pytest.raises(UngueltigerBronzeKandidatError):
        record_silver_observation(
            session,
            bronze_zeile=ungueltige_zeile,
            normalisierter_wert=Decimal("400"),
            einheit="CHF",
        )

    assert session.query(MarketDataSilver).count() == 0


def test_record_silver_observation_is_idempotent_for_same_bronze_version(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC3 — Reproduzierbarkeit: ein zweiter Aufruf
    fuer dieselbe Bronze-Version legt keinen weiteren Silver-Datensatz an,
    sondern liefert den bestehenden zurueck."""
    bronze_zeile = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    erste = record_silver_observation(
        session, bronze_zeile=bronze_zeile, normalisierter_wert=Decimal("400"), einheit="CHF"
    )
    zweite = record_silver_observation(
        session, bronze_zeile=bronze_zeile, normalisierter_wert=Decimal("400"), einheit="CHF"
    )

    assert zweite.id == erste.id
    assert session.query(MarketDataSilver).count() == 1


def test_berechne_adjustierten_wert_returns_unchanged_value_without_relevant_action() -> None:
    """@trace datenqualitaet#AC6 — ohne eine fuer das Symbol/den Zeitpunkt
    relevante Corporate Action bleibt der Rohwert unveraendert, kein
    Adjustierungs-Vermerk."""
    adjustiert, info = berechne_adjustierten_wert(
        Decimal("400"),
        datetime(2026, 1, 1, tzinfo=UTC),
        symbol="AAPL",
        aktionen=[],
    )

    assert adjustiert == Decimal("400")
    assert info is None


def test_berechne_adjustierten_wert_applies_split_adjustment_without_artificial_jump() -> None:
    """@trace datenqualitaet#AC6 — ein 4-fuer-1-Split (Faktor 0.25) nach dem
    Beobachtungszeitpunkt adjustiert den historischen Rohwert so, dass er
    mit dem post-Split-Niveau uebereinstimmt (kein kuenstlicher Sprung an
    der Split-Grenze, deckt A2)."""
    split = CorporateAction(
        symbol="AAPL",
        wirksam_ab=datetime(2026, 6, 1, tzinfo=UTC),
        aktions_typ="split",
        faktor=Decimal("0.25"),
    )

    vor_split_adjustiert, info = berechne_adjustierten_wert(
        Decimal("400"),  # Rohwert VOR dem Split
        datetime(2026, 1, 1, tzinfo=UTC),
        symbol="AAPL",
        aktionen=[split],
    )
    nach_split_adjustiert, info_nach = berechne_adjustierten_wert(
        Decimal("100"),  # Rohwert NACH dem Split (bereits auf neuem Niveau)
        datetime(2026, 7, 1, tzinfo=UTC),
        symbol="AAPL",
        aktionen=[split],
    )

    # Adjustierter Vor-Split-Wert (400 * 0.25 = 100) == unadjustierter
    # Nach-Split-Wert (100) -- kein kuenstlicher Sprung.
    assert vor_split_adjustiert == Decimal("100.00")
    assert nach_split_adjustiert == Decimal("100")
    assert info == {
        "angewandte_aktionen": [
            {"typ": "split", "wirksam_ab": "2026-06-01T00:00:00+00:00", "faktor": "0.25"}
        ],
        "kumulierter_faktor": "0.25",
    }
    assert info_nach is None  # keine Aktion mehr NACH dem Nach-Split-Zeitpunkt


def test_berechne_adjustierten_wert_applies_cumulative_factor_for_multiple_actions() -> None:
    """@trace datenqualitaet#AC6 — zwei nachfolgende Corporate Actions
    (Split + Dividende) werden kumulativ multiplikativ angewandt."""
    split = CorporateAction(
        symbol="AAPL",
        wirksam_ab=datetime(2026, 3, 1, tzinfo=UTC),
        aktions_typ="split",
        faktor=Decimal("0.5"),
    )
    dividende = CorporateAction(
        symbol="AAPL",
        wirksam_ab=datetime(2026, 6, 1, tzinfo=UTC),
        aktions_typ="dividende",
        faktor=Decimal("0.9"),
    )

    adjustiert, info = berechne_adjustierten_wert(
        Decimal("200"),
        datetime(2026, 1, 1, tzinfo=UTC),
        symbol="AAPL",
        aktionen=[dividende, split],  # Reihenfolge im Aufruf beliebig
    )

    assert adjustiert == Decimal("90.000")  # 200 * 0.5 * 0.9
    assert info["kumulierter_faktor"] == "0.45"
    assert len(info["angewandte_aktionen"]) == 2
    # chronologisch sortiert angewandt (Split zuerst, dann Dividende).
    assert info["angewandte_aktionen"][0]["typ"] == "split"
    assert info["angewandte_aktionen"][1]["typ"] == "dividende"


def test_rebuild_silver_series_uses_latest_version_per_event_id(session: Session) -> None:
    """@trace datenqualitaet#AC3 — bei mehreren Bronze-Versionen desselben
    Ereignisses (Revision, AC10) fliesst nur die zuletzt bekannte Version in
    die abgeleitete Silver-Reihe ein (Point-in-Time-Konsistenz, keine
    Duplikate)."""
    source_id = _source_id(session)
    original = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="ibkr:AAPL:2026-01-01",
        symbol="AAPL",
        payload={"preis": "100"},
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2026, 1, 1, 12, tzinfo=UTC),
        asset_class_tag=1,
    )
    revision = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="ibkr:AAPL:2026-01-01",
        symbol="AAPL",
        payload={"preis": "105"},  # korrigierter Wert
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2026, 1, 2, tzinfo=UTC),  # spaeter empfangen
        asset_class_tag=1,
    )
    session.add_all([original, revision])
    session.commit()

    ergebnisse = rebuild_silver_series_for_symbol(
        session,
        data_source_id=source_id,
        symbol="AAPL",
        wert_extraktor=lambda zeile: Decimal(zeile.payload["preis"]),
        einheit="CHF",
    )

    assert len(ergebnisse) == 1
    assert ergebnisse[0].normalisierter_wert == Decimal("105")
    assert ergebnisse[0].bronze_id == revision.id


def test_rebuild_silver_series_for_symbol_skips_invalid_bronze_candidates(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC3 — ein ungueltiger Bronze-Kandidat
    (anlageklassen_tag ausserhalb 1..11) wird bei der Reihen-Ableitung
    uebersprungen, ohne den gesamten Lauf abzubrechen (NFR)."""
    source_id = _source_id(session)
    gueltig = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    ungueltig = MarketDataBronze(
        data_source_id=source_id,
        source_event_id="ibkr:AAPL:2026-01-02",
        symbol="AAPL",
        payload={"preis": "410"},
        observed_at=datetime(2026, 1, 2, tzinfo=UTC),
        asset_class_tag=99,
    )
    session.add(ungueltig)
    session.commit()

    ergebnisse = rebuild_silver_series_for_symbol(
        session,
        data_source_id=source_id,
        symbol="AAPL",
        wert_extraktor=lambda zeile: Decimal(zeile.payload["preis"]),
        einheit="CHF",
    )

    assert len(ergebnisse) == 1
    assert ergebnisse[0].bronze_id == gueltig.id


def test_rebuild_silver_series_for_symbol_reflects_retroactive_corporate_action(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC6 — Edge-Case "Corporate Action rueckwirkend
    gemeldet": die historische Silver-Reihe wird nach Bekanntwerden einer
    Corporate Action neu (adjustiert) abgeleitet; Bronze bleibt in jedem
    Fall unveraendert."""
    source_id = _source_id(session)
    vor_split = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:2026-01-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        preis="400",
    )

    # Erste Ableitung -- noch ohne Kenntnis des Splits.
    erste_ableitung = rebuild_silver_series_for_symbol(
        session,
        data_source_id=source_id,
        symbol="AAPL",
        wert_extraktor=lambda zeile: Decimal(zeile.payload["preis"]),
        einheit="CHF",
    )
    assert erste_ableitung[0].normalisierter_wert == Decimal("400")

    # Split wird jetzt (rueckwirkend) bekannt -- Reihe wird neu abgeleitet.
    split = CorporateAction(
        symbol="AAPL",
        wirksam_ab=datetime(2026, 6, 1, tzinfo=UTC),
        aktions_typ="split",
        faktor=Decimal("0.25"),
    )
    zweite_ableitung = rebuild_silver_series_for_symbol(
        session,
        data_source_id=source_id,
        symbol="AAPL",
        wert_extraktor=lambda zeile: Decimal(zeile.payload["preis"]),
        einheit="CHF",
        aktionen=[split],
    )

    assert len(zweite_ableitung) == 1
    assert zweite_ableitung[0].normalisierter_wert == Decimal("100.00")
    assert zweite_ableitung[0].adjustierungs_info is not None
    # Keine Duplikat-Zeile -- die alte (unadjustierte) Silver-Zeile wurde
    # durch die neu abgeleitete ersetzt.
    assert session.query(MarketDataSilver).count() == 1

    # Bronze bleibt unveraendert (AC6-Edge-Case-Invariante).
    unveraenderte_bronze_zeile = session.execute(
        select(MarketDataBronze).where(MarketDataBronze.id == vor_split.id)
    ).scalar_one()
    assert unveraenderte_bronze_zeile.payload == {"preis": "400"}


def test_rebuild_silver_series_for_symbol_does_not_delete_other_data_source_rows(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC3 — Iteration-2-Regressionsschutz (Critical,
    Reviewer-Befund, empirisch gegen Postgres 17 belegt): ein Rebuild fuer
    Quelle A darf KEINE Silver-Zeile einer anderen Quelle B loeschen/
    beruehren, selbst wenn beide Quellen zufaellig dieselbe
    `source_event_id`-Zeichenkette fuer dasselbe Symbol verwenden
    (`(data_source_id, source_event_id)` ist laut BR-122/data-model.md die
    einzige eindeutige Ereignis-Identitaet, nicht `source_event_id` allein)."""
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

    # Kollidierende Event-ID: beide Quellen liefern "AAPL:2026-01-01" fuer
    # dasselbe Symbol.
    _bronze_zeile(
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

    rebuild_silver_series_for_symbol(
        session,
        data_source_id=quelle_a,
        symbol="AAPL",
        wert_extraktor=lambda zeile: Decimal(zeile.payload["preis"]),
        einheit="CHF",
    )
    silber_b_vorher = record_silver_observation(
        session,
        bronze_zeile=bronze_b,
        normalisierter_wert=Decimal("999"),
        einheit="CHF",
    )

    # Zweiter Rebuild NUR fuer Quelle A -- darf die Silver-Zeile von Quelle B
    # nicht loeschen (frueherer Critical-Bug: DELETE filterte nur nach
    # symbol + source_event_id, ohne data_source_id).
    rebuild_silver_series_for_symbol(
        session,
        data_source_id=quelle_a,
        symbol="AAPL",
        wert_extraktor=lambda zeile: Decimal(zeile.payload["preis"]),
        einheit="CHF",
    )

    silber_b_nachher = session.execute(
        select(MarketDataSilver).where(MarketDataSilver.data_source_id == quelle_b)
    ).scalar_one()
    assert silber_b_nachher.id == silber_b_vorher.id
    assert silber_b_nachher.normalisierter_wert == Decimal("999")

    silber_a = session.execute(
        select(MarketDataSilver).where(MarketDataSilver.data_source_id == quelle_a)
    ).scalar_one()
    assert silber_a.normalisierter_wert == Decimal("400")
    assert session.query(MarketDataSilver).count() == 2


def test_silver_dedupe_lock_is_noop_under_sqlite(session: Session) -> None:
    """@trace datenqualitaet#AC3 — Iteration-2-Regressionsschutz:
    `_erwirke_silver_dedupe_lock()` (Nebenlaeufigkeits-Haertung) darf unter
    SQLite (Test-Backend, kein `pg_advisory_xact_lock`) keine Ausnahme
    werfen und keine SQL-Anweisung ausfuehren — die Funktion muss
    dialektbedingt ein reiner No-Op sein."""
    _erwirke_silver_dedupe_lock(
        session, bronze_id=uuid.uuid4(), bronze_ingested_at=datetime(2026, 1, 1, tzinfo=UTC)
    )

    # Kein Fehler ausgeloest, Session bleibt normal nutzbar.
    assert session.query(MarketDataSilver).count() == 0


def test_record_silver_observation_flush_conflict_reloads_authoritative_row_not_crash(
    session: Session,
) -> None:
    """@trace datenqualitaet#AC3 — Iteration-2-Regressionsschutz (Important,
    Reviewer-Befund): lehnt die DB-seitige zweite Sicherung
    (`uq_market_data_silver_bronze_version`) einen Insert als Duplikat ab,
    MUSS `record_silver_observation()` dies als `IntegrityError` abfangen
    und die tatsaechlich massgebliche (bereits vorhandene) Zeile
    zurueckgeben — NIE das eigene, nicht persistierte ORM-Objekt und NIE mit
    unbehandelter Exception crashen. Hier per `before_flush`-Event simuliert
    (analog `tests/db/test_bronze.py`), da SQLite keinen echten
    Postgres-Unique-Index-Reject unter Nebenlaeufigkeit ausfuehren kann."""
    bronze_zeile = _bronze_zeile(
        session,
        source_event_id="ibkr:AAPL:race",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    massgebliche_zeile = MarketDataSilver(
        bronze_id=bronze_zeile.id,
        bronze_ingested_at=bronze_zeile.ingested_at,
        data_source_id=bronze_zeile.data_source_id,
        source_event_id=bronze_zeile.source_event_id,
        symbol=bronze_zeile.symbol,
        normalisierter_wert=Decimal("400"),
        einheit="CHF",
        observed_at=bronze_zeile.observed_at,
    )
    session.add(massgebliche_zeile)
    session.commit()

    def _simuliere_unique_index_reject(sess, _flush_context, _instances) -> None:
        for objekt in sess.new:
            if (
                isinstance(objekt, MarketDataSilver)
                and objekt.bronze_id == bronze_zeile.id
                and objekt.bronze_ingested_at == bronze_zeile.ingested_at
            ):
                raise IntegrityError(
                    "INSERT INTO market_data_silver ...",
                    {},
                    Exception("simulierter Unique-Index-Reject (unique_violation)"),
                )

    event.listen(session, "before_flush", _simuliere_unique_index_reject)
    try:
        ergebnis = record_silver_observation(
            session,
            bronze_zeile=bronze_zeile,
            # Der Aufrufer sah die massgebliche Zeile nicht rechtzeitig
            # (analog zur Race-Luecke) und versucht denselben Bronze-
            # Version-Insert erneut.
            normalisierter_wert=Decimal("999"),
            einheit="CHF",
        )
    finally:
        event.remove(session, "before_flush", _simuliere_unique_index_reject)

    assert ergebnis.id == massgebliche_zeile.id
    assert ergebnis.normalisierter_wert == Decimal("400")
    # Kein Duplikat entstanden -- der abgelehnte Insert hat keine Zeile angelegt.
    assert session.query(MarketDataSilver).count() == 1
