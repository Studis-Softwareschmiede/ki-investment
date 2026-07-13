"""create depot_fill_dedup (idempotency ledger for fill booking, ADR-011)

Covers (depot): AC2, AC3, AC5 (DBA-Zweit-Review, Critical-Befund)

Quelle: docs/data-model.md §4 `depot_fill_dedup`; Spec `docs/specs/depot.md`
(Story S-016, "Edge-Cases & Fehlerverhalten"); `docs/architecture.md` P8 +
ADR-011 (Fill→Depot-Fortschreibung idempotent, Client-Order-ID als
Dedup-Schlüssel).

Nachgezogen im DBA-Zweit-Review von S-016: `FillInput` trug bislang keine
Client-Order-/Fill-ID, die Schreibpfade (`lege_position_an`/
`aktualisiere_kauf`/`verbuche_verkauf_lot`) hatten keinen Dedup-Check — bei
At-least-once-Zustellung (Redis-Queue, P8) hätte ein doppelt zugestellter
Fill die Position doppelt fortgeschrieben (ADR-011-Verstoss).

`depot_fill_dedup` ist bewusst ein reiner Idempotenz-Marker (PK
`client_order_id`, kein weiterer fachlicher Inhalt) — **kein** Ersatz für
die volle append-only Transaktionshistorie (`transaction`, AC4/AC7 →
S-035); S-035 kann bei Bedarf einen eigenen UNIQUE-Constraint direkt auf
`transaction.client_order_id` einführen und diese Tabelle ablösen (Notiz
data-model.md §4).

Revision ID: 385adb3a764b
Revises: 36e7c473f4aa
Create Date: 2026-07-12 19:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "385adb3a764b"
down_revision: Union[str, Sequence[str], None] = "36e7c473f4aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "depot_fill_dedup",
        sa.Column("client_order_id", sa.String(), primary_key=True),
        sa.Column(
            "instrument_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("instrument.id"),
            nullable=False,
        ),
        sa.Column("richtung", sa.String(), nullable=False),
        sa.Column(
            "verbucht_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("richtung IN ('kauf', 'verkauf')", name="ck_depot_fill_dedup_richtung"),
    )
    op.create_index("ix_depot_fill_dedup_instrument_id", "depot_fill_dedup", ["instrument_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_depot_fill_dedup_instrument_id", table_name="depot_fill_dedup")
    op.drop_table("depot_fill_dedup")
