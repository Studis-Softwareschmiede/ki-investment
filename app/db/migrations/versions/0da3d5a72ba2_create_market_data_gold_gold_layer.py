"""create market data gold gold layer

Covers (datenqualitaet): AC4

Quelle: docs/data-model.md §2 `market_data_gold` (S-051), §8 Indizes, §9
Partitionierung.

**Physisches Schema:** `id`, `silver_id` + `silver_observed_at` (zusammen die
zusammengesetzte FK auf `market_data_silver(id, observed_at)` — deckt
Vertragsfeld `herkunft: silver_version`), `data_source_id` (FK →
`data_source.id`, denormalisiert aus der Silver-Zeile — analog zur
Silver-Migration `cf167d0a63f5`/Iteration-2-Reviewer-Befund: nur
`(data_source_id, source_event_id)` ist eine eindeutige Ereignis-Identität;
ohne diese Spalte könnte ein Rebuild für Quelle A silent Gold-Zeilen einer
anderen Quelle B löschen), `source_event_id` (= Vertragsfeld `event_id`),
`symbol` (aus der Silver-Zeile übernommen), `angereicherter_wert` (=
Vertragsfeld `angereicherter_wert`, aus `market_data_silver.normalisierter_
wert` übernommen), `qualitaetsindikator` (= Vertragsfeld, aus
`market_data_bronze.quality_indicator` propagiert — siehe
`app/db/gold.py`-Docstring für die Begründung dieser Ableitung),
`observed_at` (Partitionsschlüssel, aus der Silver-Zeile übernommen),
`computed_at` (Audit-Zeitpunkt der Gold-Ableitung, analog
`instrument_signal_bundle.computed_at`). PK `(id, observed_at)`.

**`uq_market_data_gold_silver_version`:** `UNIQUE (silver_id,
silver_observed_at, observed_at)` — genau ein Gold-Datensatz je Silver-Zeile
(1:1-Ableitung, Idempotenz-Garantie, analog
`uq_market_data_silver_bronze_version`). `observed_at` ist redundant zu
`silver_observed_at` (beide stets identisch, da 1:1 aus der Silver-Zeile
uebernommen) — PostgreSQL verlangt trotzdem, dass jeder Unique-Index auf einer
`PARTITION BY RANGE`-Tabelle den Partitionsschluessel (`observed_at`) explizit
enthaelt (empirisch gegen Postgres 17 verifiziert: `CREATE TABLE` schlaegt
sonst mit `FeatureNotSupported: unique constraint on partitioned table must
include all partitioning columns` fehl — Coder-Self-Test, siehe Handoff).

**Partitionierung (§9):** deklarativ `PARTITION BY RANGE (observed_at)`,
analog zu Bronze (`cfdd83ba9a2c`) und Silver (`cf167d0a63f5`) mit einer
`DEFAULT`-Partition statt automatisierter Monats-Vorausplanung (kein AC dieser
Story) — konsistente Fortführung des etablierten Zeitreihen-Partitionierungs-
Musters für die dritte Schicht.

**Reproduzierbarkeit (AC4-NFR) statt Immutabilität:** wie
`market_data_silver` ist diese Tabelle NICHT append-only —
`app/db/gold.py::rebuild_gold_series_for_symbol` löscht und leitet die
betroffenen Zeilen bei einer Neuableitung aus Silver/Bronze neu ab. Es gibt
daher bewusst KEINEN BEFORE-UPDATE/DELETE-Trigger (Unterschied zu Bronze,
analog Silver).

**FK auf partitionierte Silver-Tabelle:** PostgreSQL erlaubt Foreign Keys auf
partitionierte Tabellen, sofern die referenzierten Spalten deren vollen
Unique-/Primary-Key abdecken (hier: `(id, observed_at)` — erfüllt).

**`ON DELETE CASCADE` (Iteration 2, DBA-Befund, Critical):** die FK auf
`market_data_silver` trug urspruenglich KEINE `ON DELETE`-Klausel (Postgres-
Default `NO ACTION`) — `app/db/silver.py::rebuild_silver_series_for_symbol()`
loescht bei jeder Corporate-Actions-Neuableitung ALLE bestehenden
Silver-Zeilen fuer `(data_source_id, symbol)`; sobald mindestens eine dieser
Zeilen bereits eine abgeleitete Gold-Zeile hatte, schlug dieses `DELETE`
unter echtem Postgres mit einer Fremdschluesselverletzung fehl (in
SQLite-Tests unbemerkt, da `PRAGMA foreign_keys=ON` in den betroffenen
Test-Fixtures fehlte — siehe `.claude/lessons/coder.md`). **Entscheidung:**
`ON DELETE CASCADE` statt eines Vorab-Loeschens in
`rebuild_silver_series_for_symbol()` — Gold-Zeilen haben laut AC4 keine
eigenstaendige Existenz (reine Ableitung aus Silver/Bronze) und sind laut
AC4-NFR jederzeit ueber `app/db/gold.py::rebuild_gold_series_for_symbol()`
reproduzierbar; ein automatisches Mitloeschen bei einer Silver-Neuableitung
ist damit die zum bestehenden Silver-Design konsistente Wahl (Silver selbst
loescht/leitet bei Corporate Actions neu ab, ohne dass Bronze angefasst
wird — Gold folgt demselben Muster eine Ebene tiefer). Die Anschluss-Pflicht
"nach einer Silver-Neuableitung Gold per `rebuild_gold_series_for_symbol()`
neu aufbauen" liegt bei der (noch nicht gebauten) Orchestrierungsschicht,
analog zur bereits dokumentierten Bronze->Silver-Verdrahtung
(`app/db/validation.py`-Docstring).

Revision ID: 0da3d5a72ba2
Revises: cf167d0a63f5
Create Date: 2026-07-12 21:06:32.852355

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0da3d5a72ba2"
down_revision: Union[str, Sequence[str], None] = "cf167d0a63f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # PARTITION BY erfordert rohes DDL (alembic/SQLAlchemy `op.create_table`
    # kennt keine Partitionierungs-Klausel, alembic/A08) — analog zur
    # Bronze-/Silver-Migration.
    op.execute(
        """
        CREATE TABLE market_data_gold (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            silver_id UUID NOT NULL,
            silver_observed_at TIMESTAMPTZ NOT NULL,
            data_source_id UUID NOT NULL REFERENCES data_source (id),
            source_event_id TEXT NOT NULL,
            symbol TEXT,
            angereicherter_wert NUMERIC(20, 8) NOT NULL,
            qualitaetsindikator TEXT,
            observed_at TIMESTAMPTZ NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, observed_at),
            FOREIGN KEY (silver_id, silver_observed_at)
                REFERENCES market_data_silver (id, observed_at)
                ON DELETE CASCADE,
            CONSTRAINT uq_market_data_gold_silver_version
                UNIQUE (silver_id, silver_observed_at, observed_at)
        ) PARTITION BY RANGE (observed_at);
        """
    )

    # Default-Partition faengt jeden observed_at-Wert auf (§9 — echte
    # Monats-Partitionen sind eine spaetere Ops-/Scheduler-Aufgabe, analog
    # Bronze/Silver).
    op.execute("CREATE TABLE market_data_gold_default PARTITION OF market_data_gold DEFAULT;")

    # data-model.md §8: Konsumenten-Lookup je Titel/Zeit, Event-Lookup,
    # Silver-Rueckverfolgung, quellen-korrektes Rebuild-/Delete-Scoping
    # (analog Silver-Migration, Iteration-2-Lehre vorab angewandt).
    op.create_index(
        "ix_market_data_gold_symbol_observed_at",
        "market_data_gold",
        ["symbol", "observed_at"],
    )
    op.create_index(
        "ix_market_data_gold_source_event_id",
        "market_data_gold",
        ["source_event_id"],
    )
    op.create_index(
        "ix_market_data_gold_silver_id_observed_at",
        "market_data_gold",
        ["silver_id", "silver_observed_at"],
    )
    op.create_index(
        "ix_market_data_gold_data_source_id_symbol",
        "market_data_gold",
        ["data_source_id", "symbol"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_market_data_gold_data_source_id_symbol", table_name="market_data_gold")
    op.drop_index("ix_market_data_gold_silver_id_observed_at", table_name="market_data_gold")
    op.drop_index("ix_market_data_gold_source_event_id", table_name="market_data_gold")
    op.drop_index("ix_market_data_gold_symbol_observed_at", table_name="market_data_gold")
    op.drop_table("market_data_gold_default")
    op.drop_table("market_data_gold")
