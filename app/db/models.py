"""ORM-Modelle — 1:1 aus docs/data-model.md (`dba`-Detailkonzept, bindend).

Diese Datei bildet bislang nur die von der laufenden Story benoetigten Tabellen ab;
weitere Entitaeten aus data-model.md kommen ueber Folge-Stories dazu (P6/ADR-008:
Anlageklassen sind Konfiguration, keine Code-Grenze).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# data-model.md §1 `asset_class`: CHECK prio_stufe ∈ {MVP, Stufe2, Stufe3}
PRIO_STUFE_VALUES = ("MVP", "Stufe2", "Stufe3")

# data-model.md §1 `analysis_category`: CHECK code ∈ {...} (5 Analysekategorien, C-007)
ANALYSIS_CATEGORY_CODES = ("fundamental", "technisch", "qualitativ", "makro", "risiko_quant")

# data-model.md §1 `data_source`: CHECK kategorie ∈ {...} — die 5 Kategorien
# aus AC5/C-009 ("KI Investment – Datenquellen.md"): Equity Insider &
# Fundamentals · Retail Sentiment & Social · Blockchain & Crypto Smart Money ·
# ETFs & Fonds · Makroökonomie & Anleihen.
DATA_SOURCE_KATEGORIE_VALUES = (
    "equity_fundamentals",
    "retail_social",
    "blockchain_crypto",
    "etf_fonds",
    "makro_anleihen",
)

# data-model.md §1 `data_source`: CHECK qualitaet ∈ {...} (nullable Spalte).
DATA_SOURCE_QUALITAET_VALUES = ("niedrig", "mittel", "mittel_hoch", "hoch", "sehr_hoch")


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
    """Datenquellen-Registry (data-model.md `data_source`, C-009, AC5/AC13).

    `aktiv` steuert, ob der Scheduler diese Quelle je abruft (AC13 — nur die
    5 im MVP kostenlosen Quellen sind `aktiv=true`, siehe Seed-Migration
    `3654339f201d_...py`). `vault_ref` ist NIE ein Klartext-Secret, nur ein
    Zeiger-Name auf die künftige Env-Var/Secrets-Store-Referenz (BR-126).
    """

    __tablename__ = "data_source"
    __table_args__ = (
        CheckConstraint(
            "kategorie IN ('equity_fundamentals', 'retail_social', 'blockchain_crypto', "
            "'etf_fonds', 'makro_anleihen')",
            name="ck_data_source_kategorie",
        ),
        CheckConstraint(
            "qualitaet IS NULL OR qualitaet IN "
            "('niedrig', 'mittel', 'mittel_hoch', 'hoch', 'sehr_hoch')",
            name="ck_data_source_qualitaet",
        ),
        CheckConstraint(
            "frequenz_sekunden BETWEEN 30 AND 86400",
            name="ck_data_source_frequenz_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    kategorie: Mapped[str] = mapped_column(String, nullable=False)
    qualitaet: Mapped[str | None] = mapped_column(String, nullable=True)
    frequenz_sekunden: Mapped[int] = mapped_column(Integer, nullable=False)
    kostenmodell: Mapped[str | None] = mapped_column(String, nullable=True)
    kosten_monatlich_chf: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True, server_default=sa.text("0")
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
    AC5). Ordnet jeder Quelle die Anlageklassen zu, für die sie verwertbare
    Signale liefert — Basis des Registry-Matchings in der (späteren)
    Datenquellen-Abfrage. Reddit trägt hier ausschliesslich Zeilen für die
    retail-getriebenen Klassen 1 und 7 (AC6, BR-123, siehe Seed-Migration).
    """

    __tablename__ = "data_source_asset_class"
    __table_args__ = (sa.Index("ix_data_source_asset_class_asset_class_id", "asset_class_id"),)

    data_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("data_source.id"), primary_key=True
    )
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), primary_key=True
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"DataSourceAssetClass(data_source_id={self.data_source_id!r}, "
            f"asset_class_id={self.asset_class_id!r})"
        )
