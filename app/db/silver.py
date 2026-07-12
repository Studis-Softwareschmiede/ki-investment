"""Silver-Store: normalisierte, Corporate-Actions-adjustierte Werte, abgeleitet
aus Bronze (Story S-024).

Deckt `docs/specs/datenqualitaet.md` AC3/AC6:

- **AC3 (Normalisierung, reproduzierbar aus Bronze):**
  `record_silver_observation()` leitet aus EINER konkreten Bronze-Zeile genau
  einen Silver-Datensatz ab (`{ event_id, normalisierter_wert, einheit,
  adjustierungs_info, abgeleitet_aus: bronze_version }`, Spec-Vertrag
  "Silver-Datensatz"). **NFR "nur valide Kandidaten dürfen nach Silver":**
  jeder Aufruf validiert die zugrunde liegende Bronze-Zeile zuerst über
  `app.db.validation.validate_bronze_kandidat()` — ein invalider Kandidat
  wird mit `UngueltigerBronzeKandidatError` zurückgewiesen, es entsteht kein
  Silver-Datensatz. **Reproduzierbarkeit:** derselbe Bronze-Zeile-Aufruf mit
  denselben Adjustierungs-Parametern liefert (idempotent) denselben
  Silver-Datensatz zurück — ein bereits abgeleiteter Datensatz für dieselbe
  Bronze-Version wird nicht dupliziert, sondern unverändert zurückgegeben.
  **Nebenläufigkeits-Härtung (Iteration 2, nach Reviewer-Befund empirisch
  gegen Postgres 17 gemessen):** `record_silver_observation()` erwirkt VOR
  der Lese-Prüfung eine Postgres-Advisory-Xact-Lock je Bronze-Version
  (`_erwirke_silver_dedupe_lock`, analog `app.db.bronze`) und fängt einen
  trotzdem durchgeschlüpften `IntegrityError` aus dem physischen
  `uq_market_data_silver_bronze_version`-Unique-Index (Migration
  `cf167d0a63f5`) ab, statt zwei Duplikat-Zeilen für dieselbe Bronze-Version
  entstehen zu lassen.

- **AC6 (Corporate-Actions-Adjustierung, deckt A2):**
  `berechne_adjustierten_wert()` wendet auf einen Rohwert alle für dasselbe
  Symbol nach dessen Beobachtungszeitpunkt eingetretenen Corporate Actions
  (Splits, Dividenden) kumulativ multiplikativ an — Standard-Methodik der
  Rück-Adjustierung (adjusted = roh_wert × Π aktions_faktor), sodass eine aus
  der adjustierten Reihe abgeleitete Kennzahl keinen durch die Corporate
  Action verursachten künstlichen Sprung zeigt. Die unadjustierten
  Originalwerte bleiben unverändert in Bronze (`payload`); nur die
  Silver-Zeile trägt den adjustierten Wert + `adjustierungs_info`
  (Nachvollziehbarkeit, welche Aktionen mit welchem Faktor angewandt
  wurden).

  **Edge-Case "Corporate Action rückwirkend gemeldet":**
  `rebuild_silver_series_for_symbol()` leitet die komplette Silver-Reihe für
  `(data_source_id, symbol)` neu aus Bronze ab (bestehende Silver-Zeilen
  dieser Kombination werden zuerst entfernt, dann aus der aktuellen
  Bronze-Historie + der übergebenen (jetzt vollständigeren)
  Corporate-Actions-Liste neu berechnet) — Bronze bleibt dabei in jedem Fall
  unverändert. **Cross-Data-Source-Fix (Iteration 2, Reviewer-Befund,
  empirisch gegen Postgres 17 belegt):** die DELETE-Klausel filtert seit
  Iteration 2 zusätzlich nach `data_source_id` (jetzt eine denormalisierte
  Spalte von `MarketDataSilver`) — `(symbol, source_event_id)` allein ist
  laut BR-122/data-model.md KEINE eindeutige Ereignis-Identität, ein Rebuild
  für Quelle A hätte sonst silent auch Silver-Zeilen einer anderen Quelle B
  gelöscht, wenn beide zufällig dieselbe `source_event_id`-Zeichenkette für
  dasselbe Symbol verwenden.

  Die Berechnung/Herkunft der einzelnen `CorporateAction.faktor`-Werte (wie
  aus einem Split-Verhältnis oder einer Dividendenhöhe ein multiplikativer
  Faktor entsteht) ist eine Datenbeschaffungs-/Adapter-Frage (`[[dateneingang]]`,
  Nicht-Ziel dieser Story) — dieses Modul nimmt den Faktor bereits berechnet
  entgegen und wendet ihn konsistent (kumulativ, kein Update der
  Vergangenheit ohne erneuten Aufruf) an.

Bronze-Kompatibilität: `market_data_silver.instrument_id` aus data-model.md
ist bewusst nicht umgesetzt (die `instrument`-Tabelle existiert in dieser
Codebasis noch nicht, siehe data-model.md-Präzisierung + Coder-Handoff
S-024) — `symbol` (aus der Bronze-Zeile übernommen) übernimmt stattdessen
die fachliche Rolle, Corporate Actions dem richtigen Titel zuzuordnen.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MarketDataBronze, MarketDataSilver
from app.db.utils import als_utc_naiv
from app.db.validation import validate_bronze_kandidat


class UngueltigerBronzeKandidatError(Exception):
    """AC3-NFR: eine Bronze-Zeile, die `validate_bronze_kandidat()` als
    ungültig einstuft, darf nicht nach Silver übernommen werden."""

    def __init__(self, *, source_event_id: str, verletzte_regeln: tuple[str, ...]) -> None:
        self.source_event_id = source_event_id
        self.verletzte_regeln = verletzte_regeln
        super().__init__(
            f"Bronze-Kandidat '{source_event_id}' ist ungueltig "
            f"({', '.join(verletzte_regeln)}) und darf nicht nach Silver."
        )


@dataclass(frozen=True)
class CorporateAction:
    """Eine Corporate Action (Split/Dividende) für ein Symbol (AC6).

    `faktor` ist bereits der multiplikative Rück-Adjustierungsfaktor, der auf
    historische (vor `wirksam_ab` liegende) Rohwerte angewandt wird — für
    einen n-für-1-Split entspricht das `1/n` (z.B. 4-für-1-Split → 0.25), für
    eine Dividende dem Verhältnis (Schlusskurs − Dividende) / Schlusskurs.
    Die Berechnung des konkreten Faktors ist Sache des Aufrufers/der
    Datenquelle, nicht dieses Moduls.
    """

    symbol: str
    wirksam_ab: datetime
    aktions_typ: str
    faktor: Decimal


def berechne_adjustierten_wert(
    roh_wert: Decimal,
    beobachtungs_zeitpunkt: datetime,
    *,
    symbol: str,
    aktionen: Sequence[CorporateAction],
) -> tuple[Decimal, dict[str, Any] | None]:
    """AC6: adjustiert `roh_wert` kumulativ mit allen Corporate Actions
    desselben Symbols, deren `wirksam_ab` NACH `beobachtungs_zeitpunkt` liegt
    (Standard-Rück-Adjustierung — spätere Aktionen wirken auf frühere
    Beobachtungen zurück, damit die adjustierte Reihe keinen künstlichen
    Sprung an der Aktions-Grenze zeigt). Gibt `(roh_wert, None)` zurück, wenn
    keine passende Aktion vorliegt (kein Adjustment nötig)."""
    relevante = sorted(
        (
            aktion
            for aktion in aktionen
            if aktion.symbol == symbol
            and als_utc_naiv(aktion.wirksam_ab) > als_utc_naiv(beobachtungs_zeitpunkt)
        ),
        key=lambda aktion: aktion.wirksam_ab,
    )
    if not relevante:
        return roh_wert, None

    kumulierter_faktor = Decimal("1")
    angewandte_aktionen: list[dict[str, Any]] = []
    for aktion in relevante:
        kumulierter_faktor *= aktion.faktor
        angewandte_aktionen.append(
            {
                "typ": aktion.aktions_typ,
                "wirksam_ab": aktion.wirksam_ab.isoformat(),
                "faktor": str(aktion.faktor),
            }
        )

    adjustierter_wert = roh_wert * kumulierter_faktor
    adjustierungs_info = {
        "angewandte_aktionen": angewandte_aktionen,
        "kumulierter_faktor": str(kumulierter_faktor),
    }
    return adjustierter_wert, adjustierungs_info


def _erwirke_silver_dedupe_lock(
    session: Session, *, bronze_id: uuid.UUID, bronze_ingested_at: datetime
) -> None:
    """Serialisiert konkurrierende `record_silver_observation()`-Aufrufe fuer
    dieselbe Bronze-Version (Iteration-2-Nebenlaeufigkeits-Haertung,
    Reviewer-Befund, empirisch gegen Postgres 17 gemessen — siehe
    `.claude/lessons/coder.md`): ohne Lock legten zwei parallele, noch nicht
    committete Aufrufe fuer DIESELBE Bronze-Version zwei Silver-Duplikate an
    (die "existiert schon?"-Lese-Pruefung sah unter READ COMMITTED die
    jeweils andere, uncommittete Transaktion nicht). Analog
    `app.db.bronze._erwirke_dedupe_lock`, hier keyed auf `(bronze_id,
    bronze_ingested_at)` statt `(data_source_id, source_event_id)`.

    Nur unter PostgreSQL wirksam; unter SQLite (Test-Backend) ist dies ein
    No-Op (kein `pg_advisory_xact_lock` verfuegbar, Nebenlaeufigkeitsproblem
    existiert dort strukturell nicht — Tests laufen sequenziell/in-process).
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    lock_schluessel = f"{bronze_id}:{bronze_ingested_at.isoformat()}"
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:schluessel))"),
        {"schluessel": lock_schluessel},
    )


