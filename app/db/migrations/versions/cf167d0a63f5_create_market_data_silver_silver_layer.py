"""create market_data_silver silver layer

Covers (datenqualitaet): AC3, AC6

Quelle: docs/data-model.md §2 `market_data_silver` (S-024-Präzisierung — der
ursprünglich notierte Signal-Bündel-Zuschnitt deckte den Silver-Datensatz-
Vertrag aus `docs/specs/datenqualitaet.md` nicht ab und wurde hier auf den
tatsächlichen Vertrag präzisiert), §8 Indizes, §9 Partitionierung.

**Physisches Schema:** `id`, `bronze_id` + `bronze_ingested_at` (zusammen die
zusammengesetzte FK auf `market_data_bronze(id, ingested_at)` — deckt
Vertragsfeld `abgeleitet_aus: bronze_version`), `data_source_id` (FK →
`data_source.id`, denormalisiert aus der Bronze-Zeile — Ereignis-Identität
laut BR-122/data-model.md ist nur `(data_source_id, source_event_id)`
eindeutig; ohne diese Spalte könnte ein Rebuild für Quelle A silent
Silver-Zeilen von Quelle B löschen, Iteration-2-Reviewer-Befund),
`source_event_id` (= Vertragsfeld `event_id`), `symbol` (aus der Bronze-Zeile
übernommen, für die Corporate-Actions-Zuordnung je Titel — Ersatz für das in
dieser Codebasis noch nicht existierende `instrument_id`, siehe
data-model.md-Präzisierung), `normalisierter_wert`, `einheit`,
`adjustierungs_info` (JSONB, nullable), `observed_at` (Partitionsschlüssel,
aus der Bronze-Zeile übernommen). PK `(id, observed_at)`.

**`uq_market_data_silver_bronze_version` (Iteration 2):** `UNIQUE (bronze_id,
bronze_ingested_at, observed_at)` — anders als bei `market_data_bronze`
(BR-122, physischer Unique-Index dort strukturell unmöglich) ist hier ein
echter Unique-Index möglich, weil `observed_at` (Partitionsschlüssel) für
dieselbe Bronze-Version deterministisch identisch ist (aus der referenzierten
Bronze-Zeile übernommen). Schliesst zusammen mit dem Advisory-Lock in
`app/db/silver.py::record_silver_observation()` die Nebenläufigkeits-Lücke
(zwei parallele Aufrufe für dieselbe Bronze-Version legten in Iteration 1
zwei Duplikat-Zeilen an, empirisch gegen Postgres 17 gemessen).

**Partitionierung (§9):** deklarativ `PARTITION BY RANGE (observed_at)`,
analog zur Bronze-Migration (`cfdd83ba9a2c`) mit einer `DEFAULT`-Partition
statt automatisierter Monats-Vorausplanung (kein AC dieser Story).

**Reproduzierbarkeit (AC3-NFR) statt Immutabilität:** anders als
`market_data_bronze` (BR-121, append-only) ist diese Tabelle NICHT
append-only — `app/db/silver.py::rebuild_silver_series_for_symbol` löscht
und leitet die betroffenen Zeilen bei einer rückwirkend gemeldeten Corporate
Action neu ab (AC6-Edge-Case). Es gibt daher bewusst KEINEN
BEFORE-UPDATE/DELETE-Trigger (Unterschied zu Bronze).

**FK auf partitionierte Bronze-Tabelle:** PostgreSQL erlaubt Foreign Keys auf
partitionierte Tabellen, sofern die referenzierten Spalten deren vollen
Unique-/Primary-Key abdecken (hier: `(id, ingested_at)` — erfüllt). Die FK
wird hier auf der (ebenfalls partitionierten) `market_data_silver`-Tabelle
je Partition durchgesetzt.

Revision ID: cf167d0a63f5
Revises: cfdd83ba9a2c
Create Date: 2026-07-12 20:30:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf167d0a63f5"
down_revision: Union[str, Sequence[str], None] = "cfdd83ba9a2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # PARTITION BY erfordert rohes DDL (alembic/SQLAlchemy `op.create_table`
    # kennt keine Partitionierungs-Klausel, alembic/A08) — analog zur
    # Bronze-Migration (cfdd83ba9a2c).
    op.execute(
        """
        CREATE TABLE market_data_silver (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            bronze_id UUID NOT NULL,
            bronze_ingested_at TIMESTAMPTZ NOT NULL,
            data_source_id UUID NOT NULL REFERENCES data_source (id),
            source_event_id TEXT NOT NULL,
            symbol TEXT,
            normalisierter_wert NUMERIC(20, 8) NOT NULL,
            einheit TEXT NOT NULL,
            adjustierungs_info JSONB,
            observed_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id, observed_at),
            FOREIGN KEY (bronze_id, bronze_ingested_at)
                REFERENCES market_data_bronze (id, ingested_at),
            CONSTRAINT uq_market_data_silver_bronze_version
                UNIQUE (bronze_id, bronze_ingested_at, observed_at)
        ) PARTITION BY RANGE (observed_at);
        """
    )

    # Default-Partition faengt jeden observed_at-Wert auf (§9 — echte
    # Monats-Partitionen sind eine spaetere Ops-/Scheduler-Aufgabe, analog
    # Bronze).
    op.execute("CREATE TABLE market_data_silver_default PARTITION OF market_data_silver DEFAULT;")

    # data-model.md §8: Corporate-Actions-Adjustierung je Titel/Zeit,
    # Event-Lookup, Bronze-Rueckverfolgung.
    op.create_index(
        "ix_market_data_silver_symbol_observed_at",
        "market_data_silver",
        ["symbol", "observed_at"],
    )
    op.create_index(
        "ix_market_data_silver_source_event_id",
        "market_data_silver",
        ["source_event_id"],
    )
    op.create_index(
        "ix_market_data_silver_bronze_id_ingested_at",
        "market_data_silver",
        ["bronze_id", "bronze_ingested_at"],
    )
    # Iteration 2 (Reviewer-Befund): Rebuild-/Delete-Scoping muss nach der
    # vollständigen Ereignis-Identität (data_source_id + symbol) filtern
    # koennen, nicht nur nach symbol (siehe app/db/silver.py).
    op.create_index(
        "ix_market_data_silver_data_source_id_symbol",
        "market_data_silver",
        ["data_source_id", "symbol"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_market_data_silver_data_source_id_symbol", table_name="market_data_silver")
    op.drop_index("ix_market_data_silver_bronze_id_ingested_at", table_name="market_data_silver")
    op.drop_index("ix_market_data_silver_source_event_id", table_name="market_data_silver")
    op.drop_index("ix_market_data_silver_symbol_observed_at", table_name="market_data_silver")
    op.drop_table("market_data_silver_default")
    op.drop_table("market_data_silver")
