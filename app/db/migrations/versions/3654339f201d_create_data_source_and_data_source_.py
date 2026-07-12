"""create data_source and data_source_asset_class tables with seed 12 sources

Covers (dateneingang): AC5, AC6, AC13

Quelle: docs/data-model.md §1 `data_source` + `data_source_asset_class`
(C-009, BR-123, BR-126), Verträge-Tabelle "Quellen-Registry-Eintrag" in
docs/specs/dateneingang.md, Original-Notiz
"KI Investment – Datenquellen.md" (12 Quellen, 5 Kategorien, Kosten- und
Anlageklassen-Zuordnung 1:1 übernommen).

`data_source` ist in data-model.md §11 (Migrations-Reihenfolge) Teil der
"Konfig mit FK auf Basis" (Schritt 2) — sie hat KEINE FK-Abhängigkeit zu
`asset_class`, nur `data_source_asset_class` referenziert beide Tabellen
(M:N, AC5). Ausschliesslich die 5 im MVP kostenlosen Quellen (SEC Form 4,
Reddit, Polymarket, FRED, Wirtschaftskalender — AC13, wörtlich aus der Spec
übernommen) tragen `aktiv=true`; alle anderen 7 Quellen sind registriert,
aber `aktiv=false` (kostenpflichtig/institutionell, auch wenn einzelne davon
zusätzlich einen Free-Tier haben — z. B. Nansen/Leeway/CBonds — AC13 zählt
namentlich nur die 5 genannten Quellen zur aktiven MVP-Menge, keine
implizite "hat einen kostenlosen Tarif"-Regel).

`data_source_asset_class` bildet AC5 (Anlageklassen-Zuordnung je Quelle) und
AC6 (Reddit nur retail-getriebene Klassen 1/7, siehe BR-123) strukturell ab:
Reddit trägt in dieser Seed-Tabelle ausschliesslich die Zeilen
(reddit, 1) und (reddit, 7) — für Obligationen (4) und FX (10) existiert
keine Reddit-Zeile, d. h. es kann für diese Klassen strukturell kein
Reddit-Match aus der Registry entstehen (kein Abruf, AC6).

Fehlende Detailwerte (z. B. `rate_limit` oder `kosten_monatlich_chf` bei
institutionellen Quellen mit "Custom Pricing") werden bewusst NICHT erfunden
— die Original-Notiz nennt hierfür keinen Zahlenwert, die Spalte bleibt NULL
(beides ist laut data-model.md §1 nullable, keine NOT-NULL-Vorgabe).

Revision ID: 3654339f201d
Revises: 2da446925bbc
Create Date: 2026-07-12 15:15:12.739148

"""

from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "3654339f201d"
down_revision: Union[str, Sequence[str], None] = "2da446925bbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 12 Datenquellen in 5 Kategorien (AC5), 1:1 aus
# "KI Investment – Datenquellen.md" (Analyse-Session 29.06.2026, C-009).
# `aktiv` folgt ausschliesslich der wörtlichen AC13-Aufzählung (die 5 im MVP
# kostenlosen Quellen); `vault_ref` ist nur gesetzt, wo die Original-Notiz
# explizit "API-Key/OAuth/Token nötig" nennt (BR-126 — kein Klartext-Secret,
# nur ein Zeiger-Name auf die künftige Env-Var/Secrets-Store-Referenz).
DATA_SOURCE_SEED = [
    {
        "name": "SEC Form 4 Insider-Trades",
        "kategorie": "equity_fundamentals",
        "qualitaet": "hoch",
        "frequenz_sekunden": 7200,
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST",
        "rate_limit": "10 req/sec",
        "vault_ref": None,
        "aktiv": True,
    },
    {
        "name": "Finnhub Fundamentals & News",
        "kategorie": "equity_fundamentals",
        "qualitaet": "hoch",
        "frequenz_sekunden": 1200,
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": Decimal("45.00"),
        "zugangsart": "REST+WebSocket",
        "rate_limit": None,
        "vault_ref": "FINNHUB_API_KEY",
        "aktiv": False,
    },
    {
        "name": "Reddit WallStreetBets Sentiment",
        "kategorie": "retail_social",
        "qualitaet": "mittel",
        "frequenz_sekunden": 1200,
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST (OAuth via PRAW)",
        "rate_limit": "100 req/min",
        "vault_ref": "REDDIT_OAUTH_CREDENTIALS",
        "aktiv": True,
    },
    {
        "name": "Polymarket Prediction Markets",
        "kategorie": "blockchain_crypto",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 45,
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST+WebSocket",
        "rate_limit": "60-100 req/min",
        "vault_ref": None,
        "aktiv": True,
    },
    {
        "name": "Whale Alert Blockchain",
        "kategorie": "blockchain_crypto",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 45,
        "kostenmodell": "pro",
        "kosten_monatlich_chf": Decimal("28.00"),
        "zugangsart": "REST+WebSocket",
        "rate_limit": "1000 calls/min",
        "vault_ref": None,
        "aktiv": False,
    },
    {
        "name": "Nansen Smart Money Tracking",
        "kategorie": "blockchain_crypto",
        "qualitaet": "hoch",
        "frequenz_sekunden": 30,
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": Decimal("46.00"),
        "zugangsart": "REST",
        "rate_limit": "20 req/sec, 500 req/min",
        "vault_ref": "NANSEN_API_KEY",
        "aktiv": False,
    },
    {
        "name": "Morningstar ETF & Fonds",
        "kategorie": "etf_fonds",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 86400,
        "kostenmodell": "institutionell",
        "kosten_monatlich_chf": None,
        "zugangsart": "REST (Token, Morningstar Direct)",
        "rate_limit": None,
        "vault_ref": "MORNINGSTAR_API_TOKEN",
        "aktiv": False,
    },
    {
        "name": "Leeway Tech ETF & Stocks",
        "kategorie": "etf_fonds",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 3600,
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": Decimal("50.00"),
        "zugangsart": "REST (Token)",
        "rate_limit": "50 req/day (Free) / 100000 req/day (Paid)",
        "vault_ref": "LEEWAY_API_TOKEN",
        "aktiv": False,
    },
    {
        "name": "EPFR Global Fund Flows",
        "kategorie": "etf_fonds",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 86400,
        "kostenmodell": "institutionell",
        "kosten_monatlich_chf": None,
        "zugangsart": "Feed+REST (via Massive)",
        "rate_limit": None,
        "vault_ref": None,
        "aktiv": False,
    },
    {
        "name": "FRED – Federal Reserve Economic Data",
        "kategorie": "makro_anleihen",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 86400,
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST",
        "rate_limit": None,
        "vault_ref": "FRED_API_KEY",
        "aktiv": True,
    },
    {
        "name": "Wirtschaftskalender (Finnworlds)",
        "kategorie": "makro_anleihen",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 3600,
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST",
        "rate_limit": None,
        "vault_ref": None,
        "aktiv": True,
    },
    {
        "name": "CBonds Staatsanleihen & Renten",
        "kategorie": "makro_anleihen",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 3600,
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": None,
        "zugangsart": "REST/Feed",
        "rate_limit": None,
        "vault_ref": None,
        "aktiv": False,
    },
]

