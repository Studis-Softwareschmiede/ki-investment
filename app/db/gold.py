"""Gold-Store: angereicherte, für Konsumenten bestimmte Werte, abgeleitet
aus Silver (+ Bronze) (Story S-051).

Deckt `docs/specs/datenqualitaet.md` AC4:

- **AC4 (Anreicherung, Konsumenten-Sicht):**
  `record_gold_observation()` leitet aus EINER konkreten (bereits validen,
  weil ueber `record_silver_observation()` erzeugten) Silver-Zeile genau
  einen Gold-Datensatz ab (`{ event_id, angereicherter_wert,
  qualitaetsindikator, herkunft: silver_version }`, Spec-Vertrag
  "Gold-Datensatz"). Die Anreicherung besteht aus zwei Teilen:
  - `angereicherter_wert` wird unveraendert aus
    `MarketDataSilver.normalisierter_wert` uebernommen (dort bereits
    normalisiert + Corporate-Actions-adjustiert, AC3/AC6).
  - `qualitaetsindikator` wird aus `MarketDataBronze.quality_indicator`
    propagiert (Socket-Qualitaetsmetadatum, in Silver bisher nicht
    exponiert) — Gold kombiniert damit Wert (Silver) + Qualitaets-Kontext
    (Bronze) zu einer konsumentenfertigen Sicht. Score-/Signal-Aggregation
    (z-Scores, Kategorie-Scores) ist laut Spec-Nicht-Ziel Sache der Analyse,
    NICHT dieser Schicht — dieses Modul erfindet daher keine eigene
    Bewertungslogik.

  **Bronze bleibt unangetastet (AC4-Kern-Invariante):** dieses Modul besitzt
  keine Schreibfunktion auf `market_data_bronze`/`market_data_silver` — es
  liest beide nur, um die Gold-Zeile abzuleiten.

  **"Ungueltige Datenpunkte erscheinen nicht in Gold-Ergebnissen" (AC4,
  AC8-Anschluss):** strukturell garantiert, nicht erneut geprueft — ein
  Gold-Datensatz kann nur aus einer tatsaechlich PERSISTIERTEN Silver-Zeile
  abgeleitet werden, und `app.db.silver.record_silver_observation()` lehnt
  ungueltige Bronze-Kandidaten bereits ab (`UngueltigerBronzeKandidatError`,
  AC7/AC8-Gate) — es existiert schlicht keine Silver-Zeile fuer einen
  ungueltigen Kandidaten, aus der Gold ableiten koennte.

  **Reproduzierbarkeit (AC4-NFR):** derselbe Silber-Zeile-Aufruf liefert
  (idempotent) denselben Gold-Datensatz zurueck — ein bereits abgeleiteter
  Datensatz fuer dieselbe Silver-Version wird nicht dupliziert, sondern
  unveraendert zurueckgegeben. `rebuild_gold_series_for_symbol()` leitet die
  komplette Gold-Reihe fuer `(data_source_id, symbol)` jederzeit neu aus der
  aktuellen Silver-/Bronze-Historie ab (analog
  `app.db.silver.rebuild_silver_series_for_symbol`) — Bronze und Silver
  bleiben dabei unveraendert.

  **Nebenlaeufigkeits-Haertung:** `record_gold_observation()` erwirkt VOR der
  Lese-Pruefung eine Postgres-Advisory-Xact-Lock je Silver-Version
  (`_erwirke_gold_dedupe_lock`, analog `app.db.bronze`/`app.db.silver`) und
  faengt einen trotzdem durchgeschluepften `IntegrityError` aus dem
  physischen `uq_market_data_gold_silver_version`-Unique-Index (Migration
  `0da3d5a72ba2`) ab, statt zwei Duplikat-Zeilen fuer dieselbe Silver-Version
  entstehen zu lassen. Anders als Bronze/Silver verwendet der Lock-Schluessel
  hier bewusst die **Zwei-Key-Form** von `pg_advisory_xact_lock` mit einem
  Domaenen-Praefix (`hashtext('gold')`, `hashtext(<schluessel>)`) — eine
  DBA-Suggestion aus dem Coder-Handoff der Vorgaenger-Story (S-024), um den
  32-Bit-Advisory-Lock-Namespace explizit von Bronze/Silver zu trennen statt
  ihn ueber alle drei Schichten hinweg zu teilen (Performance-/
  Starvation-Risiko bei zufaelligen Hash-Kollisionen zwischen Schichten,
  siehe `.claude/lessons/coder.md`).

Cross-Data-Source-Sicherheit (Iteration-2-Lehre aus S-024 vorab angewandt):
`MarketDataGold.data_source_id` ist denormalisiert aus der Silver-Zeile
uebernommen; `rebuild_gold_series_for_symbol()` filtert seine DELETE-Klausel
zusaetzlich nach `data_source_id` — `(symbol, source_event_id)` allein ist
laut BR-122/data-model.md KEINE eindeutige Ereignis-Identitaet.

Bronze-/Silver-Kompatibilitaet: `market_data_gold.instrument_id` (analog
Silver) ist bewusst nicht umgesetzt — die `instrument`-Tabelle existiert in
dieser Codebasis noch nicht (siehe data-model.md-Praezisierung + Coder-
Handoff S-024). `symbol` (aus der Silver-Zeile uebernommen) uebernimmt
stattdessen die fachliche Rolle.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import MarketDataBronze, MarketDataGold, MarketDataSilver


class SilberBronzeMismatchError(Exception):
    """AC4: `bronze_zeile` und `silber_zeile` gehoeren nicht zusammen (die
    Silber-Zeile wurde nicht aus GENAU dieser Bronze-Zeile abgeleitet) —
    verhindert eine Gold-Zeile mit falscher `herkunft`/falschem
    `qualitaetsindikator`."""

    def __init__(self, *, source_event_id: str) -> None:
        self.source_event_id = source_event_id
        super().__init__(
            f"Silber-Zeile '{source_event_id}' referenziert eine andere "
            "Bronze-Version als die uebergebene bronze_zeile."
        )


def _erwirke_gold_dedupe_lock(
    session: Session, *, silver_id: uuid.UUID, silver_observed_at: datetime
) -> None:
    """Serialisiert konkurrierende `record_gold_observation()`-Aufrufe fuer
    dieselbe Silver-Version (Nebenlaeufigkeits-Haertung, analog
    `app.db.bronze`/`app.db.silver`).

    Nutzt bewusst die **Zwei-Key-Form** von `pg_advisory_xact_lock`
    (`hashtext('gold')`, `hashtext(<schluessel>)`) statt der Single-Key-Form
    — DBA-Suggestion aus `.claude/lessons/coder.md` (S-024-Handoff), um den
    32-Bit-Advisory-Lock-Namespace explizit von Bronze/Silver zu trennen.

    Nur unter PostgreSQL wirksam; unter SQLite (Test-Backend) ist dies ein
    No-Op (kein `pg_advisory_xact_lock` verfuegbar).
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    lock_schluessel = f"{silver_id}:{silver_observed_at.isoformat()}"
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('gold'), hashtext(:schluessel))"),
        {"schluessel": lock_schluessel},
    )


