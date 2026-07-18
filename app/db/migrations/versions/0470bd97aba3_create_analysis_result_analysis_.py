"""create analysis_result, analysis_category_score, analysis_fact (AC4/AC5/AC7)

Covers (frontend-cockpit): AC4, AC5, AC7

Quelle: docs/data-model.md §3 `analysis_result`/`analysis_category_score`/
`analysis_fact` (C-007, C-008), §8 Indizes, §11 Migrations-Reihenfolge
Punkt 5 ("`analysis_result` referenziert bei Einführung zusätzlich
`category_weight_version.id` und `analysis_method_version.id`"); Spec
`docs/specs/frontend-cockpit.md` AC4/AC5/AC7, Story S-066; BR-103, BR-104,
BR-105, BR-106, BR-107, BR-108.

Schliesst den in `architecture.md` §13.3-Fussnote benannten Read-Modell-Gap:
Kandidaten-Analysen (5 Kategorie-Scores + geerdete Fakten) lagen bislang
nur als reine Domänen-Rechnung vor (`app.domain.scoring.score_engine`) —
diese Migration legt die erste persistente, HTTP-abfragbare Ablage an
(`app.api.queries.kandidaten`, `GET /api/kandidaten` + `GET
/api/kandidaten/{id}`). Kein Order-Pfad-Verhalten (AC7, rein lesend).

`analysis_result.gesamtscore`/`signal_enum` sind NULLable (No-Evidence-No-
Trade-Übersprung, → BR-108) — anders als z.B. `gate_result.ampel` gibt es
hier keinen Erzeuger-Pfad, der IMMER einen vollständigen Wert liefert.

`ON DELETE CASCADE` auf `analysis_category_score.analysis_result_id` und
`analysis_fact.analysis_result_id` (data-model.md §3: "FK → analysis_
result.id (ON DELETE CASCADE)") — beide Kind-Tabellen haben keine
eigenständige Existenz ohne ihre `analysis_result`-Zeile.

Revision ID: 0470bd97aba3
Revises: 8af19cda9240
Create Date: 2026-07-19 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "0470bd97aba3"
down_revision: Union[str, Sequence[str], None] = "8af19cda9240"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ANALYSE_TYP_VALUES = ("neue_titel", "bestehende_titel")
_SIGNAL_VALUES = ("KAUF", "BEOBACHTEN", "HALTEN", "REDUZIEREN", "VERKAUF")
_EXIT_URGENCY_VALUES = ("hard_exit", "soft_exit", "none")
_CROSS_CHECK_STATUS_VALUES = ("ok", "abweichung", "nicht_pruefbar")


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "analysis_result",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "instrument_id", PGUUID(as_uuid=True), sa.ForeignKey("instrument.id"), nullable=False
        ),
        sa.Column("analyse_typ", sa.String(), nullable=True),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            nullable=False,
        ),
        sa.Column(
            "category_weight_version_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("category_weight_version.id"),
            nullable=False,
        ),
        sa.Column(
            "analysis_method_version_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("analysis_method_version.id"),
            nullable=False,
        ),
        sa.Column("gesamtscore", sa.Numeric(6, 3), nullable=True),
        sa.Column("signal_enum", sa.String(), nullable=True),
        sa.Column("exit_urgency", sa.String(), nullable=True),
        sa.Column("sanity_cap_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schema_valid", sa.Boolean(), nullable=False),
        sa.Column("llm_model", sa.String(), nullable=True),
        sa.Column("mode", sa.String(), nullable=True),
        sa.Column("begruendung", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"analyse_typ IN ({', '.join(repr(v) for v in _ANALYSE_TYP_VALUES)})",
            name="ck_analysis_result_analyse_typ",
        ),
        sa.CheckConstraint(
            "gesamtscore IS NULL OR (gesamtscore >= 0 AND gesamtscore <= 10)",
            name="ck_analysis_result_gesamtscore_range",
        ),
        sa.CheckConstraint(
            f"signal_enum IN ({', '.join(repr(v) for v in _SIGNAL_VALUES)})",
            name="ck_analysis_result_signal_enum",
        ),
        sa.CheckConstraint(
            f"exit_urgency IN ({', '.join(repr(v) for v in _EXIT_URGENCY_VALUES)})",
            name="ck_analysis_result_exit_urgency",
        ),
        sa.CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_analysis_result_mode"),
    )
    op.create_index(
        "ix_analysis_result_instrument_id_created_at",
        "analysis_result",
        ["instrument_id", "created_at"],
    )
    op.create_index("ix_analysis_result_analyse_typ", "analysis_result", ["analyse_typ"])
    op.create_index("ix_analysis_result_mode", "analysis_result", ["mode"])

    op.create_table(
        "analysis_category_score",
        sa.Column(
            "analysis_result_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "category_code",
            sa.String(),
            sa.ForeignKey("analysis_category.code"),
            primary_key=True,
        ),
        sa.Column("score", sa.Numeric(6, 3), nullable=True),
        sa.Column("evidence_present", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 10)",
            name="ck_analysis_category_score_range",
        ),
    )
    op.create_index(
        "ix_analysis_category_score_analysis_result_id",
        "analysis_category_score",
        ["analysis_result_id"],
    )

    op.create_table(
        "analysis_fact",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "analysis_result_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("analysis_result.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kennzahl", sa.String(), nullable=False),
        sa.Column("wert", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "source_id", PGUUID(as_uuid=True), sa.ForeignKey("data_source.id"), nullable=False
        ),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cross_check_status", sa.String(), nullable=True),
        sa.Column("abweichung_pct", sa.Numeric(8, 4), nullable=True),
        sa.CheckConstraint(
            f"cross_check_status IN ({', '.join(repr(v) for v in _CROSS_CHECK_STATUS_VALUES)})",
            name="ck_analysis_fact_cross_check_status",
        ),
    )
    op.create_index("ix_analysis_fact_analysis_result_id", "analysis_fact", ["analysis_result_id"])
    op.create_index("ix_analysis_fact_source_id", "analysis_fact", ["source_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_analysis_fact_source_id", table_name="analysis_fact")
    op.drop_index("ix_analysis_fact_analysis_result_id", table_name="analysis_fact")
    op.drop_table("analysis_fact")

    op.drop_index(
        "ix_analysis_category_score_analysis_result_id",
        table_name="analysis_category_score",
    )
    op.drop_table("analysis_category_score")

    op.drop_index("ix_analysis_result_mode", table_name="analysis_result")
    op.drop_index("ix_analysis_result_analyse_typ", table_name="analysis_result")
    op.drop_index("ix_analysis_result_instrument_id_created_at", table_name="analysis_result")
    op.drop_table("analysis_result")
