"""create hybrid_entscheid (AC29/AC30/AC31 offene Hybrid-Entscheide)

Covers (frontend-cockpit): AC29, AC30, AC31

Quelle: docs/data-model.md §4 `hybrid_entscheid` (C-016), §8 Index
`(status, mode, frist)`, `(instrument_id)`; Spec
`docs/specs/frontend-cockpit.md` AC29/AC30/AC31, Story S-080; BR-141
(`hybrid_entscheid.mode`).

**DBA-Review Iteration 2 (Suggestions, vor Landung kostenlos nachgezogen):**
(a) `(status, mode)`-Index um `frist` erweitert (`(status, mode, frist)`) —
deckt die AC29-Query (`WHERE status='offen' AND mode='simuliert' ORDER BY
frist ASC`, `SqlAlchemyHybridEntscheidungRepository.offene_entscheide`) als
vollständigen Covering-Index ab. (b) `CHECK (groesse > 0)` ergänzt (analog
`position.menge`, `ck_position_menge_non_negative`-Konvention, hier strikt
positiv).

AC29 ("offene, bestätigungspflichtige Entscheide des Hybrid-Modus ...
Titel, Richtung Kauf/Verkauf, Grösse, vorgeschlagene Order, Frist/Ablauf,
Begründung"): kein bestehendes Modul legt heute eine solche Zeile an (der
Buy-/Sell-Pfad, S-028/S-034, gibt ein reines In-Prozess-Signal weiter; die
S-056-Warteliste ist ein reiner Struktur-Flag ohne eigene Persistenz) —
diese Migration legt die schlanke, HTTP-abfragbare Persistenz dafür an.

`mode CHECK IN ('simuliert')` (AC30/BR-019-Härtung, → BR-141): anders als
die übrigen `mode`-Spalten (`echt`/`simuliert`, BR-130) lässt diese
Tabelle strukturell GAR KEINEN `'echt'`-Wert zu — die MVP-Live-Sperre
("eine Bestätigung löst im MVP ausschliesslich simulierte Orders aus",
AC30) gilt bereits auf Schema-Ebene.

Kein Append-only-Trigger: `status` wird bewusst per UPDATE fortgeschrieben
(`offen` → `bestaetigt`/`abgelehnt`, AC30-Control-Plane-Schreibpfad
`app.db.hybrid_entscheide.entscheide`) — anders als z. B. `transaction`
(BR-115) gibt es hier keine Append-only-Invariante.

Revision ID: 827b9dcc737c
Revises: 4b55b546a716
Create Date: 2026-07-19 08:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "827b9dcc737c"
down_revision: Union[str, Sequence[str], None] = "4b55b546a716"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "hybrid_entscheid",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "instrument_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("instrument.id"),
            nullable=False,
        ),
        sa.Column("richtung", sa.String(), nullable=False),
        sa.Column("groesse", sa.Numeric(20, 8), nullable=False),
        sa.Column("vorgeschlagene_order", sa.String(), nullable=False),
        sa.Column("frist", sa.DateTime(timezone=True), nullable=False),
        sa.Column("begruendung", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'offen'"),
        ),
        sa.Column(
            "mode",
            sa.String(),
            nullable=False,
            server_default=sa.text("'simuliert'"),
        ),
        sa.Column(
            "erstellt_am",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("entschieden_am", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("richtung IN ('kauf', 'verkauf')", name="ck_hybrid_entscheid_richtung"),
        sa.CheckConstraint(
            "status IN ('offen', 'bestaetigt', 'abgelehnt')", name="ck_hybrid_entscheid_status"
        ),
        sa.CheckConstraint("mode IN ('simuliert')", name="ck_hybrid_entscheid_mode"),
        sa.CheckConstraint("groesse > 0", name="ck_hybrid_entscheid_groesse_positive"),
    )
    op.create_index(
        "ix_hybrid_entscheid_status_mode_frist", "hybrid_entscheid", ["status", "mode", "frist"]
    )
    op.create_index("ix_hybrid_entscheid_instrument_id", "hybrid_entscheid", ["instrument_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_hybrid_entscheid_instrument_id", table_name="hybrid_entscheid")
    op.drop_index("ix_hybrid_entscheid_status_mode_frist", table_name="hybrid_entscheid")
    op.drop_table("hybrid_entscheid")
