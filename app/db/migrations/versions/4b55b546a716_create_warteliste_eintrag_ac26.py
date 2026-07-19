"""create warteliste_eintrag (AC26/AC27/AC28)

Covers (frontend-cockpit): AC26, AC27, AC28

Quelle: docs/data-model.md §4 `warteliste_eintrag` (Cockpit-Read-Modell),
§8 Indizes, §10 BR-140, §11 Migrations-Reihenfolge Punkt 6; Spec
`docs/specs/frontend-cockpit.md` AC26/AC27/AC28, Story S-079.

Reines Cockpit-Read-Modell, komplett unabhängig von
`app.domain.risikomanagement` (Boundary AC2) — die vom Risikomanagement-
Gate gelieferte Warteliste-Markierung (`GateEntscheid.warteliste: bool`,
AC7/S-056) ist bewusst NICHT persistiert (Spec "Offene Punkte"); diese
Tabelle hat KEINEN Domänen-Schreibpfad, nur `app.demo.warteliste`
(Fixture-Insert, AC28) füllt sie. Anders als `risk_check_log` (FK auf
`position.id`) betrifft sie gerade Kandidaten, die NIE zu einer Position
werden — daher nur FK auf `instrument`/`asset_class`.

Revision ID: 4b55b546a716
Revises: 0470bd97aba3
Create Date: 2026-07-19 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "4b55b546a716"
down_revision: Union[str, Sequence[str], None] = "0470bd97aba3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BLOCKADE_GRUND_VALUES = ("klumpenrisiko", "korrelation", "drawdown", "kelly_cap")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "warteliste_eintrag",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "instrument_id", PGUUID(as_uuid=True), sa.ForeignKey("instrument.id"), nullable=False
        ),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            nullable=False,
        ),
        sa.Column("geplante_groesse", sa.Numeric(20, 8), nullable=False),
        sa.Column("blockade_grund", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column(
            "blockiert_am",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"blockade_grund IN ({', '.join(repr(v) for v in _BLOCKADE_GRUND_VALUES)})",
            name="ck_warteliste_eintrag_blockade_grund",
        ),
        sa.CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_warteliste_eintrag_mode"),
        sa.CheckConstraint(
            "geplante_groesse > 0", name="ck_warteliste_eintrag_geplante_groesse_positiv"
        ),
    )
    op.create_index("ix_warteliste_eintrag_mode", "warteliste_eintrag", ["mode"])
    op.create_index("ix_warteliste_eintrag_instrument_id", "warteliste_eintrag", ["instrument_id"])
    op.create_index(
        "ix_warteliste_eintrag_asset_class_id", "warteliste_eintrag", ["asset_class_id"]
    )
    op.create_index("ix_warteliste_eintrag_blockiert_am", "warteliste_eintrag", ["blockiert_am"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_warteliste_eintrag_blockiert_am", table_name="warteliste_eintrag")
    op.drop_index("ix_warteliste_eintrag_asset_class_id", table_name="warteliste_eintrag")
    op.drop_index("ix_warteliste_eintrag_instrument_id", table_name="warteliste_eintrag")
    op.drop_index("ix_warteliste_eintrag_mode", table_name="warteliste_eintrag")
    op.drop_table("warteliste_eintrag")
