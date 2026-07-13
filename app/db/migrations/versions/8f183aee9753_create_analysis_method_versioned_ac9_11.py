"""create analysis_method (versioned, AC9-AC11) + seed alle 11 Klassen x Kategorien

Covers (anlageklassen-config): AC9, AC10, AC11

Quelle: docs/data-model.md §1 `analysis_method_version` / `analysis_method`
(S-018-Präzisierung), BR-102, BR-132, BR-133; docs/specs/anlageklassen-config.md
AC9-AC11, Verträge "Methodentabelle".

- **AC9** (Methodentabelle je Klasse/Kategorie, festes Ranking 1-10):
  `analysis_method`-Tabelle mit `ck_analysis_method_ranking_range`
  (1 <= ranking <= 10, BR-102).
- **AC10** (Versionierung, Methodentabellen-Teil — der Kategoriegewichte-Teil
  ist bereits `386f43ae972d`): eigenständiges `analysis_method_version`-
  Register, analog zu `category_weight_version`, aber **unabhängig**
  versioniert (kein gemeinsamer Versionszähler über beide Konfig-Domänen,
  siehe data-model.md-Notiz). Genau eine `is_current = true`-Version
  (BR-133, partieller UNIQUE-Index).
- **AC11** (quartalsweiser Review-Hinweis, reiner Prozess-Hinweis): Spalte
  `last_reviewed_at`; die Fälligkeitsprüfung selbst ist reine App-Logik
  (`app/db/analysis_method_review.py`, BR-132) — kein DB-Constraint, da sie
  von der aktuellen Zeit abhängt (kein sinnvoller CHECK-Constraint).

**Seed (S-018 Iteration 2 — vollständig, aus der Konzept-Quelle übernommen):**
`ANALYSIS_METHOD_SEED` deckt ALLE 11 Anlageklassen × (bis zu) 5
Analysekategorien ab — 1:1 transkribiert aus der Obsidian-Konzeptnotiz
"KI Investment – Anlageklassen.md" (Nr./Kurzbezeichnung/Ranking je
Methodentabelle; Beschreibung/Nutzen/automation_grade bewusst NICHT
übernommen — kein Bestandteil der AC9-Verträge, kann bei Bedarf in einer
Folge-Story ergänzt werden). Insgesamt 190 Zeilen (Summe je Klasse siehe
`_METHODEN_JE_KLASSE_KATEGORIE`-Dict unten). Iteration 1 dieser Story hatte
hier bewusst nur die 7 Spec-Verträge-Zeilen (Aktien/Fundamental) geseedet
und den Rest als offene Seed-Lücke dokumentiert — dieser Reviewer-Befund
ist mit der Konzept-Quelle als Primärbeleg behoben (kein SPEC-LÜCKE mehr).

**Mapping-Sonderfälle (dokumentiert, keine stille Annahme):**
- **Cash/Geldmarkt (asset_class_id=3) × Technisch:** die Konzept-Quelle
  führt dort explizit KEINE Methodentabelle ("Nicht anwendbar – kein
  relevanter Preistrend") — konsistent mit dem 0%-Kategoriegewicht in der
  Kategoriegewichte-Verträge-Tabelle (`docs/specs/anlageklassen-config.md`
  AC8). `(asset_class_id=3, category_code='technisch')` bleibt daher
  bewusst OHNE Seed-Zeilen — eine leere Methodentabelle ist für diese
  Kombination zulässig (kein Constraint verlangt mindestens eine Zeile je
  (Klasse, Kategorie); AC9 verlangt "je Analysekategorie eine
  Methodentabelle", eine leere Tabelle ist eine Methodentabelle mit null
  Einträgen, kein Widerspruch).
- **Aktive Fonds (asset_class_id=5):** die Konzept-Quelle führt als erste
  Kategorie "Performance / Quantitativ (30%)" (Codes P1-P5) statt
  "Fundamentale Bewertung" — auf den kanonischen `fundamental`-Slot
  gemappt (die 5 kanonischen Analysekategorien aus AC6 gelten unverändert
  für alle Klassen; 30% entspricht exakt dem für Aktive Fonds hinterlegten
  Fundamental-Gewicht in der Kategoriegewichte-Verträge-Tabelle, AC8).

Revision ID: 8f183aee9753
Revises: 386f43ae972d
Create Date: 2026-07-13 09:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "8f183aee9753"
down_revision: Union[str, Sequence[str], None] = "386f43ae972d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CURRENT_VERSION_INDEX = "ux_analysis_method_version_current"
_INITIAL_VERSION_NOTE = "Initial-Version — vollständiger Seed aller 11 Klassen (S-018 Iteration 2)"

# Asset-Klassen-IDs (data-model.md `asset_class`, AC1-Nummerierung).
_AKTIEN = 1
_ETFS = 2
_CASH = 3
_OBLIGATIONEN = 4
_AKTIVE_FONDS = 5
_IMMOBILIEN = 6
_KRYPTO = 7
_ROHSTOFFE = 8
_INFRASTRUKTUR = 9
_FX = 10
_DERIVATE = 11

# Kanonische Analysekategorie-Codes (AC6 / app.db.models.ANALYSIS_CATEGORY_CODES).
_FUNDAMENTAL = "fundamental"
_TECHNISCH = "technisch"
_QUALITATIV = "qualitativ"
_MAKRO = "makro"
_RISIKO_QUANT = "risiko_quant"

# Je (asset_class_id, category_code) -> Liste von (code, kurzbezeichnung, ranking),
# 1:1 aus der Konzept-Quelle "KI Investment – Anlageklassen.md" (Obsidian-Vault,
# vom /flow-Koordinator als Primärquelle benannt, S-018 Iteration 2) transkribiert
# — NICHTS erfunden. Mapping-Sonderfälle siehe Modul-Docstring.
_METHODEN_JE_KLASSE_KATEGORIE: dict[tuple[int, str], list[tuple[str, str, int]]] = {
    (_AKTIEN, _FUNDAMENTAL): [
        ("F1", "DCF / FCFE", 9),
        ("F2", "ROE / ROIC", 9),
        ("F3", "EV/EBITDA", 8),
        ("F4", "KBV (P/B)", 6),
        ("F5", "KGV (P/E)", 7),
        ("F6", "Verschuldungsgrad", 8),
        ("F7", "Earnings Revisions", 7),
    ],
    (_AKTIEN, _TECHNISCH): [
        ("T1", "Trend / Gleitende Durchschnitte", 8),
        ("T2", "MACD", 7),
        ("T3", "Volumen", 7),
        ("T4", "Unterstützung/Widerstand", 7),
        ("T5", "Sentiment", 6),
    ],
    (_AKTIEN, _QUALITATIV): [
        ("Q1", "Economic Moat", 9),
        ("Q2", "Management-Qualität", 8),
        ("Q3", "ESG (materialitätsbasiert)", 7),
        ("Q4", "Branchen-/Geschäftsmodell", 7),
    ],
    (_AKTIEN, _MAKRO): [
        ("M1", "Zinsumfeld", 8),
        ("M2", "Konjunkturzyklus", 7),
        ("M3", "Geopolitik", 6),
    ],
    (_AKTIEN, _RISIKO_QUANT): [
        ("R1", "Volatilität", 8),
        ("R2", "Beta", 8),
        ("R3", "Sharpe Ratio", 8),
        ("R4", "VaR", 7),
        ("R5", "Max Drawdown", 8),
    ],
    (_ETFS, _FUNDAMENTAL): [
        ("F1", "Tracking Difference", 9),
        ("F2", "Total Cost of Ownership", 9),
        ("F3", "NAV-Prämie/Discount", 8),
        ("F4", "TER", 7),
    ],
    (_ETFS, _TECHNISCH): [
        ("T1", "Trend", 6),
        ("T2", "Sentiment/Flows", 6),
    ],
    (_ETFS, _QUALITATIV): [
        ("Q1", "Handelsliquidität (ADV)", 9),
        ("Q2", "Bid-Ask-Spread", 8),
        ("Q3", "Domizil/Steuer (UCITS)", 8),
        ("Q4", "Index-Methodik", 8),
        ("Q5", "Wertpapierleihe-Erträge", 6),
    ],
    (_ETFS, _MAKRO): [
        ("M1", "Asset-Klassen-Umfeld", 7),
        ("M2", "Zins-/Währungsumfeld", 6),
    ],
    (_ETFS, _RISIKO_QUANT): [
        ("R1", "Liquiditätsrisiko", 8),
        ("R2", "Volatilität", 7),
        ("R3", "Tracking Error", 7),
    ],
    (_CASH, _FUNDAMENTAL): [
        ("F1", "Geldmarktzinsen", 9),
        ("F2", "T-Bill-Rendite", 9),
        ("F3", "Risikofreier Zinssatz", 8),
    ],
    # (_CASH, _TECHNISCH) bewusst NICHT vorhanden — siehe Mapping-Notiz im
    # Modul-Docstring (0%-Gewicht, Quelle nennt "nicht anwendbar").
    (_CASH, _QUALITATIV): [
        ("Q1", "Emittenten-Bonität", 9),
        ("Q2", "Fonds-Anbieter", 7),
    ],
    (_CASH, _MAKRO): [
        ("M1", "Zentralbankpolitik", 9),
        ("M2", "Inflation vs. Nominalzins", 9),
    ],
    (_CASH, _RISIKO_QUANT): [
        ("R1", "Liquidität", 9),
        ("R2", "Gegenparteirisiko", 7),
    ],
    (_OBLIGATIONEN, _FUNDAMENTAL): [
        ("F1", "Effektive Duration", 9),
        ("F2", "OAS", 9),
        ("F3", "Yield to Worst", 8),
        ("F4", "Convexity", 8),
        ("F5", "Key-Rate-Duration", 7),
        ("F6", "Credit Spread", 8),
    ],
    (_OBLIGATIONEN, _TECHNISCH): [
        ("T1", "Spread-Trend", 7),
        ("T2", "Kurstrend", 5),
        ("T3", "Sentiment/Flows", 6),
    ],
    (_OBLIGATIONEN, _QUALITATIV): [
        ("Q1", "Emittenten-Rating", 8),
        ("Q2", "Covenant-Qualität", 7),
        ("Q3", "ESG (Emittent)", 6),
    ],
    (_OBLIGATIONEN, _MAKRO): [
        ("M1", "Zinsstrukturkurve", 9),
        ("M2", "Inflationserwartungen", 9),
        ("M3", "Geldpolitik", 8),
    ],
    (_OBLIGATIONEN, _RISIKO_QUANT): [
        ("R1", "Zinsrisiko", 9),
        ("R2", "Kreditrisiko", 8),
        ("R3", "Liquiditätsrisiko", 7),
    ],
    # Quelle: "Performance / Quantitativ (30%)" -- gemappt auf den
    # kanonischen `fundamental`-Slot (siehe Modul-Docstring).
    (_AKTIVE_FONDS, _FUNDAMENTAL): [
        ("P1", "Alpha", 9),
        ("P2", "Information Ratio", 9),
        ("P3", "Active Share", 9),
        ("P4", "Downside/Upside Capture", 8),
        ("P5", "Tracking Error", 7),
    ],
    (_AKTIVE_FONDS, _TECHNISCH): [
        ("T1", "NAV-Trend", 5),
    ],
    (_AKTIVE_FONDS, _QUALITATIV): [
        ("Q1", "People (Manager)", 9),
        ("Q2", "Process", 9),
        ("Q3", "Parent", 8),
        ("Q4", "Style Drift", 8),
        ("Q5", "Asset-Bloat", 7),
        ("Q6", "ESG-Integration", 6),
    ],
    (_AKTIVE_FONDS, _MAKRO): [
        ("M1", "Marktumfeld der Anlageklasse", 7),
    ],
    (_AKTIVE_FONDS, _RISIKO_QUANT): [
        ("R1", "Max Drawdown", 9),
        ("R2", "Sortino Ratio", 8),
        ("R3", "Calmar Ratio", 8),
        ("R4", "Volatilität", 7),
    ],
    (_IMMOBILIEN, _FUNDAMENTAL): [
        ("F1", "AFFO [REIT]", 9),
        ("F2", "Cap Rate [direkt+REIT]", 9),
        ("F3", "NOI [direkt+REIT]", 8),
        ("F4", "P/FFO & P/AFFO [REIT]", 8),
        ("F5", "FFO [REIT]", 7),
        ("F6", "Loan-to-Value", 8),
        ("F7", "WALT", 7),
    ],
    (_IMMOBILIEN, _TECHNISCH): [
        ("T1", "Kurstrend [REIT]", 5),
    ],
    (_IMMOBILIEN, _QUALITATIV): [
        ("Q1", "Occupancy Rate", 9),
        ("Q2", "Lagequalität", 8),
        ("Q3", "Mieterbonität", 7),
        ("Q4", "ESG (Gebäude)", 7),
    ],
    (_IMMOBILIEN, _MAKRO): [
        ("M1", "Zinsumfeld", 9),
        ("M2", "Konjunktur/Beschäftigung", 7),
        ("M3", "Demografie/Regulierung", 6),
    ],
    (_IMMOBILIEN, _RISIKO_QUANT): [
        ("R1", "Zinsrisiko", 9),
        ("R2", "Leverage", 8),
        ("R3", "Liquiditätsrisiko", 8),
    ],
    (_KRYPTO, _FUNDAMENTAL): [
        ("F1", "MVRV-Ratio", 8),
        ("F2", "SOPR", 7),
        ("F3", "Realized Cap", 7),
        ("F4", "TVL (DeFi)", 7),
        ("F5", "Exchange In-/Outflows", 7),
        ("F6", "Token Vesting/Emission", 7),
    ],
    (_KRYPTO, _TECHNISCH): [
        ("T1", "Trend / Moving Averages", 8),
        ("T2", "Funding Rates", 8),
        ("T3", "Developer-Aktivität", 7),
        ("T4", "Sentiment", 7),
        ("T5", "Volumen", 6),
    ],
    (_KRYPTO, _QUALITATIV): [
        ("Q1", "Tokenomics / Use Case", 8),
        ("Q2", "Team / Community", 7),
        ("Q3", "Sicherheit / Audits", 7),
    ],
    (_KRYPTO, _MAKRO): [
        ("M1", "MiCA-Regulierung", 8),
        ("M2", "Liquiditätszyklen", 8),
        ("M3", "Geldpolitik / USD", 7),
    ],
    (_KRYPTO, _RISIKO_QUANT): [
        ("R1", "Volatilität", 9),
        ("R2", "Liquiditätsrisiko", 8),
        ("R3", "Korrelation zu BTC", 8),
        ("R4", "Max Drawdown", 8),
    ],
    (_ROHSTOFFE, _FUNDAMENTAL): [
        ("F1", "Contango/Backwardation", 9),
        ("F2", "Roll-Yield", 9),
        ("F3", "Futures-Kurvenstruktur", 8),
        ("F4", "Convenience Yield", 7),
        ("F5", "Cost of Carry", 7),
        ("F6", "Angebot/Nachfrage-Bilanz", 8),
    ],
    (_ROHSTOFFE, _TECHNISCH): [
        ("T1", "Trend", 8),
        ("T2", "COT-Positionierung", 7),
        ("T3", "Sentiment", 6),
    ],
    (_ROHSTOFFE, _QUALITATIV): [
        ("Q1", "Produktqualität / Lagerung", 5),
    ],
    (_ROHSTOFFE, _MAKRO): [
        ("M1", "Realzinsen / TIPS (Gold)", 9),
        ("M2", "Zentralbankkäufe (Gold)", 8),
        ("M3", "Geopolitik", 8),
        ("M4", "USD / Konjunktur", 7),
    ],
    (_ROHSTOFFE, _RISIKO_QUANT): [
        ("R1", "Roll-Risiko", 8),
        ("R2", "Volatilität", 8),
        ("R3", "Währungsrisiko", 7),
    ],
    (_INFRASTRUKTUR, _FUNDAMENTAL): [
        ("F1", "DCF / RAB-Methode", 9),
        ("F2", "IRR", 9),
        ("F3", "DSCR", 8),
        ("F4", "Konzessionslaufzeit", 8),
        ("F5", "Inflationsindexierung", 8),
    ],
    (_INFRASTRUKTUR, _TECHNISCH): [
        ("T1", "Kurstrend [gelistet]", 5),
    ],
    (_INFRASTRUKTUR, _QUALITATIV): [
        ("Q1", "Greenfield vs. Brownfield", 8),
        ("Q2", "Volumenrisiko", 8),
        ("Q3", "Gegenpartei / Konzessionsgeber", 7),
        ("Q4", "ESG", 7),
    ],
    (_INFRASTRUKTUR, _MAKRO): [
        ("M1", "Zinsumfeld", 8),
        ("M2", "Inflation", 8),
        ("M3", "Geopolitik / Politik", 7),
    ],
    (_INFRASTRUKTUR, _RISIKO_QUANT): [
        ("R1", "Regulierungsrisiko", 9),
        ("R2", "Politisches Risiko", 8),
        ("R3", "Liquiditätsrisiko", 8),
    ],
    (_FX, _FUNDAMENTAL): [
        ("F1", "Carry / Realzinsdifferenz", 9),
        ("F2", "Zinsparität (gedeckt/ungedeckt)", 8),
        ("F3", "Terms of Trade", 7),
        ("F4", "FX-Reserven", 7),
    ],
    (_FX, _TECHNISCH): [
        ("T1", "Trend", 8),
        ("T2", "Risk-Reversals", 8),
        ("T3", "COT-Positionierung", 7),
        ("T4", "Optionsvolatilität", 7),
    ],
    (_FX, _QUALITATIV): [
        ("Q1", "Institutionelle Qualität", 5),
    ],
    (_FX, _MAKRO): [
        ("M1", "Geldpolitik / Zinspfad", 9),
        ("M2", "Inflation", 8),
        ("M3", "Leistungsbilanz", 7),
        ("M4", "Geopolitik", 7),
    ],
    (_FX, _RISIKO_QUANT): [
        ("R1", "Carry-Crash-Risiko", 9),
        ("R2", "Volatilität", 8),
    ],
    (_DERIVATE, _FUNDAMENTAL): [
        ("F1", "Basiswert-Analyse", 9),
        ("F2", "Innerer Wert", 7),
        ("F3", "Fair Value (Futures)", 7),
    ],
    (_DERIVATE, _TECHNISCH): [
        ("T1", "Implizite Volatilität (IV)", 9),
        ("T2", "IV vs. Hist. Volatilität", 9),
        ("T3", "Open Interest", 8),
        ("T4", "Trend des Underlyings", 8),
        ("T5", "Sentiment / Put-Call-Ratio", 7),
    ],
    (_DERIVATE, _QUALITATIV): [
        ("Q1", "Kontraktspezifikationen", 7),
        ("Q2", "Marktliquidität", 7),
    ],
    (_DERIVATE, _MAKRO): [
        ("M1", "Zinsumfeld", 7),
        ("M2", "Volatilitätsregime", 8),
        ("M3", "Geopolitik / Events", 7),
    ],
    (_DERIVATE, _RISIKO_QUANT): [
        ("R1", "Delta", 9),
        ("R2", "Gamma", 8),
        ("R3", "Theta", 9),
        ("R4", "Vega", 8),
        ("R5", "Margin-Anforderungen (Futures)", 8),
        ("R6", "Max Verlust", 9),
    ],
}


def _baue_analysis_method_seed() -> list[dict]:
    """Flacht `_METHODEN_JE_KLASSE_KATEGORIE` zu Insert-Zeilen ab und
    validiert JEDES Ranking gegen 1-10 (AC9) — ein Quell-Wert ausserhalb
    dieses Bereichs ist ein Abbruchgrund (Migration schlägt beim Laden
    fehl), KEIN stiller Clamp."""
    zeilen: list[dict] = []
    for (asset_class_id, category_code), methoden in _METHODEN_JE_KLASSE_KATEGORIE.items():
        for code, kurzbezeichnung, ranking in methoden:
            if not (1 <= ranking <= 10):
                raise ValueError(
                    f"analysis_method-Seed: Ranking {ranking} fuer "
                    f"asset_class_id={asset_class_id} code={code} ausserhalb 1-10 (AC9) "
                    "-- Quelle pruefen, kein automatisches Clamping."
                )
            zeilen.append(
                {
                    "asset_class_id": asset_class_id,
                    "category_code": category_code,
                    "code": code,
                    "kurzbezeichnung": kurzbezeichnung,
                    "ranking": ranking,
                }
            )
    return zeilen


ANALYSIS_METHOD_SEED = _baue_analysis_method_seed()


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "analysis_method_version",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(), nullable=True),
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX {_CURRENT_VERSION_INDEX}
        ON analysis_method_version (is_current)
        WHERE is_current
        """
    )
    op.execute(f"INSERT INTO analysis_method_version (note) VALUES ('{_INITIAL_VERSION_NOTE}')")

    analysis_method = op.create_table(
        "analysis_method",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "asset_class_id", sa.SmallInteger(), sa.ForeignKey("asset_class.id"), nullable=False
        ),
        sa.Column(
            "category_code", sa.String(), sa.ForeignKey("analysis_category.code"), nullable=False
        ),
        sa.Column(
            "config_version_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analysis_method_version.id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("kurzbezeichnung", sa.String(), nullable=False),
        sa.Column("beschreibung", sa.String(), nullable=True),
        sa.Column("nutzen", sa.String(), nullable=True),
        sa.Column("ranking", sa.SmallInteger(), nullable=False),
        sa.Column("automation_grade", sa.String(), nullable=True),
        sa.Column(
            "last_reviewed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "ranking >= 1 AND ranking <= 10", name="ck_analysis_method_ranking_range"
        ),
        sa.CheckConstraint(
            "automation_grade IS NULL OR automation_grade IN ('AUTO', 'TEIL', 'BUILD')",
            name="ck_analysis_method_automation_grade",
        ),
        sa.UniqueConstraint(
            "asset_class_id", "code", "config_version_id", name="uq_analysis_method_code_version"
        ),
    )
    op.create_index(
        "ix_analysis_method_asset_class_category_version",
        "analysis_method",
        ["asset_class_id", "category_code", "config_version_id"],
    )
    op.create_index(
        "ix_analysis_method_config_version_id", "analysis_method", ["config_version_id"]
    )

    # Seed an die (einzige) initiale Version binden — idempotenter Insert
    # (data-model.md §11 Punkt 10 "ON CONFLICT DO NOTHING") ueber die
    # UNIQUE-Constraint (asset_class_id, code, config_version_id). Die
    # initiale Version-ID wird vorab konkret abgefragt (statt einer
    # verschachtelten SELECT-Subquery je Zeile im Bulk-Insert) — robuster
    # und leichter nachvollziehbar.
    bind = op.get_bind()
    initial_version_id = bind.execute(
        sa.text("SELECT id FROM analysis_method_version WHERE is_current LIMIT 1")
    ).scalar_one()
    op.execute(
        pg_insert(analysis_method)
        .values([{**row, "config_version_id": initial_version_id} for row in ANALYSIS_METHOD_SEED])
        .on_conflict_do_nothing(index_elements=["asset_class_id", "code", "config_version_id"])
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_analysis_method_config_version_id", table_name="analysis_method")
    op.drop_index("ix_analysis_method_asset_class_category_version", table_name="analysis_method")
    op.drop_table("analysis_method")
    op.execute(f"DROP INDEX IF EXISTS {_CURRENT_VERSION_INDEX}")
    op.drop_table("analysis_method_version")
