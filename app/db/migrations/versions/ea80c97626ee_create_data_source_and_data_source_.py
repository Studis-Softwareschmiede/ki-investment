"""create data_source and data_source_asset_class tables with seed

Covers (dateneingang): AC5, AC6, AC13

Quelle: docs/data-model.md §1 `data_source` + `data_source_asset_class`
(BR-123, BR-126), Verträge-Tabelle "Quellen-Registry-Eintrag" in
docs/specs/dateneingang.md, sowie die Konzept-Detailtabelle
"KI Investment – Datenquellen.md" (C-009, Analyse-Session 29.06.2026) für die
konkreten 12 Quellen-Namen/-Kategorien/-Anlageklassen — die Spec selbst nennt
nur die 5 Kategorien-Namen und explizit 5 der 12 Quellen (SEC Form 4, Reddit,
Polymarket, FRED, Wirtschaftskalender); die übrigen 7 Namen (Finnhub, Whale
Alert, Nansen, Morningstar, Leeway Tech, EPFR, CBonds) sind Spec-Zitat
("Whale Alert, Nansen, Finnhub, u. a." — Abhängigkeiten-Abschnitt) plus
Konzept-Quelle, keine coder-eigene Erfindung.

AC5 (12 Quellen, 5 Kategorien, Anlageklassen-Zuordnung 1-11): jede Zeile in
DATA_SOURCE_SEED traegt eine `kategorie` aus den 5 CHECK-Werten; die
Zuordnung zu Anlageklassen steht in DATA_SOURCE_ASSET_CLASS_SEED (M:N).

AC6 (Reddit nur retail-getriebene Klassen 1/7, BR-123): die
Anlageklassen-Zeilen fuer "Reddit WallStreetBets Sentiment" sind auf genau
{1, 7} beschraenkt (siehe REDDIT_ASSET_CLASS_IDS unten) — Obligationen (4)
und FX (10) erscheinen dort nicht. BR-123 ist laut data-model.md §10 als
"App (Quellen-Matching)"-Regel eingestuft (nicht DB-Trigger) — hier bereits
strukturell durch die Seed-Daten erfuellt; die Datenquellen-Abfrage-Matching-
Logik selbst (AC7/AC8) ist nicht Teil dieser Story (S-006, implements nur
AC5/AC6/AC13).

AC13 (MVP nur Freiquellen aktiv): `aktiv=True` ist ausschliesslich auf die 5
in AC13 namentlich genannten Quellen gesetzt (SEC Form 4, Reddit, Polymarket,
FRED, Wirtschaftskalender); alle uebrigen 7 (kostenpflichtig/institutionell)
sind registriert, aber `aktiv=False`.

`data_source.id` ist deterministisch aus dem Quellen-Namen abgeleitet
(`uuid.uuid5`), damit ein wiederholtes `alembic upgrade head` denselben
Datensatz trifft (idempotenter Seed via ON CONFLICT DO NOTHING analog
S-003/S-004, `dba`-Lesson).

Revision ID: ea80c97626ee
Revises: 2da446925bbc
Create Date: 2026-07-12 15:04:56.250199

"""

import uuid
from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "ea80c97626ee"
down_revision: Union[str, Sequence[str], None] = "2da446925bbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deterministischer Namensraum fuer die Quellen-UUIDs (idempotenter Seed).
_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ki-investment.dateneingang.data_source")


def _source_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(_UUID_NAMESPACE, slug)