def record_silver_observation(
    session: Session,
    *,
    bronze_zeile: MarketDataBronze,
    normalisierter_wert: Decimal,
    einheit: str,
    adjustierungs_info: dict[str, Any] | None = None,
) -> MarketDataSilver:
    """AC3: leitet aus einer konkreten (bereits validen) Bronze-Zeile genau
    einen Silver-Datensatz ab und persistiert ihn.

    Weist `bronze_zeile` per `validate_bronze_kandidat()` als ungültig
    zurück (`UngueltigerBronzeKandidatError`), statt einen Silver-Datensatz
    aus einem ungültigen Kandidaten zu erzeugen (NFR "nur valide Kandidaten
    dürfen nach Silver"). Ist für dieselbe Bronze-Version bereits ein
    Silver-Datensatz vorhanden, wird dieser unverändert zurückgegeben
    (idempotent, keine Duplikat-Zeile — Reproduzierbarkeit).

    Nebenläufigkeits-Härtung (Iteration 2, Reviewer-Befund): erwirkt VOR der
    Lese-Prüfung eine Postgres-Advisory-Xact-Lock je Bronze-Version
    (`_erwirke_silver_dedupe_lock`) und fängt einen trotzdem durchgeschlüpften
    `IntegrityError` aus dem physischen `uq_market_data_silver_bronze_version`-
    Unique-Index ab (Migration `cf167d0a63f5`) — lädt dann die tatsächlich
    massgebliche (bereits vorhandene) Zeile frisch nach, statt ein
    verwaistes eigenes ORM-Objekt zurückzugeben.
    """
    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=bronze_zeile.data_source_id,
        source_event_id=bronze_zeile.source_event_id,
        payload=bronze_zeile.payload,
        beobachtungs_zeitpunkt=bronze_zeile.observed_at,
        anlageklassen_tag=bronze_zeile.asset_class_tag,
    )
    if not ergebnis.valide:
        raise UngueltigerBronzeKandidatError(
            source_event_id=bronze_zeile.source_event_id,
            verletzte_regeln=ergebnis.verletzte_regeln,
        )

    _erwirke_silver_dedupe_lock(
        session, bronze_id=bronze_zeile.id, bronze_ingested_at=bronze_zeile.ingested_at
    )

    def _lade_bestehende_zeile() -> MarketDataSilver | None:
        return session.execute(
            select(MarketDataSilver).where(
                MarketDataSilver.bronze_id == bronze_zeile.id,
                MarketDataSilver.bronze_ingested_at == bronze_zeile.ingested_at,
            )
        ).scalar_one_or_none()

    bestehende = _lade_bestehende_zeile()
    if bestehende is not None:
        return bestehende

    zeile = MarketDataSilver(
        bronze_id=bronze_zeile.id,
        bronze_ingested_at=bronze_zeile.ingested_at,
        data_source_id=bronze_zeile.data_source_id,
        source_event_id=bronze_zeile.source_event_id,
        symbol=bronze_zeile.symbol,
        normalisierter_wert=normalisierter_wert,
        einheit=einheit,
        adjustierungs_info=adjustierungs_info,
        observed_at=bronze_zeile.observed_at,
    )
    try:
        with session.begin_nested():
            session.add(zeile)
            session.flush()
    except IntegrityError:
        # `uq_market_data_silver_bronze_version` (zweite Sicherung neben dem
        # Advisory-Lock) hat den Insert als Duplikat abgelehnt — das
        # ROLLBACK der SAVEPOINT entfernt `zeile` automatisch aus der
        # Session (kanonisches SQLAlchemy-Muster fuer "insert-or-select
        # unter Race", analog `app.db.bronze.record_observation`).
        massgebliche_zeile = _lade_bestehende_zeile()
        if massgebliche_zeile is None:  # pragma: no cover - sollte unerreichbar sein
            raise
        return massgebliche_zeile
    return zeile


