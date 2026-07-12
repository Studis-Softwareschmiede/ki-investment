"""create asset_class table and seed 11 classes

Covers (anlageklassen-config): AC1, AC2, AC3, AC12
Quelle: docs/data-model.md §1 `asset_class` (BR-100), Verträge-Tabelle in
docs/specs/anlageklassen-config.md.

Revision ID: b2bd709be080
Revises:
Create Date: 2026-07-12 13:10:31.061140

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "b2bd709be080"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Verbindliche Nummerierung (AC1) + MVP-Toggle-Default {1, 2, 7} (AC2) +
# Empfehlungsstufe (AC3, Krypto bewusst Stufe3 trotz aktiv-Default — siehe
# Spec-Hinweis in der Verträge-Tabelle) + retail_driven (data-model.md BR-123,
# NOT NULL — nur 1 Aktien und 7 Krypto sind retail-getrieben).
ASSET_CLASS_SEED = [
    {"id": 1, "name": "Aktien", "prio_stufe": "MVP", "aktiv": True, "retail_driven": True},
    {"id": 2, "name": "ETFs", "prio_stufe": "MVP", "aktiv": True, "retail_driven": False},
    {
        "id": 3,
        "name": "Cash/Geldmarkt",
        "prio_stufe": "MVP",
        "aktiv": False,
        "retail_driven": False,
    },
    {
        "id": 4,
        "name": "Obligationen",
        "prio_stufe": "Stufe2",
        "aktiv": False,
        "retail_driven": False,
    },
    {
        "id": 5,
        "name": "Aktive Fonds",
        "prio_stufe": "Stufe2",
        "aktiv": False,
        "retail_driven": False,
    },
    {
        "id": 6,
        "name": "Immobilien",
        "prio_stufe": "Stufe2",
        "aktiv": False,
        "retail_driven": False,
    },
    {
        "id": 7,
        "name": "Kryptowährungen",
        "prio_stufe": "Stufe3",
        "aktiv": True,
        "retail_driven": True,
    },
    {
        "id": 8,
        "name": "Rohstoffe",
        "prio_stufe": "Stufe3",
        "aktiv": False,
        "retail_driven": False,
    },
    {
        "id": 9,
        "name": "Infrastrukturfonds",
        "prio_stufe": "Stufe3",
        "aktiv": False,
        "retail_driven": False,
    },
    {"id": 10, "name": "FX", "prio_stufe": "Stufe3", "aktiv": False, "retail_driven": False},
    {
        "id": 11,
        "name": "Derivate",
        "prio_stufe": "Stufe3",
        "aktiv": False,
        "retail_driven": False,
    },
]


def upgrade() -> None:
    """Upgrade schema."""
    asset_class = op.create_table(
        "asset_class",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("prio_stufe", sa.String(), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False),
        sa.Column("retail_driven", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("id BETWEEN 1 AND 11", name="ck_asset_class_id_range"),
        sa.CheckConstraint(
            "prio_stufe IN ('MVP', 'Stufe2', 'Stufe3')", name="ck_asset_class_prio_stufe"
        ),
    )
    # Idempotenter Seed (data-model.md §11 Punkt 10: "ON CONFLICT DO NOTHING") —
    # ein wiederholtes `alembic upgrade head` gegen eine bereits geseedete DB
    # darf keine IntegrityError werfen und die Zeilenzahl nicht verändern.
    op.execute(
        pg_insert(asset_class).values(ASSET_CLASS_SEED).on_conflict_do_nothing(
            index_elements=["id"]
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("asset_class")
