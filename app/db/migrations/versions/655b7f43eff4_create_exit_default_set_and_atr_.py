"""create exit_default_set and atr_multiplier_default tables with seed

Covers (strategie-exit-regeln): AC6, AC7, AC8, AC9

Quelle: docs/data-model.md §1 `exit_default_set`/`atr_multiplier_default`,
Verträge-Abschnitt "Konfigurationsdaten (provisorische Defaults)" in
docs/specs/strategie-exit-regeln.md — die AC8-Tabelle (Default-Exit-Set je
Strategie/Klasse) sowie die AC9-Bandbreite (ATR-Multiplikator je
Volatilitätsklasse), beide 1:1 aus der Spec übernommen (siehe die
AC8-/AC9-Präzisierungs-Blockquotes in der Spec für die dort dokumentierten
Konkretisierungs-Entscheidungen: `index_buy_and_hold`-Mittelwert 27.5 % statt
der Spanne 25–30 %, `atr_multiplier_default`-Punktwerte als Bandbreiten-
Mittelpunkte).

AC6 (drei Exit-Regel-Kategorien immer dokumentiert): diese Migration liefert
nur die Konfigurationsdaten für die Stop-Trigger-Kategorie (AC7-AC9) — die
Validierung, dass Thesis-Breakpoint + Stop-Trigger nie leer sind, ist
`app.db.exit_regel_ableitung.leite_exit_regeln_ab`.

AC7 (ATR-basierte Stop-Regeln statt fixer Prozentwerte als Default):
`exit_default_set.stop_typ` ist für 3 von 5 Kategorien `atr_trailing`
(growth_momentum, krypto) bzw. `technisch` (daytrade_swing, kein Prozent-
Stop); nur `index_buy_and_hold` nutzt `fix_pct` — eine von der Spec selbst
explizit vorgesehene Kategorie-Ausnahme (AC8: "weiter Stop 25–30 % oder
keiner"), kein blanket Default. Der generische Fallback für Strategien ohne
eigene Tabellenzeile hat bewusst KEINE Seed-Zeile hier (siehe
`app.db.exit_regel_ableitung.klassifiziere_exit_kategorie`-Docstring) — er
verwendet `atr_trailing` als AC7-Baseline, ohne eine `fix_pct`-Alternative.

AC8 (Default-Exit-Set je Strategie/Klasse, provisorisch/konfigurierbar):
EXIT_DEFAULT_SET_SEED seedet die 5 Tabellenzeilen. `stop_parameter_pct`
(nur `index_buy_and_hold` gesetzt), `take_profit_hinweis`, `time_box` sind
Freitext-/Konfigurationsfelder — `app.db.exit_regel_ableitung` interpretiert
sie, diese Migration definiert nur die Startwerte.

AC9 (ATR-Multiplikator je Volatilitätsklasse, provisorisch/konfigurierbar):
ATR_MULTIPLIER_DEFAULT_SEED seedet `ruhig`/`volatil` mit dem
Bandbreiten-Mittelpunkt als angewandtem `multiplikator`
(2.25 = Mittelpunkt 2.0–2.5; 3.50 = Mittelpunkt 3.0–4.0) plus den
Original-Grenzwerten als Referenz.

Beide Tabellen sind reine Konfigurationsdaten (analog `strategy_cluster`,
Migration `ddaf9dcc6216`) — zur Laufzeit per `UPDATE` änderbar, kein
Code-/Migrations-Deploy nötig (NFR "zur Laufzeit konfigurierbar" +
"im Simulationsmodus kalibrierbar").

Revision ID: 655b7f43eff4
Revises: f908ab5874fe
Create Date: 2026-07-18 09:00:00.000000

"""

