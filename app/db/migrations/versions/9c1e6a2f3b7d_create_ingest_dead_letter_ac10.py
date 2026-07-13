"""create ingest_dead_letter (AC10 dead-letter-queue)

Covers (dateneingang): AC10

Quelle: docs/data-model.md §7 `ingest_dead_letter` (C-009), §8 Index
`(data_source_id, created_at)` (DLQ-Backlog-Monitoring), §9 Retention
(90 Tage nach Resolution — App-seitige Bereinigung, nicht Teil dieser
Migration); Spec `docs/specs/dateneingang.md` AC10.

AC10 ("nach erschöpften Versuchen wird das Arbeitselement in eine
Dead-Letter-Queue verschoben und protokolliert"): diese Tabelle ist die
dauerhafte Ablage, in die `app.scheduler.worker` nach erschöpften
Exponential-Backoff-Versuchen schreibt (`app.db.ingest_dead_letter.
record_dead_letter`). Retention (90 Tage) ist laut data-model.md §9 eine
App-/Batch-Aufgabe, kein DB-Constraint dieser Migration.

Revision ID: 9c1e6a2f3b7d
Revises: 8f183aee9753
Create Date: 2026-07-13 01:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "9c1e6a2f3b7d"
down_revision: Union[str, Sequence[str], None] = "8f183aee9753"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ingest_dead_letter",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "data_source_id",
            UUID(as_uuid=True),
            sa.ForeignKey("data_source.id"),
            nullable=False,
        ),
        sa.Column("source_event_id", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON().with_variant(JSONB, "postgresql"), nullable=True),
        sa.Column("fehler", sa.String(), nullable=False),
        sa.Column("retry_count", sa.SmallInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # data-model.md §8: (data_source_id, created_at)-Index fuer
    # DLQ-Backlog-Monitoring.
    op.create_index(
        "ix_ingest_dead_letter_data_source_id_created_at",
        "ingest_dead_letter",
        ["data_source_id", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_ingest_dead_letter_data_source_id_created_at", table_name="ingest_dead_letter"
    )
    op.drop_table("ingest_dead_letter")
