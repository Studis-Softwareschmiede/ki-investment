"""create rule_hypothesis (AC1/AC2 Mindest-Evidenz-Protokoll & Marktlogik-Filter)

Covers (lernschleife): AC1, AC2

Quelle: docs/data-model.md §6 `rule_hypothesis` (C-012), §8 Index
`(asset_class_id)`, §10 BR-136; Spec `docs/specs/lernschleife.md` AC1/AC2,
Story S-058.

AC1 ("jede Hypothese trägt ein Mindest-Evidenz-Protokoll: mindestens
Anzahl Fälle, Zeitraum, Signalquelle/Anlageklasse") UND AC2 ("rein
statistische Zufallsmuster ohne marktlogische Begründung werden nicht als
Hypothese weitergegeben"): diese Migration legt `rule_hypothesis` mit
`anzahl_faelle`/`zeitraum_von`/`zeitraum_bis`/`signalquelle`/
`asset_class_id` (AC1) sowie `marktlogik` (AC2) als NOT-NULL-Pflichtfelder
an — DB-seitige zweite Sicherungsebene neben dem Pydantic-Vertrag
`app.contracts.research.Hypothese`/`Evidenzprotokoll` und dem App-Filter
`app.domain.research.hypothesen_erzeugung.erzeuge_hypothesen` (→ BR-136).

**Spec-Präzisierung (data-model.md §6 ursprünglich nur `beschreibung`/
`params`/`free_param_count`):** die AC1-Evidenzprotokoll-Felder und
`marktlogik` wurden bei der Umsetzung dieser Story ergänzt, um den
Spec-Vertrag "Hypothese (Research → Gate): `{ hypothese_id, beschreibung,
marktlogik, evidenz{...} }`" vollständig abzubilden.

**FK-Nachrüstung `trial_registry.hypothesis_id → rule_hypothesis.id`:**
die Migration `e4f7a1c9b2d3` (S-059) legte `trial_registry.hypothesis_id`
mangels existierender `rule_hypothesis`-Tabelle noch ohne FK an (siehe
deren Migrations-Docstring: "sobald S-058 rule_hypothesis anlegt, sollte
eine additive Folge-Migration die FK ergänzen"). Diese Migration rüstet
den Constraint additiv nach — data-model.md §6 modelliert `hypothesis_id`
als `FK → rule_hypothesis.id NOT NULL`, keine bestehenden Zeilen/Tests
sind betroffen (Trial-Registry ist zu diesem Zeitpunkt noch nicht in
Produktion befüllt).

Revision ID: 3c0ecd3737cb
Revises: aa1e7addeda8
Create Date: 2026-07-18 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "3c0ecd3737cb"
down_revision: Union[str, Sequence[str], None] = "aa1e7addeda8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rule_hypothesis",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("beschreibung", sa.String(), nullable=False),
        sa.Column("marktlogik", sa.String(), nullable=False),
        sa.Column("anzahl_faelle", sa.Integer(), nullable=False),
        sa.Column("zeitraum_von", sa.DateTime(timezone=True), nullable=False),
        sa.Column("zeitraum_bis", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signalquelle", sa.String(), nullable=False),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            nullable=False,
        ),
        sa.Column("params", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("free_param_count", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("anzahl_faelle > 0", name="ck_rule_hypothesis_anzahl_faelle_positive"),
        sa.CheckConstraint(
            "zeitraum_bis >= zeitraum_von", name="ck_rule_hypothesis_zeitraum_konsistent"
        ),
    )
    op.create_index("ix_rule_hypothesis_asset_class_id", "rule_hypothesis", ["asset_class_id"])

    op.create_foreign_key(
        "fk_trial_registry_hypothesis_id",
        "trial_registry",
        "rule_hypothesis",
        ["hypothesis_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_trial_registry_hypothesis_id", "trial_registry", type_="foreignkey")
    op.drop_index("ix_rule_hypothesis_asset_class_id", table_name="rule_hypothesis")
    op.drop_table("rule_hypothesis")