# Anlageklassen-Zuordnung je Quelle (AC5), M:N via `data_source_asset_class`.
# `name` referenziert `DATA_SOURCE_SEED[i]["name"]` (per Lookup zur
# `data_source.id`-UUID zur Insert-Zeit, siehe `upgrade()`).
# Reddit deckt strukturell NUR die retail-getriebenen Klassen 1 (Aktien) und
# 7 (Krypto) ab (AC6, BR-123) — keine Zeile für 4 (Obligationen) oder
# 10 (FX).
DATA_SOURCE_ASSET_CLASS_SEED = [
    ("SEC Form 4 Insider-Trades", [1]),
    ("Finnhub Fundamentals & News", [1, 2, 11]),
    ("Reddit WallStreetBets Sentiment", [1, 7]),
    ("Polymarket Prediction Markets", [1, 7]),
    ("Whale Alert Blockchain", [7]),
    ("Nansen Smart Money Tracking", [7]),
    ("Morningstar ETF & Fonds", [2, 5, 9]),
    ("Leeway Tech ETF & Stocks", [1, 2]),
    ("EPFR Global Fund Flows", [2, 5]),
    ("FRED – Federal Reserve Economic Data", [3, 4, 10]),
    ("Wirtschaftskalender (Finnworlds)", [3, 4, 8, 10]),
    ("CBonds Staatsanleihen & Renten", [4]),
]


def upgrade() -> None:
    """Upgrade schema."""
    data_source = op.create_table(
        "data_source",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("kategorie", sa.String(), nullable=False),
        sa.Column("qualitaet", sa.String(), nullable=True),
        sa.Column("frequenz_sekunden", sa.Integer(), nullable=False),
        sa.Column("kostenmodell", sa.String(), nullable=True),
        sa.Column(
            "kosten_monatlich_chf",
            sa.Numeric(10, 2),
            nullable=True,
            server_default=sa.text("0"),
        ),
        sa.Column("zugangsart", sa.String(), nullable=True),
        sa.Column("rate_limit", sa.String(), nullable=True),
        sa.Column("vault_ref", sa.String(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "kategorie IN ('equity_fundamentals', 'retail_social', 'blockchain_crypto', "
            "'etf_fonds', 'makro_anleihen')",
            name="ck_data_source_kategorie",
        ),
        sa.CheckConstraint(
            "qualitaet IS NULL OR qualitaet IN "
            "('niedrig', 'mittel', 'mittel_hoch', 'hoch', 'sehr_hoch')",
            name="ck_data_source_qualitaet",
        ),
        sa.CheckConstraint(
            "frequenz_sekunden BETWEEN 30 AND 86400",
            name="ck_data_source_frequenz_range",
        ),
    )

    data_source_asset_class = op.create_table(
        "data_source_asset_class",
        sa.Column(
            "data_source_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("data_source.id"),
            primary_key=True,
        ),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_data_source_asset_class_asset_class_id",
        "data_source_asset_class",
        ["asset_class_id"],
    )

    # Idempotenter Seed (data-model.md §11 Punkt 10: "ON CONFLICT DO NOTHING").
    op.execute(
        pg_insert(data_source)
        .values(DATA_SOURCE_SEED)
        .on_conflict_do_nothing(index_elements=["name"])
    )

    # Quelle -> UUID-Lookup fuer die M:N-Seed-Zeilen (Name ist UNIQUE).
    connection = op.get_bind()
    name_to_id = {
        row.name: row.id
        for row in connection.execute(sa.select(data_source.c.id, data_source.c.name))
    }
    mapping_rows = [
        {"data_source_id": name_to_id[source_name], "asset_class_id": asset_class_id}
        for source_name, asset_class_ids in DATA_SOURCE_ASSET_CLASS_SEED
        for asset_class_id in asset_class_ids
    ]
    op.execute(
        pg_insert(data_source_asset_class)
        .values(mapping_rows)
        .on_conflict_do_nothing(index_elements=["data_source_id", "asset_class_id"])
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("data_source_asset_class")
    op.drop_table("data_source")