def record_gold_observation(
    session: Session,
    *,
    bronze_zeile: MarketDataBronze,
    silber_zeile: MarketDataSilver,
) -> MarketDataGold:
    """AC4: leitet aus einer konkreten Silver-Zeile (+ der Bronze-Zeile, aus
    der diese Silver-Zeile abgeleitet wurde) genau einen Gold-Datensatz ab
    und persistiert ihn.

    Weist eine Silber-/Bronze-Kombination zurueck, die nicht zusammengehoert
    (`SilberBronzeMismatchError`) — verhindert eine Gold-Zeile mit falscher
    `herkunft` oder falschem `qualitaetsindikator`. Ist fuer dieselbe
    Silver-Version bereits ein Gold-Datensatz vorhanden, wird dieser
    unveraendert zurueckgegeben (idempotent, keine Duplikat-Zeile —
    Reproduzierbarkeit).
    """
    if (
        silber_zeile.bronze_id != bronze_zeile.id
        or silber_zeile.bronze_ingested_at != bronze_zeile.ingested_at
    ):
        raise SilberBronzeMismatchError(source_event_id=silber_zeile.source_event_id)

    _erwirke_gold_dedupe_lock(
        session, silver_id=silber_zeile.id, silver_observed_at=silber_zeile.observed_at
    )

    def _lade_bestehende_zeile() -> MarketDataGold | None:
        return session.execute(
            select(MarketDataGold).where(
                MarketDataGold.silver_id == silber_zeile.id,
                MarketDataGold.silver_observed_at == silber_zeile.observed_at,
            )
        ).scalar_one_or_none()

    bestehende = _lade_bestehende_zeile()
    if bestehende is not None:
        return bestehende

    zeile = MarketDataGold(
        silver_id=silber_zeile.id,
        silver_observed_at=silber_zeile.observed_at,
        data_source_id=silber_zeile.data_source_id,
        source_event_id=silber_zeile.source_event_id,
        symbol=silber_zeile.symbol,
        angereicherter_wert=silber_zeile.normalisierter_wert,
        qualitaetsindikator=bronze_zeile.quality_indicator,
        observed_at=silber_zeile.observed_at,
    )
    try:
        with session.begin_nested():
            session.add(zeile)
            session.flush()
    except IntegrityError:
        # `uq_market_data_gold_silver_version` (zweite Sicherung neben dem
        # Advisory-Lock) hat den Insert als Duplikat abgelehnt — das
        # ROLLBACK der SAVEPOINT entfernt `zeile` automatisch aus der
        # Session (kanonisches SQLAlchemy-Muster, analog
        # `app.db.bronze`/`app.db.silver`).
        massgebliche_zeile = _lade_bestehende_zeile()
        if massgebliche_zeile is None:  # pragma: no cover - sollte unerreichbar sein
            raise
        return massgebliche_zeile
    return zeile


