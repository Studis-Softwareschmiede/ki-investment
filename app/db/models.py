"""ORM-Modelle — 1:1 aus docs/data-model.md (`dba`-Detailkonzept, bindend).

Diese Datei bildet bislang nur die von der laufenden Story benoetigten Tabellen ab;
weitere Entitaeten aus data-model.md kommen ueber Folge-Stories dazu (P6/ADR-008:
Anlageklassen sind Konfiguration, keine Code-Grenze).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# data-model.md §1 `asset_class`: CHECK prio_stufe ∈ {MVP, Stufe2, Stufe3}
PRIO_STUFE_VALUES = ("MVP", "Stufe2", "Stufe3")

# data-model.md §1 `analysis_category`: CHECK code ∈ {...} (5 Analysekategorien, C-007)
ANALYSIS_CATEGORY_CODES = ("fundamental", "technisch", "qualitativ", "makro", "risiko_quant")

# data-model.md §1 `data_source`: CHECK kategorie ∈ {...} (5 Kategorien, C-009/AC5)
DATA_SOURCE_KATEGORIE_VALUES = (
    "equity_fundamentals",
    "retail_social",
    "blockchain_crypto",
    "etf_fonds",
    "makro_anleihen",
)

# data-model.md §1 `data_source`: CHECK qualitaet ∈ {...}
DATA_SOURCE_QUALITAET_VALUES = ("niedrig", "mittel", "mittel_hoch", "hoch", "sehr_hoch")

# data-model.md §1 `data_source`: frequenz_sekunden-Bereich (Socket-Scheduling)
DATA_SOURCE_FREQUENZ_MIN_SECONDS = 30
DATA_SOURCE_FREQUENZ_MAX_SECONDS = 86400


class AssetClass(Base):
    """Anlageklasse — Stammdaten + Feature-Toggle (data-model.md `asset_class`, BR-100).

    `aktiv` ist der persistente Toggle-Zustand auf Systemeinstellungs-Ebene (AC12):
    eine globale, nicht user-/positions-gebundene Konfigurationszeile je Klasse.
    """

    __tablename__ = "asset_class"
    __table_args__ = (
        CheckConstraint("id BETWEEN 1 AND 11", name="ck_asset_class_id_range"),
        CheckConstraint(
            "prio_stufe IN ('MVP', 'Stufe2', 'Stufe3')",
            name="ck_asset_class_prio_stufe",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    prio_stufe: Mapped[str] = mapped_column(String, nullable=False)
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retail_driven: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"AssetClass(id={self.id!r}, name={self.name!r}, aktiv={self.aktiv!r})"


class AnalysisCategory(Base):
    """Analysekategorie — 5 fixe Dimensionen der Bewertung (data-model.md
    `analysis_category`, C-007). Stammdaten-Voraussetzung für `category_weight`
    (FK `category_code`) und die spätere Methodentabelle (S-018, ausserhalb
    dieser Story).
    """

    __tablename__ = "analysis_category"
    __table_args__ = (
        CheckConstraint(
            "code IN ('fundamental', 'technisch', 'qualitativ', 'makro', 'risiko_quant')",
            name="ck_analysis_category_code",
        ),
    )

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    ist_risiko: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"AnalysisCategory(code={self.code!r}, name={self.name!r})"


class CategoryWeight(Base):
    """Kategoriegewicht je Anlageklasse (data-model.md `category_weight`,
    BR-101). Die fünf Gewichte einer Klasse müssen sich auf exakt 100 %
    summieren (AC6/AC7) — DB-seitig durch einen deferred Constraint-Trigger
    durchgesetzt (siehe Migration `2da446925bbc_...py`), App-seitig durch
    `app.db.category_weights.validate_category_weights`.

    `config_version` ist eine Vorbereitung auf die versionierten
    Konfigurationsdaten aus AC10 (voller Versionierungs-Workflow folgt in
    einer eigenen Folge-Story) — Default 1, noch ohne History-Tracking.
    """

    __tablename__ = "category_weight"
    __table_args__ = (
        CheckConstraint("weight_pct >= 0 AND weight_pct <= 100", name="ck_category_weight_range"),
    )

    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), primary_key=True
    )
    category_code: Mapped[str] = mapped_column(
        String, ForeignKey("analysis_category.code"), primary_key=True
    )
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    config_version: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=1, server_default=sa.text("1")
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"CategoryWeight(asset_class_id={self.asset_class_id!r}, "
            f"category_code={self.category_code!r}, weight_pct={self.weight_pct!r})"
        )


class DataSource(Base):
    """Datenquellen-Registry (data-model.md `data_source`, C-009) — 12 Quellen in
    5 Kategorien (AC5). `aktiv` ist der MVP-Kostentoggel (AC13): nur die 5
    kostenlosen Quellen (SEC Form 4, Reddit, Polymarket, FRED,
    Wirtschaftskalender) sind per Seed aktiv; kostenpflichtige/institutionelle
    Quellen sind registriert, aber inaktiv und lösen ohne Aktivierung keinen
    Abruf aus (siehe Migration
    `ea80c97626ee_create_data_source_and_data_source_.py`).

    `vault_ref` ist ein reiner Zeiger auf ein Secret (kein Klartext-Credential,
    → BR-126) — die tatsächliche Auth-Kapselung je Adapter ist Sache der
    Socket-Adapter-Basis (S-005), nicht dieser Registry.
    """

    __tablename__ = "data_source"
    __table_args__ = (
        CheckConstraint(
            "kategorie IN ('equity_fundamentals', 'retail_social', 'blockchain_crypto', "
            "'etf_fonds', 'makro_anleihen')",
            name="ck_data_source_kategorie",
        ),
        CheckConstraint(
            "qualitaet IN ('niedrig', 'mittel', 'mittel_hoch', 'hoch', 'sehr_hoch')",
            name="ck_data_source_qualitaet",
        ),
        CheckConstraint(
            f"frequenz_sekunden BETWEEN {DATA_SOURCE_FREQUENZ_MIN_SECONDS} "
            f"AND {DATA_SOURCE_FREQUENZ_MAX_SECONDS}",
            name="ck_data_source_frequenz_sekunden_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    kategorie: Mapped[str | None] = mapped_column(String, nullable=True)
    qualitaet: Mapped[str | None] = mapped_column(String, nullable=True)
    frequenz_sekunden: Mapped[int] = mapped_column(Integer, nullable=False)
    kostenmodell: Mapped[str | None] = mapped_column(String, nullable=True)
    kosten_monatlich_chf: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True, default=Decimal("0"), server_default=sa.text("0")
    )
    zugangsart: Mapped[str | None] = mapped_column(String, nullable=True)
    rate_limit: Mapped[str | None] = mapped_column(String, nullable=True)
    vault_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    aktiv: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"DataSource(name={self.name!r}, kategorie={self.kategorie!r}, aktiv={self.aktiv!r})"


class DataSourceAssetClass(Base):
    """Quelle ↔ Anlageklasse (M:N, data-model.md `data_source_asset_class`,
    C-009 Abdeckung). Ordnet jeder Quelle die Anlageklassen zu, für die sie
    verwertbare Signale liefert (AC5); die Reddit-Zeilen dieser Tabelle sind
    per Seed strukturell auf die retail-getriebenen Klassen 1/7 beschränkt
    (AC6, BR-123 — Enforcement-Layer laut data-model.md §10 „App
    (Quellen-Matching)", hier bereits durch die Seed-Daten selbst erfüllt).

    `ix_data_source_asset_class_asset_class_id` (data-model.md §8) deckt den
    Filter „Quellen je Klasse" (Datenquellen-Abfrage-Matching) ab — der
    Composite-PK (data_source_id, asset_class_id) unterstützt diesen
    Zugriffspfad allein nicht, da `asset_class_id` nicht der führende Teil
    des PK-Index ist.
    """

    __tablename__ = "data_source_asset_class"
    __table_args__ = (Index("ix_data_source_asset_class_asset_class_id", "asset_class_id"),)

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_source.id"), primary_key=True
    )
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), primary_key=True
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"DataSourceAssetClass(data_source_id={self.data_source_id!r}, "
            f"asset_class_id={self.asset_class_id!r})"
        )


class MarketDataBronze(Base):
    """Bronze-Rohdaten — immutabel, Point-in-Time, versioniert (data-model.md
    §2 `market_data_bronze`, BR-121/BR-122; Spec `docs/specs/datenqualitaet.md`
    AC1/AC2/AC9/AC10).

    Feldnamen 1:1 aus data-model.md §2 (physisches Schema); die Spec-Verträge
    (`docs/specs/datenqualitaet.md` „Bronze-Datensatz") nennen dieselben
    Inhalte unter den fachlichen Namen `event_id` (= `source_event_id`),
    `roh_wert` (= `payload`), `quelle` (= `data_source_id`),
    `beobachtungs_zeitpunkt` (= `observed_at`), `empfangs_zeitpunkt`
    (= `ingested_at`), `anlageklassen_tag` (= `asset_class_tag`).

    **Immutabilität (AC1, BR-121):** Es gibt in dieser Codebasis absichtlich
    KEINE Update-/Delete-Funktion für diese Tabelle — `app.db.bronze` bietet
    ausschliesslich `record_observation()` (Insert-only) und `replay()`
    (Read-only). Als DB-seitige zweite Sicherungsebene (analog BR-101,
    `category_weight`-Migration) legt die Migration
    `<REVISION>_create_market_data_bronze.py` zusätzlich einen
    BEFORE-UPDATE/DELETE-Trigger an, der jeden Änderungsversuch mit
    `RAISE EXCEPTION` zurückweist (Wahl laut data-model.md §11 Fussnote dem
    `coder` überlassen).

    **Idempotenz + Versionierung (AC9/AC10, BR-122):** `source_event_id` ist
    laut data-model.md §2 nicht global eindeutig, sondern gemeinsam mit
    `data_source_id` **eine Ereignis-Identität, die über mehrere
    Point-in-Time-Versionen hinweg stabil bleibt** — ein einzelnes physisches
    `UNIQUE (data_source_id, source_event_id)` wäre mit AC10 (neue Version bei
    Revision) unvereinbar, zusätzlich verlangt eine RANGE-partitionierte
    Tabelle laut PostgreSQL, dass jeder Unique-Index die Partitionsspalte
    (`ingested_at`) enthält — ein rein auf `ingested_at` erweiterter Index
    würde die Duplikaterkennung selbst aushebeln (jede Zeile bekommt einen
    frischen `ingested_at`-Wert). Die Dedupe-/Versionierungs-Entscheidung
    (identischer Inhalt → idempotent überspringen [AC9]; abweichender Inhalt
    → neue Version anlegen, nie überschreiben [AC10]) liegt daher in
    `app.db.bronze.record_observation()` (App-Layer) sowie — als DB-seitige
    zweite Sicherung, analog BR-101 — in einem BEFORE-INSERT-Trigger der
    Migration. Diese Präzisierung ist in `docs/data-model.md` §2 nachgezogen.

    `payload` entspricht der `roh_wert`-Spalte des Vertrags — unveränderte
    Rohantwort/Wert der Quelle (JSONB, damit sowohl Skalare als auch
    strukturierte Rohantworten passen).
    """

    __tablename__ = "market_data_bronze"
    __table_args__ = (
        Index("ix_market_data_bronze_source_ingested_at", "data_source_id", "ingested_at"),
        Index("ix_market_data_bronze_asset_class_observed_at", "asset_class_tag", "observed_at"),
        Index("ix_market_data_bronze_source_event_id", "data_source_id", "source_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    ingested_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        primary_key=True,
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        server_default=sa.text("now()"),
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_source.id"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String, nullable=False)
    asset_class_tag: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), nullable=True
    )
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    # Generisches JSON mit Postgres-Variant JSONB (data-model.md §2: "JSONB,
    # unveraenderte Rohantwort") — generisches sa.JSON bleibt dialektportabel
    # (SQLite-Tests, siehe Konvention der übrigen Migrations-Tests), waehrend
    # unter Postgres physisch JSONB verwendet wird.
    payload: Mapped[Any] = mapped_column(
        sa.JSON().with_variant(JSONB, "postgresql"), nullable=False
    )
    quality_indicator: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(sa.TIMESTAMP(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"MarketDataBronze(data_source_id={self.data_source_id!r}, "
            f"source_event_id={self.source_event_id!r}, observed_at={self.observed_at!r}, "
            f"ingested_at={self.ingested_at!r})"
        )
