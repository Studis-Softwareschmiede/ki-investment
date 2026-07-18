"""create gate_result (AC10/AC11/AC12 Ampel + Metriken)

Covers (lernschleife): AC10, AC11, AC12

Quelle: docs/data-model.md §6 `gate_result` (C-012), §8 Index `(trial_id)`,
`(ampel)`, §11 Migrations-Reihenfolge Punkt 8 (`rule_hypothesis` →
`trial_registry` → `gate_result`); Spec `docs/specs/lernschleife.md`
AC10/AC11/AC12, Story S-062; BR-119 (`gate_result.ampel`), BR-120
(`gate_result.min_trl`).

AC10 ("Das Gate gibt genau eine Ampel je Hypothese aus: 🟢/🟡/🔴"): diese
Migration legt `gate_result` mit `ampel CHECK IN ('gruen','gelb','rot')`
an — die Ampel selbst leitet der reine Domain-Kern
`app.domain.lernschleife.gate.leite_ampel_ab` ab (P1, kein DB-Zugriff);
eine Hypothese ohne Urteil (AC4/A3, Stichprobe unter der
Bewertungsuntergrenze) erzeugt bewusst KEINE Zeile hier (kein Ampel-Wert
für "kein Urteil").

`stufe CHECK IN ('A_historisch','B_paper')`: eine Zeile je Gate-Auswertung
(nach Stufe A ODER nach Stufe B) — `psr`/`min_trl` sind `NULL`, solange nur
Stufe A ausgewertet wurde (BR-120 verlangt MinTRL nur "bei jeder
[Stufe-B-]Auswertung").

`trial_id` referenziert `trial_registry.id` (nicht `rule_hypothesis.id`):
data-model.md §6 modelliert den Gate-Auswertung als Ergebnis EINES
konkreten, in der Trial-Registry gezählten Versuchs (ER-Überblick
`trial_registry ||--o{ gate_result`).

Kein Append-only-Trigger (im Unterschied zu `trial_registry`, BR-118):
BR-119/BR-120 verlangen für `gate_result` keine "nie löschen"-Invariante,
nur §9 Retention "Unbefristet" (Aufbewahrungsdauer, keine
Lösch-Untersagung) — Struktur analog `rule_hypothesis`/`trial_registry`
(additive Tabelle, keine Trigger).

Revision ID: 8af19cda9240
Revises: 4c822552d4d7
Create Date: 2026-07-18 11:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "8af19cda9240"
down_revision: Union[str, Sequence[str], None] = "4c822552d4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "gate_result",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "trial_id", PGUUID(as_uuid=True), sa.ForeignKey("trial_registry.id"), nullable=False
        ),
        sa.Column("stufe", sa.String(), nullable=False),
        sa.Column("ampel", sa.String(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.Column("wfe", sa.Numeric(6, 4), nullable=True),
        sa.Column("dsr", sa.Numeric(8, 4), nullable=True),
        sa.Column("psr", sa.Numeric(6, 4), nullable=True),
        sa.Column("min_trl", sa.Numeric(8, 2), nullable=True),
        sa.Column("begruendung", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("stufe IN ('A_historisch', 'B_paper')", name="ck_gate_result_stufe"),
        sa.CheckConstraint("ampel IN ('gruen', 'gelb', 'rot')", name="ck_gate_result_ampel"),
    )
    op.create_index("ix_gate_result_trial_id", "gate_result", ["trial_id"])
    op.create_index("ix_gate_result_ampel", "gate_result", ["ampel"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_gate_result_ampel", table_name="gate_result")
    op.drop_index("ix_gate_result_trial_id", table_name="gate_result")
    op.drop_table("gate_result")
