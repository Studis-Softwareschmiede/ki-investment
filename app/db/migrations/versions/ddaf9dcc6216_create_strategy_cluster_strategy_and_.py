"""create strategy cluster strategy and time horizon tables with seed

Covers (strategie-exit-regeln): AC2, AC3, AC4

Quelle: docs/data-model.md §1 `strategy_cluster`/`strategy`/`time_horizon`
(BR-132, C-014), Verträge-Tabelle in docs/specs/strategie-exit-regeln.md,
sowie die Konzept-Detailnotizen "KI Investment – Anlagestrategien.md"
(18 Strategien in 4 Cluster-Zeilen der Übersichtstabelle) und
"KI Investment – Zeithorizonte.md" (9-Stufen-Tabelle +
Transaktionskosten-Details-Tabelle) — beide 1:1 übernommen, keine
coder-eigene Erfindung.

AC2 (18 Strategien in 4 Clustern, MVP-Cluster-Freischaltung): STRATEGY_SEED
listet alle 18 Strategien mit Cluster-Zuordnung + App-Stufe 1:1 aus der
Cluster-Übersichtstabelle der Notiz. STRATEGY_CLUSTER_SEED seedet die 4
Cluster-Zeilen; `freigeschaltet=True` ist ausschliesslich auf
`passiv_regelbasiert` gesetzt (BR-132) — die eigentliche Ablehnung einer
Anforderung ausserhalb des freigeschalteten Clusters (E2) ist Sache von
`app.db.strategie_katalog.pruefe_cluster_freischaltung()`, nicht dieser
Migration.

AC3 (9 Zeithorizont-Stufen, Transaktionskosten-Relevanz + Break-Even-
Anforderung je Stufe): TIME_HORIZON_SEED übernimmt beide Spalten 1:1 aus den
zwei Tabellen der Notiz (Übersichtstabelle: Transaktionskosten-Relevanz;
Transaktionskosten-Details-Tabelle: Break-Even-Anforderung, dort teils über
mehrere Stufen gruppiert — Werte werden je Einzelstufe identisch
übernommen, siehe Kommentare in TIME_HORIZON_SEED).

AC4 (Strategie/Zeithorizont unabhängige Dimensionen): weder `strategy` noch
`time_horizon` noch die Seed-Daten enthalten eine Kreuzreferenz oder ein
Constraint zwischen beiden Tabellen — jede Strategie ist mit jedem
Zeithorizont kombinierbar, ohne dass diese Migration eine Kombination
blockiert.

Revision ID: ddaf9dcc6216
Revises: 0da3d5a72ba2
Create Date: 2026-07-13 02:06:25.360386

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "ddaf9dcc6216"
down_revision: Union[str, Sequence[str], None] = "0da3d5a72ba2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 4 Cluster (C-014) — MVP-Freischaltung (AC2, BR-132): ausschliesslich
# passiv_regelbasiert ist per Default freigeschaltet; die drei anderen
# Cluster sind registriert, aber gesperrt, bis eine spätere App-Stufe sie
# per UPDATE freischaltet (Konfigurationsdatum, NFR "zur Laufzeit
# konfigurierbar" — kein Code-/Migrations-Deploy nötig).
STRATEGY_CLUSTER_SEED = [
    {"code": "passiv_regelbasiert", "name": "Passiv/Regelbasiert", "freigeschaltet": True},
    {"code": "aktiv_fundamental", "name": "Aktiv-Fundamental", "freigeschaltet": False},
    {"code": "aktiv_technisch_makro", "name": "Aktiv-Technisch/Makro", "freigeschaltet": False},
    {"code": "professionell_algo", "name": "Professionell/Algorithmisch", "freigeschaltet": False},
]

# 18 Strategien, 1:1 aus der Cluster-Übersichtstabelle in
# "KI Investment – Anlagestrategien.md" (Zeilen "Strategien"-Spalte je
# Cluster) + App-Stufe-Spalte derselben Tabelle.
STRATEGY_SEED = [
    # Passiv/Regelbasiert (MVP) — 4 Strategien
    {"name": "Index", "cluster": "passiv_regelbasiert", "stufe": "MVP"},
    {"name": "DCA", "cluster": "passiv_regelbasiert", "stufe": "MVP"},
    {"name": "Dividende", "cluster": "passiv_regelbasiert", "stufe": "MVP"},
    {"name": "Factor/Smart Beta", "cluster": "passiv_regelbasiert", "stufe": "MVP"},
    # Aktiv-Fundamental (Stufe 2) — 7 Strategien
    {"name": "Value", "cluster": "aktiv_fundamental", "stufe": "Stufe2"},
    {"name": "Growth", "cluster": "aktiv_fundamental", "stufe": "Stufe2"},
    {"name": "Contrarian", "cluster": "aktiv_fundamental", "stufe": "Stufe2"},
    {"name": "ESG", "cluster": "aktiv_fundamental", "stufe": "Stufe2"},
    {"name": "Thematic", "cluster": "aktiv_fundamental", "stufe": "Stufe2"},
    {"name": "Event-Driven", "cluster": "aktiv_fundamental", "stufe": "Stufe2"},
    {"name": "Distressed", "cluster": "aktiv_fundamental", "stufe": "Stufe2"},
    # Aktiv-Technisch/Makro (Stufe 3) — 5 Strategien
    {"name": "Momentum", "cluster": "aktiv_technisch_makro", "stufe": "Stufe3"},
    {"name": "Short Selling", "cluster": "aktiv_technisch_makro", "stufe": "Stufe3"},
    {"name": "Global Macro", "cluster": "aktiv_technisch_makro", "stufe": "Stufe3"},
    {"name": "Carry Trade", "cluster": "aktiv_technisch_makro", "stufe": "Stufe3"},
    {"name": "Optionen", "cluster": "aktiv_technisch_makro", "stufe": "Stufe3"},
    # Professionell/Algorithmisch (Stufe 4, nur qualifizierte Nutzer) — 2 Strategien
    {"name": "Arbitrage", "cluster": "professionell_algo", "stufe": "Stufe4"},
    {"name": "Quant/Systematic", "cluster": "professionell_algo", "stufe": "Stufe4"},
]

# 9 Zeithorizont-Stufen, 1:1 aus "KI Investment – Zeithorizonte.md":
# Übersichtstabelle (Transaktionskosten-Relevanz) + Transaktionskosten-
# Details-Tabelle (Break-Even-Anforderung, dort gruppiert über
# "Hochfrequenz/Scalping", "Position/Mittel/Lang" bzw.
# "Buy-and-Hold/Generationell" — hier je Einzelstufe identisch übernommen).
TIME_HORIZON_SEED = [
    {
        "id": 1,
        "name": "Hochfrequenz",
        "transaktionskosten_relevanz": "KRITISCH (<0,1 %)",
        "break_even_anforderung": "Gewinn > Kosten in Sekunden",
    },
    {
        "id": 2,
        "name": "Scalping",
        "transaktionskosten_relevanz": "KRITISCH (<0,1 %)",
        "break_even_anforderung": "Gewinn > Kosten in Sekunden",
    },
    {
        "id": 3,
        "name": "Daytrading",
        "transaktionskosten_relevanz": "HOCH (<0,2 %)",
        "break_even_anforderung": "0,5–1 % pro Trade",
    },
    {
        "id": 4,
        "name": "Swing-Trading",
        "transaktionskosten_relevanz": "MITTEL (0,3–0,5 %)",
        "break_even_anforderung": "1–3 % pro Position",
    },
    {
        "id": 5,
        "name": "Position-Trading",
        "transaktionskosten_relevanz": "NIEDRIG (<0,1 %)",
        "break_even_anforderung": "2–5 % pro Position",
    },
    {
        "id": 6,
        "name": "Mittelfristig",
        "transaktionskosten_relevanz": "NIEDRIG",
        "break_even_anforderung": "2–5 % pro Position",
    },
    {
        "id": 7,
        "name": "Langfristig",
        "transaktionskosten_relevanz": "MINIMAL",
        "break_even_anforderung": "2–5 % pro Position",
    },
    {
        "id": 8,
        "name": "Buy-and-Hold",
        "transaktionskosten_relevanz": "MINIMAL",
        "break_even_anforderung": "Jahresrendite nach Kosten",
    },
    {
        "id": 9,
        "name": "Generationell",
        "transaktionskosten_relevanz": "MINIMAL",
        "break_even_anforderung": "Jahresrendite nach Kosten",
    },
]


def upgrade() -> None:
    """Upgrade schema."""
    strategy_cluster = op.create_table(
        "strategy_cluster",
        sa.Column("code", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("freigeschaltet", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "code IN ('passiv_regelbasiert', 'aktiv_fundamental', "
            "'aktiv_technisch_makro', 'professionell_algo')",
            name="ck_strategy_cluster_code",
        ),
    )

    strategy = op.create_table(
        "strategy",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("cluster", sa.String(), sa.ForeignKey("strategy_cluster.code"), nullable=False),
        sa.Column("stufe", sa.String(), nullable=False),
        sa.CheckConstraint(
            "stufe IN ('MVP', 'Stufe2', 'Stufe3', 'Stufe4')", name="ck_strategy_stufe"
        ),
    )

    time_horizon = op.create_table(
        "time_horizon",
        sa.Column("id", sa.SmallInteger(), primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("transaktionskosten_relevanz", sa.String(), nullable=False),
        sa.Column("break_even_anforderung", sa.String(), nullable=False),
        sa.CheckConstraint("id BETWEEN 1 AND 9", name="ck_time_horizon_id_range"),
    )

    # Idempotenter Seed (data-model.md §11 Punkt 10: "ON CONFLICT DO NOTHING") —
    # ein wiederholtes `alembic upgrade head` gegen eine bereits geseedete DB
    # darf keine IntegrityError werfen und die Zeilenzahl nicht verändern.
    op.execute(
        pg_insert(strategy_cluster)
        .values(STRATEGY_CLUSTER_SEED)
        .on_conflict_do_nothing(index_elements=["code"])
    )
    op.execute(
        pg_insert(strategy).values(STRATEGY_SEED).on_conflict_do_nothing(index_elements=["name"])
    )
    op.execute(
        pg_insert(time_horizon)
        .values(TIME_HORIZON_SEED)
        .on_conflict_do_nothing(index_elements=["id"])
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("time_horizon")
    op.drop_table("strategy")
    op.drop_table("strategy_cluster")
