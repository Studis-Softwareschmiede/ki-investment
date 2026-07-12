"""Bronze-Store: immutable, Point-in-Time-versionierte Ablage roher Datenpunkte.

Deckt `docs/specs/datenqualitaet.md` AC1/AC2/AC9/AC10:

- **AC1 (immutabel/append-only):** Dieses Modul bietet ausschliesslich
  `record_observation()` (fügt an) und `replay()` (liest) — keine
  Update-/Delete-Funktion existiert. Die Migration
  `<REVISION>_create_market_data_bronze.py` sichert dieselbe Invariante
  zusätzlich DB-seitig per BEFORE-UPDATE/DELETE-Trigger (zweite Ebene,
  analog BR-101/`category_weight`).
- **AC2 (Point-in-Time + Replay „Stand X"):** `observed_at` ist der fachliche
  Beobachtungszeitpunkt (Vertrag: `beobachtungs_zeitpunkt`), `ingested_at`
  der Empfangszeitpunkt (Vertrag: `empfangs_zeitpunkt`). `replay()` liefert
  je (Quelle, Event-ID) die Version, deren `ingested_at` zum Zeitpunkt
  `stand_zeitpunkt` bereits bekannt war — spätere Revisionen (grösseres
  `ingested_at`) fliessen nicht rückwirkend ein.
- **AC9 (Idempotenz, deckt E2):** Trifft für eine bereits bekannte
  `(data_source_id, source_event_id)`-Kombination ein inhaltlich
  IDENTISCHER Datenpunkt erneut ein (gleicher `payload` + gleicher
  `observed_at`), wird KEINE neue Zeile angelegt — `record_observation()`
  gibt die bestehende Zeile unverändert zurück (kein Duplikat, keine
  doppelte Weiterverarbeitung). Nebenläufigkeits-Härtung (Iteration 2, nach
  Reviewer-Befund gegen Postgres 17 gemessen — siehe
  `.claude/lessons/coder.md`): `record_observation()` erwirkt VOR der
  Lese-Prüfung eine Postgres-Advisory-Xact-Lock je Ereignis-Identität
  (`_erwirke_dedupe_lock`), damit zwei parallele, noch nicht committete
  Aufrufe für dieselbe `(data_source_id, source_event_id)` seriell statt
  gleichzeitig laufen (schliesst die READ-COMMITTED-Sichtbarkeitslücke, in
  der zwei Transaktionen sich gegenseitig nicht sehen). Der DB-seitige
  BEFORE-INSERT-Trigger wirft bei einem trotzdem durchgeschlüpften Duplikat
  KEIN stilles `RETURN NULL` mehr, sondern eine abfangbare
  `IntegrityError` (SQLSTATE `unique_violation`) — `record_observation()`
  fängt diese, verwirft das eigene (potenziell verwaiste) ORM-Objekt und
  lädt die tatsächlich massgebliche Zeile frisch nach, statt sie
  zurückzugeben.
- **AC10 (Revision, deckt A1):** Trifft für dieselbe `(data_source_id,
  source_event_id)`-Kombination ein inhaltlich ABWEICHENDER Datenpunkt ein
  (z. B. eine rückwirkende FRED-Korrektur), wird die frühere Zeile NICHT
  überschrieben — es entsteht eine zusätzliche Zeile (neue
  Point-in-Time-Version, jüngeres `ingested_at`). Ein `replay()` mit einem
  `stand_zeitpunkt` vor der Revision bleibt stabil (liefert weiterhin die
  alte Version).

Edge-Case-Hinweis (Spec „Event-ID kollidiert mit inhaltlich abweichendem
Datenpunkt"): diese Spec-Zeile ist explizit den ACs der Validierungs-Schicht
zugeordnet (AC7/AC8, S-023/S-024, NICHT Teil dieser Story). Das hier gebaute
Verhalten verletzt deren Kern-Invariante ("nicht stillschweigend
überschreiben") an keiner Stelle — jede abweichende Ankunft erzeugt eine
zusätzliche Zeile statt eines Updates; die Klassifikation "das ist eigentlich
eine ungültige Kollision, keine legitime Revision" trifft der künftige
Validierungs-Layer (AC7/AC8), nicht dieses Modul.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MarketDataBronze


def _als_utc_naiv(zeitpunkt: datetime) -> datetime:
    """Normalisiert einen Zeitpunkt fuer den Inhaltsvergleich (AC9/AC10).

    SQLite (Test-Backend, kein natives `TIMESTAMPTZ`) liefert `tzinfo` bei
    gespeicherten Zeitstempeln nicht zuverlaessig zurueck, waehrend
    PostgreSQL (`TIMESTAMPTZ`, Produktiv-Backend) `tzinfo` konsistent
    bewahrt. Der Vergleich normalisiert daher auf UTC-naiv, damit derselbe
    Zeitpunkt unabhaengig vom Backend als identisch erkannt wird — der
    fachliche Moment (nicht die Wall-Clock-Repraesentation) entscheidet.
    """
    if zeitpunkt.tzinfo is not None:
        return zeitpunkt.astimezone(UTC).replace(tzinfo=None)
    return zeitpunkt


def _erwirke_dedupe_lock(
    session: Session, *, data_source_id: uuid.UUID, source_event_id: str
) -> None:
    """Serialisiert konkurrierende `record_observation()`-Aufrufe fuer
    dieselbe Ereignis-Identitaet (AC9-Nebenlaeufigkeits-Haertung, Iteration 2).

    Ohne diese Sperre sehen zwei parallele, noch nicht committete
    Transaktionen unter READ COMMITTED die jeweils andere (uncommittete)
    Zeile nicht — beide wuerden die "existiert schon?"-Pruefung negativ
    beantworten und je eine Zeile fuer dasselbe Ereignis anlegen (empirisch
    gegen Postgres 17 gemessen, siehe `.claude/lessons/coder.md`).
    `pg_advisory_xact_lock` blockiert die zweite Transaktion, bis die erste
    committet (und damit ihre Zeile sichtbar) oder rollt zurueck hat; die
    Sperre wird automatisch am Transaktionsende freigegeben.

    Nur unter PostgreSQL verfuegbar. Unter SQLite (Test-Backend) existiert
    das Nebenlaeufigkeitsproblem nicht (Tests laufen sequenziell,
    in-process) — dort ist dies ein No-Op.
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    lock_schluessel = f"{data_source_id}:{source_event_id}"
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:schluessel))"),
        {"schluessel": lock_schluessel},
    )