from datetime import timedelta
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "655b7f43eff4"
down_revision: Union[str, Sequence[str], None] = "f908ab5874fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# AC8: 5 Default-Exit-Set-Kategorien, 1:1 aus der Spec-Tabelle
# (docs/specs/strategie-exit-regeln.md AC8). Siehe Modul-Docstring für die
# AC7-Einordnung je `stop_typ` und die AC8-Präzisierung (Spec) für den
# gewählten `index_buy_and_hold`-Prozent-Mittelwert.
EXIT_DEFAULT_SET_SEED = [
    {
        "kategorie": "value_aktien",
        "stop_typ": "fundamental",
        "stop_parameter_hinweis": "fundamentaler Stop (These bricht)",
        "stop_parameter_pct": None,
        "take_profit_hinweis": "bei Zielwert",
        "time_box": timedelta(days=3 * 365),
    },
    {
        "kategorie": "growth_momentum",
        "stop_typ": "atr_trailing",
        "stop_parameter_hinweis": "ATR-Trailing-Stop, 2.5–3× ATR",
        "stop_parameter_pct": None,
        "take_profit_hinweis": "gestaffelt/kein fixer Take-Profit",
        "time_box": None,
    },
    {
        "kategorie": "index_buy_and_hold",
        "stop_typ": "fix_pct",
        "stop_parameter_hinweis": "weiter Stop 25–30 % oder keiner",
        "stop_parameter_pct": 27.5,
        "take_profit_hinweis": None,
        "time_box": None,
    },
    {
        "kategorie": "krypto",
        "stop_typ": "atr_trailing",
        "stop_parameter_hinweis": "weiter ATR-Trailing-Stop plus Teilgewinne",
        "stop_parameter_pct": None,
        "take_profit_hinweis": "Teilgewinne (gestaffelt)",
        "time_box": None,
    },
    {
        "kategorie": "daytrade_swing",
        "stop_typ": "technisch",
        "stop_parameter_hinweis": "technischer Stop unter Support − Puffer",
        "stop_parameter_pct": None,
        "take_profit_hinweis": None,
        "time_box": None,
    },
]

# AC9: ATR-Multiplikator je Volatilitätsklasse — `multiplikator` ist der
# Bandbreiten-Mittelpunkt (Richtwert der Spec: ruhig 2–2.5×, volatil 3–4×).
ATR_MULTIPLIER_DEFAULT_SEED = [
    {
        "volatilitaetsklasse": "ruhig",
        "multiplikator": 2.25,
        "multiplikator_min": 2.0,
        "multiplikator_max": 2.5,
    },
    {
        "volatilitaetsklasse": "volatil",
        "multiplikator": 3.5,
        "multiplikator_min": 3.0,
        "multiplikator_max": 4.0,
    },
]


def upgrade() -> None:
    """Upgrade schema."""
    exit_default_set = op.create_table(
        "exit_default_set",
        sa.Column("kategorie", sa.String(), primary_key=True),
        sa.Column("stop_typ", sa.String(), nullable=False),
        sa.Column("stop_parameter_hinweis", sa.String(), nullable=False),
        sa.Column("stop_parameter_pct", sa.Numeric(6, 3), nullable=True),
        sa.Column("take_profit_hinweis", sa.String(), nullable=True),
        sa.Column("time_box", sa.Interval(), nullable=True),
        sa.CheckConstraint(
            "kategorie IN ('value_aktien', 'growth_momentum', 'index_buy_and_hold', "
            "'krypto', 'daytrade_swing')",
            name="ck_exit_default_set_kategorie",
        ),
        sa.CheckConstraint(
            "stop_typ IN ('fundamental', 'atr_trailing', 'fix_pct', 'technisch', 'keiner')",
            name="ck_exit_default_set_stop_typ",
        ),
    )

    atr_multiplier_default = op.create_table(
        "atr_multiplier_default",
        sa.Column("volatilitaetsklasse", sa.String(), primary_key=True),
        sa.Column("multiplikator", sa.Numeric(5, 2), nullable=False),
        sa.Column("multiplikator_min", sa.Numeric(5, 2), nullable=False),
        sa.Column("multiplikator_max", sa.Numeric(5, 2), nullable=False),
        sa.CheckConstraint(
            "volatilitaetsklasse IN ('ruhig', 'volatil')",
            name="ck_atr_multiplier_default_volatilitaetsklasse",
        ),
    )

    # Idempotenter Seed (data-model.md §11 Punkt 10: "ON CONFLICT DO NOTHING"),
    # analog Migration ddaf9dcc6216.
    op.execute(
        pg_insert(exit_default_set)
        .values(EXIT_DEFAULT_SET_SEED)
        .on_conflict_do_nothing(index_elements=["kategorie"])
    )
    op.execute(
        pg_insert(atr_multiplier_default)
        .values(ATR_MULTIPLIER_DEFAULT_SEED)
        .on_conflict_do_nothing(index_elements=["volatilitaetsklasse"])
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("atr_multiplier_default")
    op.drop_table("exit_default_set")