def rebuild_silver_series_for_symbol(
    session: Session,
    *,
    data_source_id: uuid.UUID,
    symbol: str,
    wert_extraktor: Callable[[MarketDataBronze], Decimal],
    einheit: str,
    aktionen: Sequence[CorporateAction] = (),
) -> list[MarketDataSilver]:
    """AC3-NFR (jederzeit aus Bronze rekonstruierbar) + AC6-Edge-Case
    (rückwirkend gemeldete Corporate Action): leitet die komplette
    Silver-Reihe für `(data_source_id, symbol)` NEU aus Bronze ab.

    Bestehende Silver-Zeilen dieser Kombination werden zuerst entfernt
    (vollständige Neuableitung statt partiellem Update — vermeidet
    inkonsistente Misch-Zustände zwischen alter/neuer Adjustierung), Bronze
    bleibt in jedem Fall unverändert. Je Ereignis-Identität
    (`source_event_id`) fließt nur die zuletzt bekannte Bronze-Version ein
    (Point-in-Time-Semantik analog `app.db.bronze.replay`); ungültige
    Kandidaten (`validate_bronze_kandidat`) werden übersprungen, ohne
    erneut protokolliert zu werden (das hat der Validierungs-Layer beim
    ursprünglichen Eintreffen bereits getan, AC7/AC8).
    """
    bronze_alle = (
        session.execute(
            select(MarketDataBronze).where(
                MarketDataBronze.data_source_id == data_source_id,
                MarketDataBronze.symbol == symbol,
            )
        )
        .scalars()
        .all()
    )

    neueste_je_event: dict[str, MarketDataBronze] = {}
    for zeile in bronze_alle:
        bisherige = neueste_je_event.get(zeile.source_event_id)
        if bisherige is None or zeile.ingested_at > bisherige.ingested_at:
            neueste_je_event[zeile.source_event_id] = zeile

    bronze_reihe = sorted(neueste_je_event.values(), key=lambda zeile: zeile.observed_at)
    event_ids = list(neueste_je_event.keys())

    if event_ids:
        # Iteration-2-Reviewer-Befund (Critical, empirisch gegen Postgres 17
        # belegt): DELETE MUSS zusaetzlich nach `data_source_id` filtern —
        # `(symbol, source_event_id)` allein ist KEINE eindeutige
        # Ereignis-Identitaet (BR-122/data-model.md: nur `(data_source_id,
        # source_event_id)` ist eindeutig). Ohne diesen Filter loescht ein
        # Rebuild fuer Quelle A silent auch Silver-Zeilen einer anderen
        # Quelle B, wenn beide zufaellig dieselbe `source_event_id`
        # -Zeichenkette fuer dasselbe Symbol verwenden.
        session.execute(
            delete(MarketDataSilver).where(
                MarketDataSilver.data_source_id == data_source_id,
                MarketDataSilver.symbol == symbol,
                MarketDataSilver.source_event_id.in_(event_ids),
            )
        )

    neue_zeilen: list[MarketDataSilver] = []
    for bronze_zeile in bronze_reihe:
        ergebnis = validate_bronze_kandidat(
            session,
            data_source_id=bronze_zeile.data_source_id,
            source_event_id=bronze_zeile.source_event_id,
            payload=bronze_zeile.payload,
            beobachtungs_zeitpunkt=bronze_zeile.observed_at,
            anlageklassen_tag=bronze_zeile.asset_class_tag,
        )
        if not ergebnis.valide:
            continue

        roh_wert = wert_extraktor(bronze_zeile)
        adjustierter_wert, adjustierungs_info = berechne_adjustierten_wert(
            roh_wert,
            bronze_zeile.observed_at,
            symbol=symbol,
            aktionen=aktionen,
        )
        zeile = MarketDataSilver(
            bronze_id=bronze_zeile.id,
            bronze_ingested_at=bronze_zeile.ingested_at,
            data_source_id=data_source_id,
            source_event_id=bronze_zeile.source_event_id,
            symbol=symbol,
            normalisierter_wert=adjustierter_wert,
            einheit=einheit,
            adjustierungs_info=adjustierungs_info,
            observed_at=bronze_zeile.observed_at,
        )
        session.add(zeile)
        neue_zeilen.append(zeile)

    session.flush()
    return neue_zeilen
