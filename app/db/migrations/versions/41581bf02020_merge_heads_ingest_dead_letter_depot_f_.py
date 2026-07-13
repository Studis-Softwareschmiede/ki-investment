"""merge heads: ingest_dead_letter + depot (F-003/F-011 Konsolidierung)

Revision ID: 41581bf02020
Revises: 9c1e6a2f3b7d, f065be116c72
Create Date: 2026-07-13 08:02:24.886235

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "41581bf02020"
down_revision: Union[str, Sequence[str], None] = ("9c1e6a2f3b7d", "f065be116c72")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
