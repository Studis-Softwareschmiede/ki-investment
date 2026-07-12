"""create transaction (append-only Transaktionshistorie & TCA, S-035)

Covers (depot): AC4, AC7

Quelle: docs/data-model.md §4 `transaction` (C-017, präzisiert in S-035 um
`waehrung`/`arrival_price`/`slippage_abs`); Spec `docs/specs/depot.md`
(Story S-035, "Verträge" — Transaktionshistorie-Tupel); BR-115
(Append-only, kein UPDATE/DELETE, Steuer-Auditpfad).

AC4: legt die `transaction`-Tabelle als append-only Historie an (Titel,
Richtung/`typ`, Menge, Fill-Preis, Kosten, Zeitstempel, Währung) — jeder
Fill wird als EIN unveränderlicher Eintrag festgehalten
(`app.adapters.repositories.position_repository
.SqlAlchemyPositionRepository.schreibe_transaktion`, aufgerufen aus
`app.domain.portfolio.position_booking.verbuche_fill`); ein Vollverkauf
schliesst nur die Position (`position.status`), die Historie bleibt
unberührt bestehen (kein FK ON DELETE CASCADE, `position_id` ist zudem
NULLable für FIFO-Multi-Lot-Verkäufe, siehe Modell-Docstring).

AC7: `arrival_price` + `slippage_abs` (= `preis - arrival_price`, gleiche
Formel wie BR-114 `trade_fill.slippage_abs`) sind je Trade gespeichert und
über `historie_je_titel` + die reinen Domain-Aggregations-Funktionen
(`app.domain.portfolio.transaction_historie.aggregiere_slippage`) je Trade
und aggregiert abrufbar.

**Append-only-Durchsetzung (BR-115), DB-Schicht:** unter Postgres legt
diese Migration einen `BEFORE UPDATE OR DELETE`-Trigger an, der jede
Mutation/Löschung mit einer Exception verweigert. Unter anderen Dialekten
(SQLite, Struktur-Tests) wird der Trigger NICHT angelegt (Konvention:
Postgres-spezifische Guards sind in diesem Projekt bereits an anderer
Stelle wirkungslos-aber-fehlerfrei unter SQLite, siehe
`with_for_update()` in `position_repository`) — die App-Schicht der
Durchsetzung (kein Update-/Delete-Port) bleibt davon unberührt.

Revision ID: a1c4e7f2b930
Revises: 385adb3a764b
Create Date: 2026-07-12 20:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

# revision identifiers, used by Alembic.
revision: str = "a1c4e7f2b930"
down_revision: Union[str, Sequence[str], None] = "385adb3a764b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TRIGGER_NAME = "trg_transaction_append_only"
_TRIGGER_FUNCTION_NAME = "transaction_append_only_guard"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "transaction",
        sa.Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "position_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("position.id"),
            nullable=True,
        ),
        sa.Column(
            "instrument_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("instrument.id"),
            nullable=False,
        ),
        sa.Column("typ", sa.String(), nullable=False),
        sa.Column("menge", sa.Numeric(20, 8), nullable=False),
        sa.Column("preis", sa.Numeric(20, 8), nullable=False),
        sa.Column("kosten_chf", sa.Numeric(20, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("waehrung", sa.String(), nullable=False),
        sa.Column("arrival_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("slippage_abs", sa.Numeric(20, 8), nullable=True),
        sa.Column("fx_rate", sa.Numeric(20, 8), nullable=True),
        sa.Column("kapital_gv_chf", sa.Numeric(20, 8), nullable=True),
        sa.Column("waehrungs_gv_chf", sa.Numeric(20, 8), nullable=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column(
            "booked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "typ IN ('buy', 'sell', 'dividend', 'fee', 'fx_adjust')",
            name="ck_transaction_typ",
        ),
        sa.CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_transaction_mode"),
        sa.CheckConstraint("length(waehrung) = 3", name="ck_transaction_waehrung_iso3"),
    )
    op.create_index("ix_transaction_position_id", "transaction", ["position_id"])
    op.create_index("ix_transaction_instrument_id", "transaction", ["instrument_id"])
    op.create_index("ix_transaction_booked_at", "transaction", ["booked_at"])
    op.create_index("ix_transaction_mode", "transaction", ["mode"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {_TRIGGER_FUNCTION_NAME}() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION
                    'transaction ist append-only (BR-115) - UPDATE/DELETE nicht erlaubt';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {_TRIGGER_NAME}
            BEFORE UPDATE OR DELETE ON transaction
            FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FUNCTION_NAME}();
            """
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON transaction;")
        op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FUNCTION_NAME}();")

    op.drop_index("ix_transaction_mode", table_name="transaction")
    op.drop_index("ix_transaction_booked_at", table_name="transaction")
    op.drop_index("ix_transaction_instrument_id", table_name="transaction")
    op.drop_index("ix_transaction_position_id", table_name="transaction")
    op.drop_table("transaction")
