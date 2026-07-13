"""add FX-Attribution columns to position (S-053, AC6)

Covers (depot): AC6

Quelle: docs/data-model.md §4 `position` (präzisiert in S-053 um
`einstand_fx_rate`/`fx_kapital_gv`/`fx_waehrungs_gv`, C-017); Spec
`docs/specs/depot.md` (Story S-053, "Verträge" — Position-Vertrag
`fx_kapital_gv, fx_waehrungs_gv`); BR-129 (FX-Attribution bei
`currency != CHF`).

`einstand_fx_rate` (Ø-Einstands-FX-Kurs, analog zu `einstand_preis`) wird
von `app.adapters.repositories.position_repository
.SqlAlchemyPositionRepository.lege_position_an`/`aktualisiere_kauf`
fortgeschrieben (S-053). `fx_kapital_gv`/`fx_waehrungs_gv` (unrealisierte
FX-Attribution) sind — analog zu `unrealisierter_gv` (S-016, S-015-
Migration `36e7c473f4aa`) — reservierte, nullable Spalten OHNE
Schreibpfad: das Nachführen anhand des Live-Kurses ist eine eigene, noch
nicht gebaute Bewertungs-Schleife (siehe `app.domain.portfolio
.fx_attribution.berechne_fx_split_unrealisiert`-Docstring), kein
Fill-getriebener Schreibpfad dieser Story. Alle drei Spalten sind NULLable
(nur bei Fremdwährungspositionen befüllt, sonst `None`, → BR-129).

Revision ID: f065be116c72
Revises: a1c4e7f2b930
Create Date: 2026-07-13 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f065be116c72"
down_revision: Union[str, Sequence[str], None] = "a1c4e7f2b930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("position", sa.Column("einstand_fx_rate", sa.Numeric(20, 8), nullable=True))
    op.add_column("position", sa.Column("fx_kapital_gv", sa.Numeric(20, 8), nullable=True))
    op.add_column("position", sa.Column("fx_waehrungs_gv", sa.Numeric(20, 8), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("position", "fx_waehrungs_gv")
    op.drop_column("position", "fx_kapital_gv")
    op.drop_column("position", "einstand_fx_rate")