# 12 Datenquellen in 5 Kategorien (AC5), 1:1 aus der Konzept-Detailtabelle
# "KI Investment – Datenquellen.md" (C-009). `aktiv` folgt AC13 (nur die 5
# kostenlosen MVP-Quellen). Frequenz-Werte fuer die in AC4 explizit
# genannten Quellen (Polymarket/Whale Alert/Nansen 30-60s, Reddit 15-30min,
# SEC 2h, FRED taeglich) sind Mittelwerte der jeweiligen Spec-Range;
# Werte ohne AC4-Vorgabe uebernehmen die Konzept-Detailtabelle (provisorisch,
# per AC4 ohne Codeaenderung ueberschreibbar).
DATA_SOURCE_SEED = [
    # Kategorie A: Equity Insider & Fundamentals
    {
        "slug": "sec-form4-insider-trades",
        "name": "SEC Form 4 Insider-Trades",
        "kategorie": "equity_fundamentals",
        "qualitaet": "hoch",
        "frequenz_sekunden": 7200,  # AC4: SEC 2h
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST API, kein Key noetig (data.sec.gov)",
        "rate_limit": "10 req/sec",
        "aktiv": True,
    },
    {
        "slug": "finnhub-fundamentals-news",
        "name": "Finnhub Fundamentals & News",
        "kategorie": "equity_fundamentals",
        "qualitaet": "hoch",
        "frequenz_sekunden": 1350,  # 15-30 Min (Fundamentals), Mittelwert
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": Decimal("45.00"),
        "zugangsart": "REST API + WebSocket, API-Key noetig",
        "rate_limit": None,
        "aktiv": False,
    },
    # Kategorie B: Retail Sentiment & Social
    {
        "slug": "reddit-wallstreetbets-sentiment",
        "name": "Reddit WallStreetBets Sentiment",
        "kategorie": "retail_social",
        "qualitaet": "mittel",
        "frequenz_sekunden": 1350,  # AC4: Reddit 15-30 min, Mittelwert
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST API via PRAW, OAuth noetig",
        "rate_limit": "100 req/min",
        "aktiv": True,
    },
    # Kategorie C: Blockchain & Crypto Smart Money
    {
        "slug": "polymarket-prediction-markets",
        "name": "Polymarket Prediction Markets",
        "kategorie": "blockchain_crypto",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 45,  # AC4: Polymarket/Whale/Nansen 30-60s, Mittelwert
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST API + WebSocket unlimitiert",
        "rate_limit": "60-100 req/min",
        "aktiv": True,
    },
    {
        "slug": "whale-alert-blockchain",
        "name": "Whale Alert Blockchain",
        "kategorie": "blockchain_crypto",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 45,  # AC4: Polymarket/Whale/Nansen 30-60s, Mittelwert
        "kostenmodell": "pro",
        "kosten_monatlich_chf": Decimal("28.00"),
        "zugangsart": "REST API + WebSocket",
        "rate_limit": "1000 calls/min",
        "aktiv": False,
    },
    {
        "slug": "nansen-smart-money-tracking",
        "name": "Nansen Smart Money Tracking",
        "kategorie": "blockchain_crypto",
        "qualitaet": "hoch",
        "frequenz_sekunden": 45,  # AC4: Polymarket/Whale/Nansen 30-60s, Mittelwert
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": Decimal("46.00"),
        "zugangsart": "REST API, API-Key noetig",
        "rate_limit": "20 req/sec, 500 req/min",
        "aktiv": False,
    },
    # Kategorie D: ETFs & Fonds
    {
        "slug": "morningstar-etf-fonds",
        "name": "Morningstar ETF & Fonds",
        "kategorie": "etf_fonds",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 86400,  # taeglich (Flows)
        "kostenmodell": "institutionell",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "API via Morningstar Direct, Token-basiert",
        "rate_limit": None,
        "aktiv": False,
    },
    {
        "slug": "leeway-tech-etf-stocks",
        "name": "Leeway Tech ETF & Stocks",
        "kategorie": "etf_fonds",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 86400,  # taeglich (Fundamentals)
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": Decimal("50.00"),
        "zugangsart": "REST API, API-Token im Account-Bereich",
        "rate_limit": "50 req/day (Free)",
        "aktiv": False,
    },
    {
        "slug": "epfr-global-fund-flows",
        "name": "EPFR Global Fund Flows",
        "kategorie": "etf_fonds",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 86400,  # taeglich bis woechentlich, Obergrenze
        "kostenmodell": "institutionell",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "Data Feed + API via Massive",
        "rate_limit": None,
        "aktiv": False,
    },
    # Kategorie E: Makroökonomie & Anleihen
    {
        "slug": "fred-federal-reserve-economic-data",
        "name": "FRED - Federal Reserve Economic Data",
        "kategorie": "makro_anleihen",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 86400,  # AC4: FRED taeglich
        "kostenmodell": "frei",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST API, kostenloser API-Key noetig (fredaccount.org)",
        "rate_limit": None,
        "aktiv": True,
    },
    {
        "slug": "wirtschaftskalender-finnworlds",
        "name": "Wirtschaftskalender (Finnworlds)",
        "kategorie": "makro_anleihen",
        "qualitaet": "sehr_hoch",
        "frequenz_sekunden": 86400,  # taeglich (anstehende Releases)
        "kostenmodell": "frei",  # AC13-Freiquelle, Basis-Tier kostenlos genutzt
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST API, JSON, Kalender-Feed",
        "rate_limit": None,
        "aktiv": True,
    },
    {
        "slug": "cbonds-staatsanleihen-renten",
        "name": "CBonds Staatsanleihen & Renten",
        "kategorie": "makro_anleihen",
        "qualitaet": "mittel_hoch",
        "frequenz_sekunden": 86400,  # taeglich (Analysen)
        "kostenmodell": "free_tier",
        "kosten_monatlich_chf": Decimal("0"),
        "zugangsart": "REST API, Daten-Feeds, CSV/JSON",
        "rate_limit": None,
        "aktiv": False,
    },
]

