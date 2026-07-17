"""merge heads S-043 S-038 S-059 (Welle 1)

Revision ID: aa1e7addeda8
Revises: 655b7f43eff4, c7e21f4a9d63, e4f7a1c9b2d3
Create Date: 2026-07-18 00:28:03.701622

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "aa1e7addeda8"
down_revision: Union[str, Sequence[str], None] = ("655b7f43eff4", "c7e21f4a9d63", "e4f7a1c9b2d3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
