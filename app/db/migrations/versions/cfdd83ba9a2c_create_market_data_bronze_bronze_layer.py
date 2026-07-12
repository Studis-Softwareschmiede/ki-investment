"""create market_data_bronze bronze layer

Covers (datenqualitaet): AC1, AC2, AC9, AC10

Quelle: docs/data-model.md §2 `market_data_bronze` (BR-121 Immutabilität,
BR-122 Idempotenz), §8 Indizes, §9 Partitionierung; Verträge-Tabelle
"Bronze-Datensatz" in docs/specs/datenqualitaet.md.

**Physisches Schema:** 1:1 aus data-model.md §2 — `id`, `data_source_id`,
`source_event_id`, `asset_class_tag`, `symbol`, `payload` (JSONB, =
Vertrags-Feld `roh_wert`), `quality_indicator`, `observed_at` (=
`beobachtungs_zeitpunkt`), `ingested_at` (= `empfangs_zeitpunkt`,
Partitionsschlüssel). PK `(id, ingested_at)` — Postgres verlangt, dass der
Partitionsschlüssel Teil jedes PK/Unique-Index einer partitionierten Tabelle
ist (hier erfüllt).

**Partitionierung (§9):** deklarativ `PARTITION BY RANGE (ingested_at)`. Die
automatisierte monatliche Partitions-Vorausplanung (Scheduler-/Ops-Aufgabe,
kein AC dieser Story) ist NICHT Teil von S-022 — stattdessen legt diese
Migration eine `DEFAULT`-Partition an, die jeden `ingested_at`-Wert
strukturell auffängt, ohne dass Inserts an fehlenden Monatspartitionen
scheitern. Eine Folge-Story (Betrieb/Scheduler) kann echte Monatspartitionen
vor die Default-Partition schieben (`ALTER TABLE ... DETACH/ATTACH
PARTITION`), ohne dieses Migrations-Fundament zu ändern.

**BR-122-Präzisierung (Idempotenz + AC10-Versionierung, siehe auch
`app/db/models.py::MarketDataBronze`-Docstring):** ein einzelnes physisches
`UNIQUE (data_source_id, source_event_id)` würde AC10 (neue
Point-in-Time-Version bei Revision) unmöglich machen — UND wäre auf einer
RANGE-partitionierten Tabelle ohnehin nur zulässig, wenn der
Partitionsschlüssel (`ingested_at`) Teil des Index ist, was die
Duplikaterkennung selbst aushebelt (jede Zeile bekommt ein frisches
`ingested_at`). Statt eines Unique-Index entscheidet daher zweischichtig
(analog BR-101 / `category_weight`-Migration):
- **App-Layer** (`app/db/bronze.py::record_observation`, primär getestet):
  identischer Inhalt (`payload` + `observed_at`) zur zuletzt bekannten Version
  → idempotenter No-Op (AC9/E2); abweichender Inhalt → neue Zeile (AC10/A1).
- **DB-Layer** (BEFORE-INSERT-Trigger, zweite Sicherung gegen Inserts, die an
  `app/db/bronze.py` vorbeigehen): dieselbe Dedupe-/Versionierungs-Logik.
  Nur unter Postgres ausführbar — manuell gegen die lokale Compose-Postgres-
  Instanz verifiziert (Coder-Self-Test, siehe Handoff), nicht Teil von
  `uv run pytest` (SQLite-Tests decken die App-Layer-Logik ab, siehe
  `tests/db/test_market_data_bronze_migration.py`).

**Iteration-2-Fix (Reviewer-Befund, empirisch gegen Postgres 17 gemessen,
siehe `.claude/lessons/coder.md`):** ein `RETURN NULL`-Dedupe-Trigger ist (1)
ORM-inkompatibel (der nächste Attributzugriff auf das durch
`expire_on_commit` abgelaufene Objekt wirft eine unbehandelte
`ObjectDeletedError`, weil SQLAlchemy beim Refresh keine Zeile findet) und
(2) kein verlässlicher Nebenläufigkeits-Schutz (zwei parallele, noch nicht
committete Transaktionen sehen sich unter READ COMMITTED gegenseitig nicht —
beide Inserts liefen durch, zwei echte Duplikat-Zeilen entstanden). Der Fix
ist zweiteilig: (a) `app/db/bronze.py::record_observation()` erwirkt jetzt
VOR der Lese-Prüfung eine `pg_advisory_xact_lock`, die konkurrierende Aufrufe
für dieselbe Ereignis-Identität seriell statt gleichzeitig laufen lässt
(schliesst die Race-Lücke); (b) der Trigger wirft bei einem Duplikat KEIN
stilles `RETURN NULL` mehr, sondern eine abfangbare `RAISE EXCEPTION ...
USING ERRCODE = 'unique_violation'` — das mappt über psycopg auf
`sqlalchemy.exc.IntegrityError`, die `record_observation()` fängt, das
eigene (nie persistierte) ORM-Objekt verwirft und die tatsächlich
massgebliche Zeile frisch nachlädt.

**BR-121 (Immutabilität, AC1):** ein zweiter BEFORE-UPDATE/DELETE-Trigger
weist jeden Änderungsversuch mit `RAISE EXCEPTION` zurück (Wahl laut
data-model.md §11 Fussnote dem `coder` überlassen — hier Trigger statt
entzogener Grants, da kein dediziertes App-DB-Rollenkonzept existiert).

Revision ID: cfdd83ba9a2c
Revises: ea80c97626ee
Create Date: 2026-07-12 17:25:29.472727

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cfdd83ba9a2c"
down_revision: Union[str, Sequence[str], None] = "ea80c97626ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DEDUPE_FUNCTION_NAME = "market_data_bronze_dedupe_or_version"
_DEDUPE_TRIGGER_NAME = "trg_market_data_bronze_dedupe_or_version"
_IMMUTABLE_FUNCTION_NAME = "market_data_bronze_immutable"
_IMMUTABLE_TRIGGER_NAME = "trg_market_data_bronze_immutable"


def upgrade() -> None:
    """Upgrade schema."""
    # PARTITION BY erfordert rohes DDL (alembic/SQLAlchemy `op.create_table`
    # kennt keine Partitionierungs-Klausel, alembic/A08).
    op.execute(
        """
        CREATE TABLE market_data_bronze (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            data_source_id UUID NOT NULL REFERENCES data_source(id),
            source_event_id TEXT NOT NULL,
            asset_class_tag SMALLINT REFERENCES asset_class(id),
            symbol TEXT,
            payload JSONB NOT NULL,
            quality_indicator TEXT,
            observed_at TIMESTAMPTZ NOT NULL,
            ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, ingested_at)
        ) PARTITION BY RANGE (ingested_at);
        """
    )

    # Default-Partition faengt jeden ingested_at-Wert auf (§9 — echte
    # Monats-Partitionen sind eine spaetere Ops-/Scheduler-Aufgabe).
    op.execute("CREATE TABLE market_data_bronze_default PARTITION OF market_data_bronze DEFAULT;")

    # data-model.md §8: Replay/PIT je Klasse + Quelle, App-Layer-Lookup.
    op.create_index(
        "ix_market_data_bronze_source_ingested_at",
        "market_data_bronze",
        ["data_source_id", "ingested_at"],
    )
    op.create_index(
        "ix_market_data_bronze_asset_class_observed_at",
        "market_data_bronze",
        ["asset_class_tag", "observed_at"],
    )
    op.create_index(
        "ix_market_data_bronze_source_event_id",
        "market_data_bronze",
        ["data_source_id", "source_event_id"],
    )

    # BR-122 DB-Layer (zweite Sicherung neben app/db/bronze.py): identischer
    # Inhalt zur zuletzt bekannten Version derselben (data_source_id,
    # source_event_id) -> Insert abfangbar ablehnen (AC9); abweichender
    # Inhalt (Revision) -> Insert zulassen, keine Ueberschreibung (AC10).
    #
    # Iteration-2-Fix: KEIN stilles `RETURN NULL` mehr (ORM-inkompatibel,
    # siehe Docstring oben) -- stattdessen eine abfangbare Exception mit
    # SQLSTATE 'unique_violation', die record_observation() gezielt faengt.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_DEDUPE_FUNCTION_NAME}() RETURNS TRIGGER AS $$
        DECLARE
            letzte RECORD;
        BEGIN
            SELECT payload, observed_at INTO letzte
            FROM market_data_bronze
            WHERE data_source_id = NEW.data_source_id
              AND source_event_id = NEW.source_event_id
            ORDER BY ingested_at DESC
            LIMIT 1;

            IF FOUND AND letzte.payload = NEW.payload AND letzte.observed_at = NEW.observed_at THEN
                -- AC9/E2: dasselbe Ereignis bereits bekannt -> Insert
                -- abfangbar ablehnen statt stillschweigend zu verwerfen.
                RAISE EXCEPTION
                    'market_data_bronze_duplicate: Ereignis bereits bekannt (quelle=%, event=%)',
                    NEW.data_source_id,
                    NEW.source_event_id
                    USING ERRCODE = 'unique_violation';
            END IF;

            -- Keine Vorgaenger-Zeile ODER inhaltlich abweichend (AC10/A1:
            -- neue Point-in-Time-Version) -> Insert zulassen.
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_DEDUPE_TRIGGER_NAME}
        BEFORE INSERT ON market_data_bronze
        FOR EACH ROW EXECUTE FUNCTION {_DEDUPE_FUNCTION_NAME}();
        """
    )

    # BR-121 (AC1): append-only — jeder UPDATE/DELETE-Versuch scheitert.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {_IMMUTABLE_FUNCTION_NAME}() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'market_data_bronze ist append-only (BR-121) - UPDATE/DELETE nicht erlaubt.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {_IMMUTABLE_TRIGGER_NAME}
        BEFORE UPDATE OR DELETE ON market_data_bronze
        FOR EACH ROW EXECUTE FUNCTION {_IMMUTABLE_FUNCTION_NAME}();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"DROP TRIGGER IF EXISTS {_IMMUTABLE_TRIGGER_NAME} ON market_data_bronze")
    op.execute(f"DROP FUNCTION IF EXISTS {_IMMUTABLE_FUNCTION_NAME}()")
    op.execute(f"DROP TRIGGER IF EXISTS {_DEDUPE_TRIGGER_NAME} ON market_data_bronze")
    op.execute(f"DROP FUNCTION IF EXISTS {_DEDUPE_FUNCTION_NAME}()")
    op.drop_index("ix_market_data_bronze_source_event_id", table_name="market_data_bronze")
    op.drop_index("ix_market_data_bronze_asset_class_observed_at", table_name="market_data_bronze")
    op.drop_index("ix_market_data_bronze_source_ingested_at", table_name="market_data_bronze")
    op.drop_table("market_data_bronze_default")
    op.drop_table("market_data_bronze")