def rebuild_gold_series_for_symbol(
    session: Session,
    *,
    data_source_id: uuid.UUID,
    symbol: str,
) -> list[MarketDataGold]:
    """AC4-NFR (jederzeit aus Bronze/Silver rekonstruierbar): leitet die
    komplette Gold-Reihe fuer `(data_source_id, symbol)` NEU aus der
    aktuellen Silver-Historie (+ der jeweils zugehoerigen Bronze-Zeile fuer
    `qualitaetsindikator`) ab.

    Bestehende Gold-Zeilen dieser Kombination werden zuerst entfernt
    (vollstaendige Neuableitung statt partiellem Update, analog
    `app.db.silver.rebuild_silver_series_for_symbol`) — Bronze und Silver
    bleiben dabei in jedem Fall unveraendert. Die DELETE-Klausel filtert
    zusaetzlich nach `data_source_id` (Cross-Data-Source-Sicherheit, siehe
    Modul-Docstring).
    """
    silber_reihe = (
        session.execute(
            select(MarketDataSilver).where(
                MarketDataSilver.data_source_id == data_source_id,
                MarketDataSilver.symbol == symbol,
            )
        )
        .scalars()
        .all()
    )

    if silber_reihe:
        session.execute(
            delete(MarketDataGold).where(
                MarketDataGold.data_source_id == data_source_id,
                MarketDataGold.symbol == symbol,
            )
        )

    neue_zeilen: list[MarketDataGold] = []
    for silber_zeile in silber_reihe:
        bronze_zeile = session.execute(
            select(MarketDataBronze).where(
                MarketDataBronze.id == silber_zeile.bronze_id,
                MarketDataBronze.ingested_at == silber_zeile.bronze_ingested_at,
            )
        ).scalar_one()
        zeile = MarketDataGold(
            silver_id=silber_zeile.id,
            silver_observed_at=silber_zeile.observed_at,
            data_source_id=data_source_id,
            source_event_id=silber_zeile.source_event_id,
            symbol=symbol,
            angereicherter_wert=silber_zeile.normalisierter_wert,
            qualitaetsindikator=bronze_zeile.quality_indicator,
            observed_at=silber_zeile.observed_at,
        )
        session.add(zeile)
        neue_zeilen.append(zeile)

    session.flush()
    return neue_zeilen


__all__ = [
    "SilberBronzeMismatchError",
    "record_gold_observation",
    "rebuild_gold_series_for_symbol",
]