def record_observation(
    session: Session,
    *,
    data_source_id: uuid.UUID,
    source_event_id: str,
    payload: Any,
    beobachtungs_zeitpunkt: datetime,
    anlageklassen_tag: int | None = None,
    symbol: str | None = None,
    quality_indicator: str | None = None,
) -> MarketDataBronze:
    """Legt einen Bronze-Datensatz idempotent/versioniert ab.

    Rückgabe: die massgebliche Zeile — entweder die neu angelegte (erste
    Version oder neue Revision) oder die bereits existierende (idempotenter
    Treffer, AC9).
    """
    # Nebenlaeufigkeits-Haertung (Iteration 2): schliesst die
    # READ-COMMITTED-Race-Luecke, bevor die "existiert schon?"-Pruefung
    # ueberhaupt liest (siehe _erwirke_dedupe_lock-Docstring).
    _erwirke_dedupe_lock(
        session, data_source_id=data_source_id, source_event_id=source_event_id
    )

    def _lade_massgebliche_zeile() -> MarketDataBronze | None:
        return session.execute(
            select(MarketDataBronze)
            .where(
                MarketDataBronze.data_source_id == data_source_id,
                MarketDataBronze.source_event_id == source_event_id,
            )
            .order_by(MarketDataBronze.ingested_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    bestehende = _lade_massgebliche_zeile()

    if (
        bestehende is not None
        and bestehende.payload == payload
        and _als_utc_naiv(bestehende.observed_at) == _als_utc_naiv(beobachtungs_zeitpunkt)
    ):
        # AC9/E2: dasselbe Ereignis (gleiche Event-ID, gleicher Inhalt) ist
        # bereits bekannt — idempotent, kein Duplikat, keine neue Zeile.
        return bestehende

    neue_zeile = MarketDataBronze(
        data_source_id=data_source_id,
        source_event_id=source_event_id,
        payload=payload,
        observed_at=beobachtungs_zeitpunkt,
        asset_class_tag=anlageklassen_tag,
        symbol=symbol,
        quality_indicator=quality_indicator,
    )
    try:
        with session.begin_nested():
            session.add(neue_zeile)
            session.flush()
    except IntegrityError:
        # Der DB-seitige BEFORE-INSERT-Trigger (zweite Sicherung, BR-122) hat
        # den Insert als Duplikat abgelehnt (abfangbare Exception statt
        # stillem `RETURN NULL` — Iteration-2-Fix nach Reviewer-Befund). Das
        # ROLLBACK der SAVEPOINT (`begin_nested()`) hat `neue_zeile`
        # automatisch aus der Session entfernt (kanonisches SQLAlchemy-Muster
        # fuer "insert-or-select unter Race" — kein manuelles `expunge()`
        # noetig/moeglich). Die tatsaechlich massgebliche (bereits
        # vorhandene) Zeile wird frisch nachgeladen und zurueckgegeben — nie
        # das verwaiste eigene Objekt.
        massgebliche_zeile = _lade_massgebliche_zeile()
        if massgebliche_zeile is None:  # pragma: no cover - sollte unerreichbar sein
            raise
        return massgebliche_zeile
    return neue_zeile


def replay(
    session: Session,
    *,
    data_source_id: uuid.UUID,
    source_event_id: str,
    stand_zeitpunkt: datetime,
) -> MarketDataBronze | None:
    """Point-in-Time-Replay (AC2): liefert die Version von
    `(data_source_id, source_event_id)`, die zum Zeitpunkt `stand_zeitpunkt`
    bereits empfangen war (`ingested_at <= stand_zeitpunkt`), jeweils die
    zuletzt eingetroffene. Spätere Revisionen (grösseres `ingested_at`)
    fliessen nicht rückwirkend ein — gibt `None`, wenn zu `stand_zeitpunkt`
    noch keine Version bekannt war.
    """
    return session.execute(
        select(MarketDataBronze)
        .where(
            MarketDataBronze.data_source_id == data_source_id,
            MarketDataBronze.source_event_id == source_event_id,
            MarketDataBronze.ingested_at <= stand_zeitpunkt,
        )
        .order_by(MarketDataBronze.ingested_at.desc())
        .limit(1)
    ).scalar_one_or_none()
