"""instrument korrelations cluster (AC9, S-045)

Covers (risikomanagement): AC9

Quelle: docs/data-model.md §2 `instrument` (C-007, C-017); Spec
`docs/specs/risikomanagement.md` (Story S-045) AC9, BR-138.

Additive Spalte `instrument.korrelations_cluster` (NULLable, kein Seed) —
analog zu `gics_sector`: ein zweiter, unabhängiger Gruppierungs-Schlüssel
für die Korrelations-/Cluster-Konzentrationsprüfung des Risikomanagement-
Gates (`app.domain.risikomanagement.gate.pruefe_kauf_gate`). Die
eigentliche Korrelations-Messung (Datenquelle/Zeitfenster, Stress- vs.
Normalphase) bleibt laut Spec "Offene Punkte" unverändert offen — diese
Migration liefert nur die strukturelle Andockstelle.

Revision ID: b6c1f4a08e27
Revises: d19a6f5c7b3e
Create Date: 2026-07-18 11:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6c1f4a08e27"
down_revision: Union[str, Sequence[str], None] = "d19a6f5c7b3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "instrument",
        sa.Column("korrelations_cluster", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("instrument", "korrelations_cluster")
