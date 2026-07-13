"""create trading_platform and platform_asset_class tables

Covers (ausfuehrung-paper): AC10, AC11

Quelle: docs/data-model.md §1 `trading_platform` + `platform_asset_class`
(C-016, BR-126), Verträge-Abschnitt "Handelsplattform-Stammdaten
(Referenzdaten)" in docs/specs/ausfuehrung-paper.md.

AC10 (Referenzdaten `{ gebuehrenmodell, mindestgebuehr, typischer_spread }`
je Plattform/Anlageklasse + Plattform-Zuordnung als Konfiguration): beide
Tabellen 1:1 aus data-model.md §1, inkl. dem `bevorzugt`-Flag auf
`platform_asset_class`, das die Zuordnungs-Konfiguration traegt (siehe
`app.db.trading_platform.waehle_plattform_fuer_anlageklasse`).

AC11 (erwartete Kosten Courtage + Spread + geschaetzte Slippage an
Sizing-Module): `courtage_pct`/`typ_spread_pct` sind die Referenzdaten-Basis;
die geschaetzte Slippage ist KEIN Feld dieser Tabellen (kein Konzept-/
Spec-Beleg fuer einen konkreten Wert je Plattform/Klasse), sondern ein
separat konfigurierbarer, provisorischer Prozentsatz
(`Settings.erwartete_slippage_pct_default`, siehe app/config.py +
docs/specs/ausfuehrung-paper.md-Praezisierung).

Bewusst KEIN Seed: weder Konzept noch Spec nennen konkrete
Courtage-/Spread-/Mindestgebuehr-Zahlen je Anlageklasse fuer Interactive
Brokers — sie hier zu erfinden waere unbelegte Fabrikation. Die
Referenzdaten sind Konfiguration und werden ausserhalb dieser Story mit
tatsaechlich bekannten Konditionen befuellt.

Revision ID: f908ab5874fe
Revises: 0da3d5a72ba2
Create Date: 2026-07-13 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "f908ab5874fe"
down_revision: Union[str, Sequence[str], None] = "41581bf02020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trading_platform",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("gebuehrenmodell", sa.String(), nullable=True),
        sa.Column(
            "mindestgebuehr_chf", sa.Numeric(10, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("api_handelbar", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("vault_ref", sa.String(), nullable=True),
        sa.Column("paper_supported", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "platform_asset_class",
        sa.Column(
            "platform_id",
            UUID(as_uuid=True),
            sa.ForeignKey("trading_platform.id"),
            primary_key=True,
        ),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            primary_key=True,
        ),
        sa.Column("courtage_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("typ_spread_pct", sa.Numeric(6, 4), nullable=True),
        sa.Column("bevorzugt", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # data-model.md §8: (asset_class_id)-Index fuer "Plattform-Kosten je
    # Klasse" — der Composite-PK (platform_id, asset_class_id) deckt einen
    # reinen asset_class_id-Filter nicht ab (nicht fuehrender Spaltenteil).
    op.create_index(
        "ix_platform_asset_class_asset_class_id",
        "platform_asset_class",
        ["asset_class_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_platform_asset_class_asset_class_id", table_name="platform_asset_class")
    op.drop_table("platform_asset_class")
    op.drop_table("trading_platform")