# Anlageklassen-Zuordnung je Quelle (AC5-Vertrag "anlageklassen: [1..11]"),
# 1:1 aus der Konzept-Detailtabelle (Kategorie-Tabellen + "Abdeckung je
# Anlageklasse"-Kreuztabelle, beide deckungsgleich).
DATA_SOURCE_ASSET_CLASS_IDS = {
    "sec-form4-insider-trades": [1],
    "finnhub-fundamentals-news": [1, 2, 11],
    # AC6/BR-123: Reddit ausschliesslich fuer die retail-getriebenen Klassen
    # Aktien (1) und Krypto (7) — bewusst KEINE weiteren IDs (insbesondere
    # nicht Obligationen=4 oder FX=10).
    "reddit-wallstreetbets-sentiment": [1, 7],
    "polymarket-prediction-markets": [1, 7],
    "whale-alert-blockchain": [7],
    "nansen-smart-money-tracking": [7],
    "morningstar-etf-fonds": [2, 5, 9],
    "leeway-tech-etf-stocks": [1, 2],
    "epfr-global-fund-flows": [2, 5],
    "fred-federal-reserve-economic-data": [3, 4, 10],
    # Nicht-Ziele (dateneingang.md): Rohstoffe (8) sind "noch offen und nicht
    # Teil des MVP" — die Konzept-Detailtabelle listet Klasse 8 hier zwar,
    # die Seed-Daten duerfen diese vertagte Scope-Entscheidung aber nicht
    # vorwegnehmen; daher bewusst OHNE 8.
    "wirtschaftskalender-finnworlds": [3, 4, 10],
    "cbonds-staatsanleihen-renten": [4],
}


def upgrade() -> None:
    """Upgrade schema."""
    data_source = op.create_table(
        "data_source",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("kategorie", sa.String(), nullable=True),
        sa.Column("qualitaet", sa.String(), nullable=True),
        sa.Column("frequenz_sekunden", sa.Integer(), nullable=False),
        sa.Column("kostenmodell", sa.String(), nullable=True),
        sa.Column(
            "kosten_monatlich_chf", sa.Numeric(10, 2), nullable=True, server_default=sa.text("0")
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
            "qualitaet IN ('niedrig', 'mittel', 'mittel_hoch', 'hoch', 'sehr_hoch')",
            name="ck_data_source_qualitaet",
        ),
        sa.CheckConstraint(
            "frequenz_sekunden BETWEEN 30 AND 86400",
            name="ck_data_source_frequenz_sekunden_range",
        ),
    )

    data_source_asset_class = op.create_table(
        "data_source_asset_class",
        sa.Column(
            "data_source_id",
            UUID(as_uuid=True),
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
    # data-model.md §8: (asset_class_id)-Index fuer "Quellen je Klasse"
    # (Datenquellen-Abfrage-Matching) — der Composite-PK
    # (data_source_id, asset_class_id) deckt einen reinen
    # asset_class_id-Filter nicht ab (nicht fuehrender Spalten-Teil).
    op.create_index(
        "ix_data_source_asset_class_asset_class_id",
        "data_source_asset_class",
        ["asset_class_id"],
    )

    seed_rows = [{**row, "id": _source_id(row["slug"])} for row in DATA_SOURCE_SEED]
    for row in seed_rows:
        row.pop("slug")

    # Idempotenter Seed (data-model.md §11 Punkt 10: "ON CONFLICT DO NOTHING").
    op.execute(
        pg_insert(data_source).values(seed_rows).on_conflict_do_nothing(index_elements=["id"])
    )

    mapping_rows = [
        {"data_source_id": _source_id(slug), "asset_class_id": asset_class_id}
        for slug, asset_class_ids in DATA_SOURCE_ASSET_CLASS_IDS.items()
        for asset_class_id in asset_class_ids
    ]
    op.execute(
        pg_insert(data_source_asset_class)
        .values(mapping_rows)
        .on_conflict_do_nothing(index_elements=["data_source_id", "asset_class_id"])
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_data_source_asset_class_asset_class_id", table_name="data_source_asset_class")
    op.drop_table("data_source_asset_class")
    op.drop_table("data_source")
