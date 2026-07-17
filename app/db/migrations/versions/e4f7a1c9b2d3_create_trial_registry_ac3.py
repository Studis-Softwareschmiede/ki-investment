"""create trial_registry (AC3 append-only Trial-Registry)

Covers (lernschleife): AC3

Quelle: docs/data-model.md §6 `trial_registry` (C-012), §8 Index
`(hypothesis_id)` + `UNIQUE (hypothesis_id, variant_hash)`, §9 Retention
(„Unbefristet" — DSR-Zählung braucht alle je getesteten Varianten, → BR-118);
Spec `docs/specs/lernschleife.md` AC3, Story S-059.

AC3 ("Jede an das Gate übergebene Regelvariante wird in einer
Trial-Registry gezählt — auch verworfene ... Abgelehnte Regeln werden
archiviert, nie gelöscht"): diese Migration legt die `trial_registry`-
Tabelle als append-only-Store an. `archived` (Default `false`) wird bei
Ablehnung einer Variante auf `true` gesetzt (App-Layer,
`app.db.trial_registry.archiviere_trial`) — die Zeile selbst bleibt
unverändert bestehen, es findet **kein DELETE** statt.

**hypothesis_id bewusst OHNE FK (Sequenzierungslücke, kein Scope-
Downgrade):** data-model.md §6 modelliert `hypothesis_id` als
`FK → rule_hypothesis.id NOT NULL`. Die Tabelle `rule_hypothesis` selbst
gehört zu AC1/AC2 (Story S-058, Research-Hypothesen-Erzeugung) — S-059 hat
laut Board explizit KEINE Story-Abhängigkeit zu S-058 und `rule_hypothesis`
existiert zum Zeitpunkt dieser Migration nicht. `hypothesis_id` bleibt daher
vorerst ein reiner `UUID NOT NULL`-Wert ohne referentielle Integrität;
sobald S-058 `rule_hypothesis` anlegt, sollte eine additive Folge-Migration
die FK ergänzen (`ALTER TABLE trial_registry ADD CONSTRAINT ... FOREIGN
KEY (hypothesis_id) REFERENCES rule_hypothesis (id)`).

**Append-only-Durchsetzung (BR-118), DB-Schicht:** BR-118 verlangt
abweichend von BR-115 (`transaction`, volle Immutabilität) explizit nur
„kein Delete-Grant" — `archived` muss von `false` auf `true` wechseln
können (Ablehnung), nur das Löschen einer Zeile ist untersagt. Unter
Postgres legt diese Migration daher einen `BEFORE DELETE`-Trigger an
(nicht `BEFORE UPDATE OR DELETE` wie bei `transaction`), der jede Löschung
mit einer Exception verweigert; UPDATE bleibt zulässig (App-Layer nutzt das
ausschliesslich für die `archived`-Spalte). Unter anderen Dialekten
(SQLite, Struktur-Tests) wird der Trigger NICHT angelegt (bestehende
Projekt-Konvention, siehe `create_transaction_historie`-Migration).

Revision ID: e4f7a1c9b2d3
Revises: f908ab5874fe
Create Date: 2026-07-18 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "e4f7a1c9b2d3"
down_revision: Union[str, Sequence[str], None] = "f908ab5874fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGER_NAME = "trg_trial_registry_no_delete"
_TRIGGER_FUNCTION_NAME = "trial_registry_no_delete_guard"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trial_registry",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("hypothesis_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("variant_hash", sa.String(), nullable=False),
        sa.Column("params", sa.JSON().with_variant(JSONB, "postgresql"), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "tested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "hypothesis_id", "variant_hash", name="uq_trial_registry_hypothesis_variant"
        ),
    )
    op.create_index("ix_trial_registry_hypothesis_id", "trial_registry", ["hypothesis_id"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {_TRIGGER_FUNCTION_NAME}() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'trial_registry ist append-only (BR-118) - DELETE nicht erlaubt';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {_TRIGGER_NAME}
            BEFORE DELETE ON trial_registry
            FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FUNCTION_NAME}();
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON trial_registry;")
        op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION_NAME}();")

    op.drop_index("ix_trial_registry_hypothesis_id", table_name="trial_registry")
    op.drop_table("trial_registry")
