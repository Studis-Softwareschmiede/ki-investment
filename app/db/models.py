"""ORM-Modelle — 1:1 aus docs/data-model.md (`dba`-Detailkonzept, bindend).

Diese Datei bildet bislang nur die von der laufenden Story benoetigten Tabellen ab;
weitere Entitaeten aus data-model.md kommen ueber Folge-Stories dazu (P6/ADR-008:
Anlageklassen sind Konfiguration, keine Code-Grenze).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Interval,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
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

# data-model.md §1 `strategy_cluster`/`strategy`: CHECK cluster-code ∈ {...}
# (C-014, 4 Cluster) — einzige Quelle fuer den CHECK-Constraint unten (kein
# separates hartkodiertes SQL-Duplikat). Katalog-Inhalt (18 Strategien/4
# Cluster) + Cluster-Gate sind S-037 (Spec `strategie-exit-regeln`,
# AC2/AC3); `position` referenziert `strategy`/`time_horizon` bereits ab
# S-015 als FK-Voraussetzung (analog zur `analysis_category`-Voraussetzung
# aus S-004/2da446925bbc).
STRATEGY_CLUSTER_VALUES = (
    "passiv_regelbasiert",
    "aktiv_fundamental",
    "aktiv_technisch_makro",
    "professionell_algo",
)
_STRATEGY_CLUSTER_VALUES_SQL = ", ".join(repr(code) for code in STRATEGY_CLUSTER_VALUES)

# data-model.md §1 `strategy`: CHECK stufe ∈ {...} (C-014) — einzige Quelle
# fuer den CHECK-Constraint unten.
STRATEGY_STUFE_VALUES = ("MVP", "Stufe2", "Stufe3", "Stufe4")
_STRATEGY_STUFE_VALUES_SQL = ", ".join(repr(stufe) for stufe in STRATEGY_STUFE_VALUES)

# data-model.md §1 `time_horizon`: CHECK id ∈ 1..9 (C-014, 9 Stufen)
TIME_HORIZON_MIN_ID = 1
TIME_HORIZON_MAX_ID = 9

# data-model.md §4 `position`: CHECK einstand_methode ∈ {...}, DEFAULT
# gleitender_durchschnitt (CH-Default, → BR-112). Die eigentliche
# Berechnung nach dieser Methode ist S-016 (AC5) — hier nur die Spalte samt
# Default/Constraint (Positions-Grundgerüst, S-015).
EINSTAND_METHODE_VALUES = ("gleitender_durchschnitt", "fifo")
EINSTAND_METHODE_DEFAULT = "gleitender_durchschnitt"

# data-model.md §4 `position`: CHECK status ∈ {...}
POSITION_STATUS_VALUES = ("offen", "geschlossen")

# data-model.md §4 `position`/`order`/...: CHECK mode ∈ {...} (→ BR-130)
MODE_VALUES = ("echt", "simuliert")

# data-model.md §4 `exit_rule`: CHECK stop_typ ∈ {...}. Erweitert in S-040
# (Migration `d19a6f5c7b3e`) um 'technisch' (AC8-Präzisierung: Daytrade/
# Swing-Default nutzt `stop_typ == "technisch"`, siehe
# `app.db.exit_regel_ableitung`/`EXIT_DEFAULT_SET_STOP_TYP_VALUES`) — ohne
# diese Erweiterung würde die Fixierung (AC1) einer Daytrade/Swing-Position
# an der CHECK-Constraint scheitern. Der SQL-String wird — anders als vor
# S-040 — jetzt AUS dieser Konstante gebildet (siehe
# `_EXIT_RULE_STOP_TYP_VALUES_SQL` unten), damit Konstante und
# CHECK-Constraint nicht auseinanderdriften (S-037-Lesson).
EXIT_RULE_STOP_TYP_VALUES = ("fix_pct", "atr_trailing", "fundamental", "technisch", "keiner")
_EXIT_RULE_STOP_TYP_VALUES_SQL = ", ".join(repr(stop_typ) for stop_typ in EXIT_RULE_STOP_TYP_VALUES)

# data-model.md §1 `exit_default_set`: CHECK kategorie ∈ {...} (Spec
# `docs/specs/strategie-exit-regeln.md` AC8 — 5 Default-Exit-Set-Kategorien
# der Spec-Tabelle, Story S-038). Strategien/Klassen ohne Treffer nutzen den
# generischen AC7-Fallback (keine eigene Tabellenzeile, siehe
# `app.db.exit_regel_ableitung`).
EXIT_DEFAULT_SET_KATEGORIE_VALUES = (
    "value_aktien",
    "growth_momentum",
    "index_buy_and_hold",
    "krypto",
    "daytrade_swing",
)
_EXIT_DEFAULT_SET_KATEGORIE_VALUES_SQL = ", ".join(
    repr(kategorie) for kategorie in EXIT_DEFAULT_SET_KATEGORIE_VALUES
)

# data-model.md §1 `exit_default_set`: CHECK stop_typ ∈ {...} — zwei
# eigenständige Wertemengen mit identischem Inhalt seit S-040
# (EXIT_RULE_STOP_TYP_VALUES wurde dort um 'technisch' erweitert, siehe
# oben), bewusst NICHT als eine gemeinsame Konstante zusammengelegt: diese
# hier beschreibt die Ableitungs-Konfiguration (`exit_default_set`, S-038),
# jene die fixierte Persistenz-Spalte (`exit_rule`, S-015/S-040) — zwei
# eigenständige Tabellen/Migrationen, deren Wertemengen sich künftig wieder
# unabhängig voneinander entwickeln könnten.
EXIT_DEFAULT_SET_STOP_TYP_VALUES = ("fundamental", "atr_trailing", "fix_pct", "technisch", "keiner")
_EXIT_DEFAULT_SET_STOP_TYP_VALUES_SQL = ", ".join(
    repr(stop_typ) for stop_typ in EXIT_DEFAULT_SET_STOP_TYP_VALUES
)

# data-model.md §1 `atr_multiplier_default`: CHECK volatilitaetsklasse ∈ {...}
# (Spec AC9, Story S-038)
ATR_MULTIPLIER_VOLATILITAETSKLASSE_VALUES = ("ruhig", "volatil")
_ATR_MULTIPLIER_VOLATILITAETSKLASSE_VALUES_SQL = ", ".join(
    repr(klasse) for klasse in ATR_MULTIPLIER_VOLATILITAETSKLASSE_VALUES
)

# data-model.md §4 `transaction`: CHECK typ ∈ {...} (C-017, Story S-035)
TRANSACTION_TYP_VALUES = ("buy", "sell", "dividend", "fee", "fx_adjust")


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


class CategoryWeightVersion(Base):
    """Versionsregister für `category_weight` (data-model.md
    `category_weight_version`, S-018/AC10) — löst die reine `config_version`-
    Tag-Spalte aus S-004 ab. Eine Version ist ein vollständiger, append-only
    Snapshot aller Kategoriegewichte; genau eine Version trägt
    `is_current = True` (BR-133, DB-seitig durch einen partiellen
    UNIQUE-Index erzwungen, siehe Migration).
    """

    __tablename__ = "category_weight_version"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        server_default=sa.text("now()"),
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"CategoryWeightVersion(id={self.id!r}, is_current={self.is_current!r})"


class CategoryWeight(Base):
    """Kategoriegewicht je Anlageklasse (data-model.md `category_weight`,
    BR-101). Die fünf Gewichte einer Klasse müssen sich auf exakt 100 %
    summieren (AC6/AC7) — DB-seitig durch einen deferred Constraint-Trigger
    durchgesetzt (siehe Migration `2da446925bbc_...py` + Folge-Migration
    S-018), App-seitig durch `app.db.category_weights.validate_category_weights`.

    `config_version_id` (S-018/AC10) ersetzt die vormalige `config_version
    SMALLINT`-Tag-Spalte (S-004): jede Änderung legt eine neue
    `CategoryWeightVersion`-Zeile an (append-only, siehe
    `app.db.config_versions.erstelle_neue_category_weight_version`) statt
    bestehende Zeilen zu überschreiben.
    """

    __tablename__ = "category_weight"
    __table_args__ = (
        CheckConstraint("weight_pct >= 0 AND weight_pct <= 100", name="ck_category_weight_range"),
        Index("ix_category_weight_config_version_id", "config_version_id"),
    )

    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), primary_key=True
    )
    category_code: Mapped[str] = mapped_column(
        String, ForeignKey("analysis_category.code"), primary_key=True
    )
    config_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category_weight_version.id"),
        primary_key=True,
    )
    weight_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"CategoryWeight(asset_class_id={self.asset_class_id!r}, "
            f"category_code={self.category_code!r}, "
            f"config_version_id={self.config_version_id!r}, weight_pct={self.weight_pct!r})"
        )


class AnalysisMethodVersion(Base):
    """Versionsregister für `analysis_method` (data-model.md
    `analysis_method_version`, S-018/AC10) — unabhängig von
    `CategoryWeightVersion` (kein gemeinsamer Versionszähler über beide
    Konfig-Domänen). Genau eine Version trägt `is_current = True` (BR-133).
    """

    __tablename__ = "analysis_method_version"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        server_default=sa.text("now()"),
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    note: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"AnalysisMethodVersion(id={self.id!r}, is_current={self.is_current!r})"


class AnalysisMethod(Base):
    """Methodentabelle je Anlageklasse/Analysekategorie (data-model.md
    `analysis_method`, C-006/C-007/C-018, AC9/AC10/AC11).

    `ranking` ist klassenspezifisch fix (1-10, DB-CHECK, BR-102) und ändert
    sich nicht je Analyse (AC9). `config_version_id` versioniert die
    Methodentabelle analog zu `CategoryWeight` (append-only, AC10).
    `last_reviewed_at` trägt den AC11-Quartals-Review-Hinweis
    (`app.db.analysis_method_review`) — ein Review aktualisiert nur diesen
    Zeitstempel, niemals `ranking` selbst (Spec-Nicht-Ziel: kein
    automatisches Anpassen von Rankings).
    """

    __tablename__ = "analysis_method"
    __table_args__ = (
        CheckConstraint("ranking >= 1 AND ranking <= 10", name="ck_analysis_method_ranking_range"),
        CheckConstraint(
            "automation_grade IS NULL OR automation_grade IN ('AUTO', 'TEIL', 'BUILD')",
            name="ck_analysis_method_automation_grade",
        ),
        UniqueConstraint(
            "asset_class_id", "code", "config_version_id", name="uq_analysis_method_code_version"
        ),
        Index(
            "ix_analysis_method_asset_class_category_version",
            "asset_class_id",
            "category_code",
            "config_version_id",
        ),
        Index("ix_analysis_method_config_version_id", "config_version_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), nullable=False
    )
    category_code: Mapped[str] = mapped_column(
        String, ForeignKey("analysis_category.code"), nullable=False
    )
    config_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_method_version.id"), nullable=False
    )
    code: Mapped[str] = mapped_column(String, nullable=False)
    kurzbezeichnung: Mapped[str] = mapped_column(String, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(String, nullable=True)
    nutzen: Mapped[str | None] = mapped_column(String, nullable=True)
    ranking: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    automation_grade: Mapped[str | None] = mapped_column(String, nullable=True)
    last_reviewed_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"AnalysisMethod(asset_class_id={self.asset_class_id!r}, "
            f"category_code={self.category_code!r}, code={self.code!r}, "
            f"ranking={self.ranking!r})"
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


class StrategyCluster(Base):
    """Strategie-Cluster + App-Stufen-Freischaltung (data-model.md
    `strategy_cluster`, C-014, S-037-Präzisierung).

    `freigeschaltet` ist das Konfigurationsdatum aus Spec-AC2
    (`docs/specs/strategie-exit-regeln.md`) — ein zur Laufzeit per UPDATE
    änderbarer Toggle (analog `AssetClass.aktiv`/`DataSource.aktiv`), MVP-Default
    ist ausschliesslich `passiv_regelbasiert` freigeschaltet (BR-135).
    """

    __tablename__ = "strategy_cluster"
    __table_args__ = (
        CheckConstraint(
            f"code IN ({_STRATEGY_CLUSTER_VALUES_SQL})",
            name="ck_strategy_cluster_code",
        ),
    )

    code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    freigeschaltet: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"StrategyCluster(code={self.code!r}, freigeschaltet={self.freigeschaltet!r})"


class Strategy(Base):
    """Anlagestrategie (data-model.md `strategy`, C-014, 18 Strategien in
    4 Clustern, Spec `docs/specs/strategie-exit-regeln.md` AC2).

    `cluster` ist eine FK auf `strategy_cluster.code` (S-037-Präzisierung,
    ersetzt die vormalige eigenständige CHECK-Wertemenge — Werte identisch)
    — die tatsächliche Freischaltungsprüfung (BR-135, E2) erfolgt über
    `app.db.strategie_katalog.pruefe_cluster_freischaltung()`.
    """

    __tablename__ = "strategy"
    __table_args__ = (
        CheckConstraint(
            f"stufe IN ({_STRATEGY_STUFE_VALUES_SQL})",
            name="ck_strategy_stufe",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    cluster: Mapped[str] = mapped_column(
        String, ForeignKey("strategy_cluster.code"), nullable=False
    )
    stufe: Mapped[str] = mapped_column(String, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"Strategy(name={self.name!r}, cluster={self.cluster!r}, stufe={self.stufe!r})"


class TimeHorizon(Base):
    """Zeithorizont (data-model.md `time_horizon`, C-014, 9 Stufen, Spec
    `docs/specs/strategie-exit-regeln.md` AC3).

    `transaktionskosten_relevanz` + `break_even_anforderung` sind die zwei
    laut AC3 geforderten Attribute je Stufe (S-037-Präzisierung — ersetzt das
    vormalige einzelne `break_even_hinweis`-Feld, das noch in keiner
    Migration umgesetzt war).
    """

    __tablename__ = "time_horizon"
    __table_args__ = (
        CheckConstraint(
            f"id BETWEEN {TIME_HORIZON_MIN_ID} AND {TIME_HORIZON_MAX_ID}",
            name="ck_time_horizon_id_range",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    transaktionskosten_relevanz: Mapped[str] = mapped_column(String, nullable=False)
    break_even_anforderung: Mapped[str] = mapped_column(String, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"TimeHorizon(id={self.id!r}, name={self.name!r})"


class ExitDefaultSet(Base):
    """Default-Exit-Set je Kategorie — provisorischer, konfigurierbarer
    Default (data-model.md `exit_default_set`, Spec
    `docs/specs/strategie-exit-regeln.md` AC8, Story S-038).

    `kategorie` bildet die 5 Zeilen der AC8-Tabelle ab (Value/Aktien,
    Growth/Momentum, Index/Buy-and-Hold, Krypto, Daytrade/Swing) — die
    Zuordnung Strategie/Anlageklasse/Zeithorizont -> Kategorie (inkl.
    generischem Fallback für Strategien ohne eigene Tabellenzeile) trifft
    `app.db.exit_regel_ableitung.klassifiziere_exit_kategorie` (AC8-
    Präzisierung in der Spec). Jede Zeile ist ein reines
    DB-Konfigurationsdatum (analog `StrategyCluster.freigeschaltet`) — zur
    Laufzeit per UPDATE änderbar, ohne Code-/Migrations-Änderung (NFR "zur
    Laufzeit konfigurierbar").
    """

    __tablename__ = "exit_default_set"
    __table_args__ = (
        CheckConstraint(
            f"kategorie IN ({_EXIT_DEFAULT_SET_KATEGORIE_VALUES_SQL})",
            name="ck_exit_default_set_kategorie",
        ),
        CheckConstraint(
            f"stop_typ IN ({_EXIT_DEFAULT_SET_STOP_TYP_VALUES_SQL})",
            name="ck_exit_default_set_stop_typ",
        ),
    )

    kategorie: Mapped[str] = mapped_column(String, primary_key=True)
    stop_typ: Mapped[str] = mapped_column(String, nullable=False)
    stop_parameter_hinweis: Mapped[str] = mapped_column(String, nullable=False)
    stop_parameter_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    take_profit_hinweis: Mapped[str | None] = mapped_column(String, nullable=True)
    time_box: Mapped[timedelta | None] = mapped_column(Interval, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"ExitDefaultSet(kategorie={self.kategorie!r}, stop_typ={self.stop_typ!r})"


class AtrMultiplierDefault(Base):
    """ATR-Multiplikator je Volatilitätsklasse — provisorischer,
    konfigurierbarer Default (data-model.md `atr_multiplier_default`, Spec
    `docs/specs/strategie-exit-regeln.md` AC9, Story S-038).

    `multiplikator` ist der angewandte Punktwert (Richtwert-Mittelpunkt der
    Spec-Bandbreite, siehe AC9-Präzisierung); `multiplikator_min`/`_max`
    dokumentieren die von der Spec genannte Bandbreite (ruhig 2–2.5×,
    volatil 3–4×) — reine Referenzwerte, nicht Teil der Ableitungsrechnung
    (`app.db.exit_regel_ableitung.leite_exit_regeln_ab` verwendet nur
    `multiplikator`)."""

    __tablename__ = "atr_multiplier_default"
    __table_args__ = (
        CheckConstraint(
            f"volatilitaetsklasse IN ({_ATR_MULTIPLIER_VOLATILITAETSKLASSE_VALUES_SQL})",
            name="ck_atr_multiplier_default_volatilitaetsklasse",
        ),
    )

    volatilitaetsklasse: Mapped[str] = mapped_column(String, primary_key=True)
    multiplikator: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    multiplikator_min: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    multiplikator_max: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"AtrMultiplierDefault(volatilitaetsklasse={self.volatilitaetsklasse!r}, "
            f"multiplikator={self.multiplikator!r})"
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


class MarketDataSilver(Base):
    """Silver-Schicht — normalisierte, Corporate-Actions-adjustierte Werte
    (data-model.md §2 `market_data_silver`, präzisiert für S-024; Spec
    `docs/specs/datenqualitaet.md` AC3/AC6).

    Deckt den Spec-Vertrag "Silver-Datensatz" 1:1 (Feldnamen laut
    data-model.md-Präzisierung):
    `event_id` = `source_event_id`, `normalisierter_wert` = `normalisierter_wert`,
    `einheit` = `einheit`, `adjustierungs_info` = `adjustierungs_info`,
    `abgeleitet_aus: bronze_version` = `bronze_id` + `bronze_ingested_at`
    (zusammen die vollständige FK auf die partitionierte `market_data_bronze`-
    Tabelle, deren PK `(id, ingested_at)` ist — Partitionsschlüssel muss laut
    Postgres Teil jeder FK auf eine partitionierte Tabelle sein).

    **Reproduzierbarkeit (AC3-NFR):** diese Tabelle ist eine reine Ableitung
    aus `market_data_bronze` — jede Zeile kann jederzeit aus der
    referenzierten Bronze-Zeile + den zum Ableitungszeitpunkt bekannten
    Corporate Actions neu berechnet werden (`app.db.silver`). Anders als
    Bronze (BR-121, append-only) ist Silver **nicht** immutable: bei einer
    rückwirkend gemeldeten Corporate Action werden die betroffenen Zeilen für
    Symbol/Quelle gelöscht und neu abgeleitet (AC6-Edge-Case) — Bronze bleibt
    dabei unverändert.

    `instrument_id` aus data-model.md ist bewusst nicht umgesetzt — die
    `instrument`-Tabelle existiert in dieser Codebasis noch nicht (siehe
    data-model.md-Präzisierung + Coder-Handoff S-024). `symbol` (aus der
    Bronze-Zeile übernommen) übernimmt stattdessen die fachliche Rolle,
    Corporate Actions dem richtigen Titel zuzuordnen.

    **`data_source_id` (Iteration 2, Reviewer-Befund, empirisch gegen
    Postgres 17 belegt):** denormalisiert aus der Bronze-Zeile übernommen.
    `source_event_id` ist laut BR-122/data-model.md §2 NUR gemeinsam mit
    `data_source_id` eine eindeutige Ereignis-Identität — ohne diese Spalte
    kann `rebuild_silver_series_for_symbol()` beim Löschen/Neu-Ableiten nicht
    zuverlässig zwischen zwei Quellen unterscheiden, die zufällig dieselbe
    `source_event_id`-Zeichenkette für dasselbe Symbol verwenden (silent
    Cross-Data-Source-Datenverlust, siehe `.claude/lessons/coder.md`).

    **`uq_market_data_silver_bronze_version` (Iteration 2, Reviewer-Befund):**
    `(bronze_id, bronze_ingested_at, observed_at)` ist physisch UNIQUE — im
    Unterschied zu `market_data_bronze` (BR-122) ist ein echter Unique-Index
    hier möglich, weil `observed_at` (Partitionsschlüssel) für dieselbe
    Bronze-Version deterministisch identisch ist (1:1 aus der referenzierten
    Bronze-Zeile übernommen, nicht wie bei Bronze bei jedem Insert neu
    vergeben) — der Index erfüllt damit sowohl die Postgres-Pflicht
    (Partitionsschlüssel Teil jedes Unique-Index auf partitionierter Tabelle)
    als auch die eigentliche Dedupe-Garantie. `record_silver_observation()`
    fängt den daraus resultierenden `IntegrityError` bei einem parallelen
    Duplikat-Versuch ab (siehe `app/db/silver.py`).
    """

    __tablename__ = "market_data_silver"
    __table_args__ = (
        ForeignKeyConstraint(
            ["bronze_id", "bronze_ingested_at"],
            ["market_data_bronze.id", "market_data_bronze.ingested_at"],
        ),
        UniqueConstraint(
            "bronze_id",
            "bronze_ingested_at",
            "observed_at",
            name="uq_market_data_silver_bronze_version",
        ),
        Index("ix_market_data_silver_symbol_observed_at", "symbol", "observed_at"),
        Index("ix_market_data_silver_source_event_id", "source_event_id"),
        Index("ix_market_data_silver_bronze_id_ingested_at", "bronze_id", "bronze_ingested_at"),
        Index("ix_market_data_silver_data_source_id_symbol", "data_source_id", "symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    observed_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), primary_key=True, nullable=False
    )
    bronze_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    bronze_ingested_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_source.id"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    normalisierter_wert: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    einheit: Mapped[str] = mapped_column(String, nullable=False)
    adjustierungs_info: Mapped[Any] = mapped_column(
        sa.JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"MarketDataSilver(source_event_id={self.source_event_id!r}, "
            f"symbol={self.symbol!r}, normalisierter_wert={self.normalisierter_wert!r}, "
            f"einheit={self.einheit!r})"
        )


class MarketDataGold(Base):
    """Gold-Schicht — angereicherte Konsumenten-Werte (data-model.md §2
    `market_data_gold`, S-051; Spec `docs/specs/datenqualitaet.md` AC4).

    Deckt den Spec-Vertrag "Gold-Datensatz" 1:1 (Feldnamen laut
    data-model.md-Präzisierung): `event_id` = `source_event_id`,
    `angereicherter_wert` = `angereicherter_wert`, `qualitaetsindikator` =
    `qualitaetsindikator`, `herkunft: silver_version` = `silver_id` +
    `silver_observed_at` (zusammen die vollständige FK auf die partitionierte
    `market_data_silver`-Tabelle, deren PK `(id, observed_at)` ist —
    Partitionsschlüssel muss laut Postgres Teil jeder FK auf eine
    partitionierte Tabelle sein).

    **Anreicherung (AC4):** `angereicherter_wert` wird unverändert aus
    `market_data_silver.normalisierter_wert` übernommen (bereits normalisiert
    + Corporate-Actions-adjustiert); `qualitaetsindikator` wird aus
    `market_data_bronze.quality_indicator` propagiert (Socket-
    Qualitätsmetadatum, in Silver bisher nicht exponiert) — die Gold-Zeile
    kombiniert damit Information aus Silver (Wert) und Bronze (Qualitäts-
    Kontext) zu einer konsumentenfertigen Sicht, ohne Score-/Signal-
    Aggregation (z-Scores etc. sind laut Spec-Nicht-Ziel Sache der Analyse,
    nicht dieser Schicht — siehe `app/db/gold.py`).

    **Reproduzierbarkeit (AC4-NFR):** wie Silver ist auch Gold eine reine
    Ableitung — `app.db.gold.rebuild_gold_series_for_symbol` leitet die
    komplette Reihe jederzeit neu aus Silver/Bronze ab. Weder Bronze noch
    Silver werden von diesem Modul verändert (AC4: "keine Anreicherung
    verändert oder ersetzt die zugrunde liegenden Bronze-Rohdaten").

    **`data_source_id` (denormalisiert, analog Silver/Iteration-2-Lehre):**
    aus der Silver-Zeile übernommen — ohne diese Spalte könnte
    `rebuild_gold_series_for_symbol` beim Löschen/Neu-Ableiten nicht
    zuverlässig zwischen zwei Quellen unterscheiden, die zufällig dieselbe
    `source_event_id`-Zeichenkette für dasselbe Symbol verwenden (dieselbe
    Klasse Cross-Data-Source-Bug wie bei Silver, hier vorab vermieden).

    **`ON DELETE CASCADE` (Iteration 2, DBA-Befund, Critical):**
    `app.db.silver.rebuild_silver_series_for_symbol` löscht bei jeder
    Corporate-Actions-Neuableitung ALLE bestehenden Silver-Zeilen für
    `(data_source_id, symbol)` — ohne `ON DELETE CASCADE` schlägt dieses
    `DELETE` unter Postgres mit einer Fremdschlüsselverletzung fehl, sobald
    mindestens eine der zu löschenden Silver-Zeilen bereits eine abgeleitete
    Gold-Zeile hat. Gold-Zeilen haben laut AC4 keine eigenständige Existenz
    (reine Ableitung) und sind laut AC4-NFR jederzeit über
    `app.db.gold.rebuild_gold_series_for_symbol` reproduzierbar — ein
    automatisches Mitlöschen bei Silver-Neuableitung ist damit konsistent
    zum bestehenden Silver-Design (siehe Migration `0da3d5a72ba2` für die
    volle Begründung).
    """

    __tablename__ = "market_data_gold"
    __table_args__ = (
        ForeignKeyConstraint(
            ["silver_id", "silver_observed_at"],
            ["market_data_silver.id", "market_data_silver.observed_at"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "silver_id",
            "silver_observed_at",
            "observed_at",
            name="uq_market_data_gold_silver_version",
        ),
        Index("ix_market_data_gold_symbol_observed_at", "symbol", "observed_at"),
        Index("ix_market_data_gold_source_event_id", "source_event_id"),
        Index("ix_market_data_gold_silver_id_observed_at", "silver_id", "silver_observed_at"),
        Index("ix_market_data_gold_data_source_id_symbol", "data_source_id", "symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    observed_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), primary_key=True, nullable=False
    )
    silver_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    silver_observed_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_source.id"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    angereicherter_wert: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    qualitaetsindikator: Mapped[str | None] = mapped_column(String, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"MarketDataGold(source_event_id={self.source_event_id!r}, "
            f"symbol={self.symbol!r}, angereicherter_wert={self.angereicherter_wert!r}, "
            f"qualitaetsindikator={self.qualitaetsindikator!r})"
        )


class IngestDeadLetter(Base):
    """Dead-Letter-Queue dauerhaft fehlschlagender Abrufe (data-model.md §7
    `ingest_dead_letter`, C-009; Spec `docs/specs/dateneingang.md` AC10,
    S-020).

    Eine Zeile entsteht, wenn ein `Arbeitselement` (`app.scheduler.queue`)
    nach erschöpften Exponential-Backoff-Versuchen (transiente Fehler: HTTP
    429, 5xx, Timeout) endgültig aufgegeben wird (`app.scheduler.worker`,
    AC10 „... wird das Arbeitselement in eine Dead-Letter-Queue verschoben
    und protokolliert, ohne andere Quellen zu blockieren"). Diese Tabelle
    ist die dauerhafte, abfragbare Ablage (DLQ-Backlog-Monitoring,
    data-model.md §8 `(data_source_id, created_at)`-Index) — die
    transiente Redis-Queue-of-Work (`app.scheduler.queue.ArbeitsQueue`)
    hält dieselbe Information nur bis zum jeweiligen Verarbeitungsversuch,
    nicht darüber hinaus.

    `payload`/`source_event_id` sind optional (`nullable=True`): ein
    Arbeitselement kann bereits vor dem eigentlichen Quellen-Abruf
    fehlschlagen (z. B. Verbindungsaufbau) und trägt dann noch keine
    quellenspezifische Rohantwort/Ereignis-ID.
    """

    __tablename__ = "ingest_dead_letter"
    __table_args__ = (
        Index(
            "ix_ingest_dead_letter_data_source_id_created_at",
            "data_source_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_source.id"), nullable=False
    )
    source_event_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[Any] = mapped_column(sa.JSON().with_variant(JSONB, "postgresql"), nullable=True)
    fehler: Mapped[str] = mapped_column(String, nullable=False)
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default=sa.text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
        server_default=sa.text("now()"),
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"IngestDeadLetter(data_source_id={self.data_source_id!r}, "
            f"fehler={self.fehler!r}, retry_count={self.retry_count!r})"
        )


class Instrument(Base):
    """Titel / handelbares Instrument (data-model.md §1 `instrument`,
    C-007, C-017).

    Keine Story besitzt bislang die Erst-Anlage von `instrument`-Zeilen
    (Kandidatensuche-/Analyse-Module, die einen Titel zuerst identifizieren,
    sind noch nicht gebaut). Analog zur `analysis_category`-Voraussetzung
    aus S-004 (Migration `2da446925bbc`) wird diese Tabelle hier als harte
    FK-Voraussetzung für `Position.instrument_id` angelegt — **leeres**
    Schema, **kein** Seed: anders als bei den 11 Anlageklassen gibt es keine
    fixe, aufzählbare Titel-Liste. `app.domain.portfolio.fill_booking`
    (S-015) legt selbst KEINE Instrument-Zeilen an; ein Fill referenziert
    `titel_id` als bereits existierende `instrument.id` (angelegt von einem
    vorgelagerten, hier noch nicht gebauten Modul).
    """

    __tablename__ = "instrument"
    __table_args__ = (
        Index("ix_instrument_asset_class_id", "asset_class_id"),
        Index("ix_instrument_symbol", "symbol"),
        sa.UniqueConstraint("symbol", "asset_class_id", name="uq_instrument_symbol_asset_class"),
        CheckConstraint("length(currency) = 3", name="ck_instrument_currency_iso3"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), nullable=False
    )
    gics_sector: Mapped[str | None] = mapped_column(String, nullable=True)
    gics_industry: Mapped[str | None] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    liquiditaet: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    volatilitaet: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"Instrument(symbol={self.symbol!r}, asset_class_id={self.asset_class_id!r})"


class Position(Base):
    """Gehaltene Position — Positions-Grundgerüst (data-model.md §4
    `position`, C-014, C-017; Spec `docs/specs/depot.md`, Story S-015,
    AC1).

    Trägt mindestens die von AC1 geforderten Attribute: Titel-Identität
    (`instrument_id`), Menge, Einstandspreis, Anlageklasse
    (`asset_class_id`), GICS-Branche (über `Instrument.gics_sector`),
    Strategie (`strategy_id`), Zeithorizont (`time_horizon_id`),
    Exit-Regeln (`ExitRule`, 1:1 über `position_id`) und die These
    (`these`). „Aktuelle Bewertung" (ebenfalls in AC1 gefordert) ist
    bewusst KEINE Spalte hier — sie wird live über den Socket-Live-Kurs-
    Zugriff bezogen (Spec §Verträge „Bewertung"), nicht persistiert.

    Diese Story (S-015) liefert nur das Schema plus den Buchungs-
    Eintrittspunkt (`app.domain.portfolio.fill_booking.pruefe_fill`,
    AC1/AC10) — das eigentliche Anlegen/Fortschreiben einer Positions-Zeile
    (Ø-Einstand-Berechnung, Gebühren-Netting, G/V) ist S-016 (AC2/AC3/AC5).

    **S-053 (AC6, FX-Attribution)** ergänzt drei Spalten:
    `einstand_fx_rate` (Ø-Einstands-FX-Kurs, `None` bei CHF) wird
    fortgeschrieben — analog zu `einstand_preis` — über
    `app.adapters.repositories.position_repository
    .SqlAlchemyPositionRepository.lege_position_an`/`aktualisiere_kauf`.
    `fx_kapital_gv`/`fx_waehrungs_gv` (unrealisierte FX-Attribution) sind
    dagegen — analog zu `unrealisierter_gv` (S-016) — reservierte Spalten
    OHNE Schreibpfad: das Nachführen anhand des Live-Kurses ist die noch
    nicht gebaute Bewertungs-Schleife (siehe `app.domain.portfolio
    .fx_attribution.berechne_fx_split_unrealisiert`-Docstring), kein
    Fill-getriebener Schreibpfad dieser Story.

    **S-040 (AC5, → BR-137):** `strategy_id`/`time_horizon_id`/`these` sind
    nach dem Kauf unveränderlich (Spec `docs/specs/strategie-exit-regeln.md`
    AC5) — unter Postgres per `BEFORE UPDATE`-Trigger durchgesetzt, der NUR
    Änderungen an genau diesen drei Spalten verweigert (Migration
    `d19a6f5c7b3e`); alle übrigen Spalten (`menge`, `einstand_preis`,
    `status`, `closed_at` etc.) bleiben regulär fortschreibbar — anders als
    `ExitRule`/`Transaction` ist `position` KEINE reine Append-only-Tabelle.
    """

    __tablename__ = "position"
    __table_args__ = (
        Index("ix_position_instrument_id", "instrument_id"),
        Index("ix_position_status", "status"),
        Index("ix_position_mode", "mode"),
        Index("ix_position_asset_class_id", "asset_class_id"),
        CheckConstraint("menge >= 0", name="ck_position_menge_non_negative"),
        CheckConstraint(
            "einstand_methode IN ('gleitender_durchschnitt', 'fifo')",
            name="ck_position_einstand_methode",
        ),
        CheckConstraint("status IN ('offen', 'geschlossen')", name="ck_position_status"),
        CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_position_mode"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument.id"), nullable=False
    )
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), nullable=False
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("strategy.id"), nullable=False
    )
    time_horizon_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("time_horizon.id"), nullable=False
    )
    these: Mapped[str] = mapped_column(String, nullable=False)
    menge: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    einstand_preis: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    einstand_methode: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=EINSTAND_METHODE_DEFAULT,
        server_default=sa.text(f"'{EINSTAND_METHODE_DEFAULT}'"),
    )
    realisierter_gv: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0"), server_default=sa.text("0")
    )
    unrealisierter_gv: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    einstand_fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    fx_kapital_gv: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    fx_waehrungs_gv: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"Position(instrument_id={self.instrument_id!r}, menge={self.menge!r}, "
            f"status={self.status!r})"
        )


class ExitRule(Base):
    """Beim Kauf fixierte Exit-Regeln (data-model.md §4 `exit_rule`, C-011,
    C-014; unveränderlich nach Kauf → BR-111).

    1:1 zu `Position` über `position_id`. S-015 lieferte nur das Schema als
    Teil des Positions-Grundgerüsts (AC1 „Exit-Regeln" als Position-
    Attribut) — die inhaltliche Ableitung der Werte (Default-Exit-Set je
    Strategie/Klasse, ATR-Multiplikatoren) ist `strategie-exit-regeln`
    (S-038, AC6-AC9).

    **S-040 (AC1/AC5)** schliesst zwei Lücken:
    - Das tatsächliche Anlegen einer Zeile beim Kauf
      (`app.adapters.repositories.position_repository
      .SqlAlchemyPositionRepository.lege_position_an`, aus dem
      `FillInput.exit_regeln`-Pass-through).
    - Die BR-111-Unveränderlichkeit (kein UPDATE/DELETE nach dem Insert) —
      unter Postgres per `BEFORE UPDATE OR DELETE`-Trigger durchgesetzt
      (Migration `d19a6f5c7b3e`, analog `Transaction`/`TrialRegistry`).
    """

    __tablename__ = "exit_rule"
    __table_args__ = (
        CheckConstraint(
            f"stop_typ IN ({_EXIT_RULE_STOP_TYP_VALUES_SQL})",
            name="ck_exit_rule_stop_typ",
        ),
    )

    position_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("position.id"), primary_key=True
    )
    stop_loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    take_profit_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    stop_typ: Mapped[str | None] = mapped_column(String, nullable=True)
    atr_multiplikator: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    thesis_invalidation: Mapped[str | None] = mapped_column(String, nullable=True)
    time_box: Mapped[timedelta | None] = mapped_column(Interval, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"ExitRule(position_id={self.position_id!r}, stop_typ={self.stop_typ!r})"


class Transaction(Base):
    """Append-only Transaktionshistorie (data-model.md §4 `transaction`,
    C-017; Spec `docs/specs/depot.md`, Story S-035, AC4/AC7; → BR-115).

    Ein Insert je Fill (Kauf/Verkauf) — `typ` bildet `FillInput.richtung`
    ab (`kauf`→`buy`, `verkauf`→`sell`); `dividend`/`fee`/`fx_adjust` sind
    im CHECK-Constraint mitgeführt (data-model.md §4), aber von keiner
    Story bisher befüllt (kein Schreibpfad für diese Typen existiert noch).

    **Append-only-Durchsetzung (AC4/BR-115), zwei Schichten:**
    - **DB:** die Migration (`create_transaction_historie`) legt unter
      Postgres einen `BEFORE UPDATE OR DELETE`-Trigger an, der jede
      Mutation/Löschung mit einer Exception verweigert (wirkungslos unter
      SQLite/Struktur-Tests, analog zu `with_for_update()`,
      `position_repository`-Konvention).
    - **App:** `PositionRepository` (der einzige Zugriffspfad, P1) bietet
      für diese Tabelle ausschliesslich `schreibe_transaktion` (Insert)
      und `historie_je_titel` (Lesen) an — keine Update-/Delete-Methode
      existiert im Port, es gibt also strukturell keinen Aufrufer-Pfad für
      eine nachträgliche Änderung.

    `position_id` ist NULLable: ein Verkauf-Fill, der bei FIFO mehrere
    Lots verbraucht (A2), ist keinem einzelnen Lot eindeutig zuordenbar —
    der Verträge-Vertrag der Transaktionshistorie selbst
    (`docs/specs/depot.md` §Verträge) referenziert ohnehin nur `titel_id`,
    keine `position_id`.

    `arrival_price`/`slippage_abs` sind NULLable auf Schema-Ebene (nur bei
    `typ ∈ {buy, sell}` sinnvoll), werden aber von
    `app.adapters.repositories.position_repository
    .SqlAlchemyPositionRepository.schreibe_transaktion` für jeden
    Kauf-/Verkauf-Fill immer gesetzt (AC7): `slippage_abs = preis −
    arrival_price`, identische Formel zu BR-114 (`trade_fill.slippage_abs`,
    C-016), hier auf die Depot-eigene Historie angewandt (C-017).
    """

    __tablename__ = "transaction"
    __table_args__ = (
        Index("ix_transaction_position_id", "position_id"),
        Index("ix_transaction_instrument_id", "instrument_id"),
        Index("ix_transaction_booked_at", "booked_at"),
        Index("ix_transaction_mode", "mode"),
        CheckConstraint(
            "typ IN ('buy', 'sell', 'dividend', 'fee', 'fx_adjust')", name="ck_transaction_typ"
        ),
        CheckConstraint("mode IN ('echt', 'simuliert')", name="ck_transaction_mode"),
        CheckConstraint("length(waehrung) = 3", name="ck_transaction_waehrung_iso3"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("position.id"), nullable=True
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument.id"), nullable=False
    )
    typ: Mapped[str] = mapped_column(String, nullable=False)
    menge: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    preis: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    kosten_chf: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0"), server_default=sa.text("0")
    )
    waehrung: Mapped[str] = mapped_column(String, nullable=False)
    arrival_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    slippage_abs: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    kapital_gv_chf: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    waehrungs_gv_chf: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    booked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"Transaction(instrument_id={self.instrument_id!r}, typ={self.typ!r}, "
            f"menge={self.menge!r})"
        )


class DepotFillDedup(Base):
    """Idempotenz-Ledger für die Fill→Depot-Fortschreibung (data-model.md §4
    `depot_fill_dedup`, ADR-011, P8) — nachgezogen im DBA-Zweit-Review von
    S-016 (Critical-Befund: ohne Dedup schreibt ein doppelt zugestellter
    Fill (Redis-Queue, at-least-once) die Position doppelt fort).

    Bewusst ein reiner Marker (`client_order_id` als PK, kein weiterer
    fachlicher Inhalt) — **kein** Ersatz für die volle append-only
    Transaktionshistorie (`transaction`, AC4/AC7 → S-035); diese Tabelle
    beantwortet ausschliesslich die Frage „wurde dieser Fill schon einmal
    verbucht?" (siehe `app.adapters.repositories.position_repository
    .SqlAlchemyPositionRepository.markiere_fill_verbucht`).
    """

    __tablename__ = "depot_fill_dedup"
    __table_args__ = (
        Index("ix_depot_fill_dedup_instrument_id", "instrument_id"),
        CheckConstraint("richtung IN ('kauf', 'verkauf')", name="ck_depot_fill_dedup_richtung"),
    )

    client_order_id: Mapped[str] = mapped_column(String, primary_key=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instrument.id"), nullable=False
    )
    richtung: Mapped[str] = mapped_column(String, nullable=False)
    verbucht_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"DepotFillDedup(client_order_id={self.client_order_id!r})"


class TradingPlatform(Base):
    """Handelsplattform-Stammdaten (data-model.md §1 `trading_platform`,
    C-016; Spec `docs/specs/ausfuehrung-paper.md` AC10/AC11, Story S-017).

    Reine Referenzdaten-Registry — welche konkrete Plattform je Anlageklasse
    zustaendig ist, ergibt sich aus `PlatformAssetClass` (M:N, `bevorzugt`-
    Flag = Konfiguration der Zuordnung, siehe dortiger Docstring). Die
    tatsaechliche Broker-Anbindung (IBKR-Paper-Adapter, AC5) ist Nicht-Ziel
    dieser Story (S-046, Folge-Story) — `vault_ref` ist bereits hier
    vorgesehen (analog `DataSource.vault_ref`, BR-126: nie Klartext-Credential
    in der DB), bleibt aber bis zur Adapter-Story ungenutzt.

    Diese Migration seedt bewusst KEINE konkreten Plattform-Zeilen: die
    Spec/das Konzept nennen nur den Broker-Namen (Interactive Brokers), aber
    keine konkreten Courtage-/Spread-/Mindestgebuehr-Zahlen je Anlageklasse
    — deren Werte hier zu erfinden waere unbelegte Fabrikation. Die
    Referenzdaten sind Konfiguration (NFR "alle ... Defaults konfigurierbar")
    und werden ausserhalb dieser Story befuellt (Admin-Tooling/Migration
    einer spaeteren Story mit tatsaechlich bekannten Konditionen).
    """

    __tablename__ = "trading_platform"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    gebuehrenmodell: Mapped[str | None] = mapped_column(String, nullable=True)
    mindestgebuehr_chf: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default=sa.text("0")
    )
    api_handelbar: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )
    vault_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    paper_supported: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=sa.true()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"TradingPlatform(name={self.name!r}, paper_supported={self.paper_supported!r})"


class PlatformAssetClass(Base):
    """Plattform ↔ Anlageklasse + Kosten (M:N, data-model.md §1
    `platform_asset_class`, C-016; AC10/AC11).

    `courtage_pct`/`typ_spread_pct` sind die Referenzdaten-Basis der
    erwarteten Kosten (AC11), die `app.db.trading_platform.
    berechne_erwartete_kosten()` an die (kuenftigen) Sizing-Module liefert.
    `bevorzugt` ist die AC10-Konfiguration der Plattform-Zuordnung je
    Anlageklasse ("Plattform-Zuordnung je Anlageklasse ist Konfiguration,
    s. Spec «Verträge»") — `app.db.trading_platform.
    waehle_plattform_fuer_anlageklasse()` liest ausschliesslich dieses Flag
    (plus die Sonderregel "genau eine Plattform ohne Konkurrenz" fuer
    Anlageklassen mit nur einem konfigurierten Kandidaten), es gibt keine
    zusaetzliche Code-Priorisierung ausserhalb dieser Tabelle.

    `ix_platform_asset_class_asset_class_id` (data-model.md §8: "Plattform-
    Kosten je Klasse") deckt den Filter "welche Plattformen/Kosten fuer
    Anlageklasse X" ab — der Composite-PK (platform_id, asset_class_id)
    unterstuetzt einen reinen `asset_class_id`-Filter allein nicht (nicht
    fuehrender Spaltenteil, analog `DataSourceAssetClass`-Praezedenzfall).
    """

    __tablename__ = "platform_asset_class"
    __table_args__ = (Index("ix_platform_asset_class_asset_class_id", "asset_class_id"),)

    platform_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trading_platform.id"), primary_key=True
    )
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), primary_key=True
    )
    courtage_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    typ_spread_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    bevorzugt: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"PlatformAssetClass(platform_id={self.platform_id!r}, "
            f"asset_class_id={self.asset_class_id!r}, bevorzugt={self.bevorzugt!r})"
        )


# data-model.md §1 `risk_profile`: CHECK name ∈ {...} (C-015, 3 Presets,
# Spec `docs/specs/risikomanagement.md` AC3) — einzige Quelle fuer den
# CHECK-Constraint unten (kein separates hartkodiertes SQL-Duplikat ausserhalb
# der Migration, analog STRATEGY_CLUSTER_VALUES).
RISK_PROFILE_NAMES = ("konservativ", "ausgewogen", "offensiv")
_RISK_PROFILE_NAMES_SQL = ", ".join(repr(name) for name in RISK_PROFILE_NAMES)


class RiskProfile(Base):
    """Risikoprofil — 3 Presets (data-model.md §1 `risk_profile`, C-015;
    Spec `docs/specs/risikomanagement.md` AC3/AC4, Story S-043).

    Reine Stammdaten-Zeile (Name der Profil-Stufe); die eigentlichen
    Grenzwerte je Profil trägt `PortfolioStrategy` (1:1 über
    `risk_profile_id`, siehe dort).
    """

    __tablename__ = "risk_profile"
    __table_args__ = (
        CheckConstraint(f"name IN ({_RISK_PROFILE_NAMES_SQL})", name="ck_risk_profile_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"RiskProfile(id={self.id!r}, name={self.name!r})"


class PortfolioStrategy(Base):
    """Depotstrategie / Makro-Grenzwerte (data-model.md §1 `portfolio_strategy`,
    C-015; Spec `docs/specs/risikomanagement.md` AC1/AC3/AC4/AC11, Story
    S-043).

    Trägt das AC1-Grenzwert-Regelwerk (max. Einzelposition, max. Gewicht je
    Branche/Sektor — GICS, EIN flacher Wert je Depotstrategie statt
    sektor-spezifischer Einzelwerte, siehe Spec-Verträge — sowie die
    Cash-Quote). `gesamt_exposure_cap_pct` ist der AC10-Kelly-Cap-Platzhalter
    (Spalte bereits Teil des bindenden data-model.md-Schemas; die
    eigentliche Gate-Durchsetzung — AC5-AC10 — ist ausserhalb dieser Story).

    `aktiv`: genau eine Zeile darf `aktiv=True` tragen (BR-117). DB-seitig
    durch einen partiellen UNIQUE-Index erzwungen (`ux_portfolio_strategy_
    aktiv`, siehe Migration — bewusst NICHT hier im `__table_args__`
    dupliziert, analog `CategoryWeightVersion`/`AnalysisMethodVersion`:
    reine Migrations-DDL, kein ORM-Autogenerate-Anspruch für diesen
    Index-Typ); App-seitig durch `app.db.depotstrategie.
    waehle_risikoprofil_preset()` (deaktiviert die bisher aktive Zeile,
    bevor die gewählte aktiviert wird — Muster von `app.db.config_versions.
    _markiere_bisherige_version_als_veraltet` übernommen).

    "Nutzer wählt ein Preset" (AC3) heisst strukturell: eine der (per Seed
    vorbereiteten) Presets aktivieren — die übrigen zwei bleiben inaktiv
    verfügbar. "Feinjustieren" (AC3) aktualisiert die Felder der gewählten
    Zeile direkt (In-Place-UPDATE, keine Versionierung — anders als
    `category_weight`/`analysis_method`, die Depotstrategie hat keinen
    AC10-Historienbedarf).
    """

    __tablename__ = "portfolio_strategy"
    __table_args__ = (
        CheckConstraint(
            "max_einzelposition_pct >= 0 AND max_einzelposition_pct <= 100",
            name="ck_portfolio_strategy_max_einzelposition_pct_range",
        ),
        CheckConstraint(
            "max_sektor_pct >= 0 AND max_sektor_pct <= 100",
            name="ck_portfolio_strategy_max_sektor_pct_range",
        ),
        CheckConstraint(
            "cash_quote_ziel_pct >= 0 AND cash_quote_ziel_pct <= 100",
            name="ck_portfolio_strategy_cash_quote_ziel_pct_range",
        ),
        CheckConstraint(
            "gesamt_exposure_cap_pct >= 0 AND gesamt_exposure_cap_pct <= 100",
            name="ck_portfolio_strategy_gesamt_exposure_cap_pct_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    risk_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("risk_profile.id"), nullable=False
    )
    max_einzelposition_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    max_sektor_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    cash_quote_ziel_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    gesamt_exposure_cap_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    aktiv: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"PortfolioStrategy(id={self.id!r}, risk_profile_id={self.risk_profile_id!r}, "
            f"aktiv={self.aktiv!r})"
        )


class PortfolioClassLimit(Base):
    """Klassen-Limit je Depotstrategie (data-model.md §1 `portfolio_class_limit`,
    C-015; Spec `docs/specs/risikomanagement.md` AC1/AC4, Story S-043).

    AC1 "max. Gewicht je Anlageklasse (der 11 Klassen)": eine Zeile je
    (Depotstrategie, Anlageklasse)-Kombination — nicht alle 11 Klassen
    müssen befüllt sein (nur Krypto ist per AC4 mit einem konkreten,
    profilabhängigen Bereich [5-15 %] belegt; die übrigen Klassen bleiben
    unbelegte Konfiguration, siehe Migrations-Docstring — keine coder-eigene
    Erfindung unbelegter Prozentzahlen, analog dem `trading_platform`/
    `platform_asset_class`-Präzedenzfall).

    Bewusst OHNE dedizierten `(asset_class_id)`-Index (data-model.md §8,
    Zeile `strategy`: "analog `risk_profile`/`portfolio_class_limit`-
    Stammdatentabellen" — bei dieser geringen Kardinalität ist ein
    Full-Table-Scan günstiger als ein zusätzlicher Index, sql/R05-Ausnahme).
    """

    __tablename__ = "portfolio_class_limit"
    __table_args__ = (
        CheckConstraint(
            "max_klasse_pct >= 0 AND max_klasse_pct <= 100",
            name="ck_portfolio_class_limit_max_klasse_pct_range",
        ),
    )

    portfolio_strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("portfolio_strategy.id"), primary_key=True
    )
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), primary_key=True
    )
    max_klasse_pct: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"PortfolioClassLimit(portfolio_strategy_id={self.portfolio_strategy_id!r}, "
            f"asset_class_id={self.asset_class_id!r}, max_klasse_pct={self.max_klasse_pct!r})"
        )


class TrialRegistry(Base):
    """Trial-Registry: JEDE an das Validierungs-Gate übergebene Regelvariante
    (data-model.md §6 `trial_registry`, C-012; Spec `docs/specs/lernschleife.md`
    AC3, Story S-059; → BR-118).

    Append-only: jede getestete Variante wird gezählt, auch verworfene —
    ohne diese vollständige Zählung ist die Deflated Sharpe Ratio (AC7,
    Folge-Story) statistisch ungültig. Eine abgelehnte Variante wird
    `archived=True` gesetzt (`app.db.trial_registry.archiviere_trial`),
    **nie gelöscht**.

    **`hypothesis_id` FK auf `rule_hypothesis.id` (nachgerüstet, S-058):**
    data-model.md §6 modelliert `hypothesis_id` als
    `FK → rule_hypothesis.id`; die Migration `e4f7a1c9b2d3` (S-059) legte
    die Spalte mangels existierender `rule_hypothesis`-Tabelle noch ohne
    FK an. Die additive Folge-Migration `3c0ecd3737cb` (S-058) rüstet den
    Constraint nach, sobald `rule_hypothesis` existiert (siehe deren
    Migrations-Docstring).

    **Append-only-Durchsetzung (BR-118), zwei Schichten:**
    - **DB:** die Migration legt unter Postgres einen `BEFORE DELETE`-
      Trigger an, der jede Löschung mit einer Exception verweigert (BR-118
      verlangt nur „kein Delete-Grant", NICHT volle Immutabilität wie
      BR-115/`transaction` — `archived` muss von `false` auf `true`
      wechseln können).
    - **App:** `app.db.trial_registry` bietet ausschliesslich
      `registriere_trial` (Insert), `archiviere_trial` (UPDATE nur der
      `archived`-Spalte) und `anzahl_trials`/`trials_fuer_hypothese`
      (Lesen) an — keine Delete-Methode existiert im Modul.
    """

    __tablename__ = "trial_registry"
    __table_args__ = (
        Index("ix_trial_registry_hypothesis_id", "hypothesis_id"),
        UniqueConstraint(
            "hypothesis_id", "variant_hash", name="uq_trial_registry_hypothesis_variant"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rule_hypothesis.id"), nullable=False
    )
    variant_hash: Mapped[str] = mapped_column(String, nullable=False)
    params: Mapped[Any] = mapped_column(sa.JSON().with_variant(JSONB, "postgresql"), nullable=False)
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa.false()
    )
    tested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"TrialRegistry(hypothesis_id={self.hypothesis_id!r}, "
            f"variant_hash={self.variant_hash!r}, archived={self.archived!r})"
        )


class RuleHypothesis(Base):
    """Regel-Hypothese aus Research (data-model.md §6 `rule_hypothesis`,
    C-012; Spec `docs/specs/lernschleife.md` AC1/AC2, Story S-058).

    Trägt das von AC1 geforderte Mindest-Evidenz-Protokoll
    (`anzahl_faelle`, `zeitraum_von`/`zeitraum_bis`, `signalquelle`,
    `asset_class_id`) sowie `marktlogik` (AC2 — nur marktlogisch
    begründete Muster werden überhaupt als Zeile hier angelegt, siehe
    `app.domain.research.hypothesen_erzeugung.erzeuge_hypothesen`) als
    NOT-NULL-Pflichtfelder — DB-seitige zweite Sicherungsebene neben dem
    Pydantic-Vertrag `app.contracts.research.Hypothese`/
    `Evidenzprotokoll` (→ BR-136).

    **Spec-Präzisierung (S-058):** die ursprüngliche `data-model.md`-
    Fassung dieser Tabelle führte nur `beschreibung`/`params`/
    `free_param_count` — die AC1-Evidenzprotokoll-Felder und `marktlogik`
    wurden bei der Umsetzung dieser Story ergänzt, um den Spec-Vertrag
    "Hypothese (Research → Gate): `{ hypothese_id, beschreibung,
    marktlogik, evidenz{...} }`" vollständig abzubilden (siehe
    `docs/data-model.md` §6).

    `params`/`free_param_count` bleiben wie ursprünglich modelliert:
    Regelparameter-Kandidat der Hypothese und Overfit-Sanity-Zähler:
    Schwellenwert-Auswertung ist NICHT Teil dieser Story (künftige
    Trial-Registry-/Gate-Story)."""

    __tablename__ = "rule_hypothesis"
    __table_args__ = (
        CheckConstraint("anzahl_faelle > 0", name="ck_rule_hypothesis_anzahl_faelle_positive"),
        CheckConstraint(
            "zeitraum_bis >= zeitraum_von", name="ck_rule_hypothesis_zeitraum_konsistent"
        ),
        Index("ix_rule_hypothesis_asset_class_id", "asset_class_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    beschreibung: Mapped[str] = mapped_column(String, nullable=False)
    marktlogik: Mapped[str] = mapped_column(String, nullable=False)
    anzahl_faelle: Mapped[int] = mapped_column(Integer, nullable=False)
    zeitraum_von: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    zeitraum_bis: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signalquelle: Mapped[str] = mapped_column(String, nullable=False)
    asset_class_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("asset_class.id"), nullable=False
    )
    params: Mapped[Any] = mapped_column(sa.JSON().with_variant(JSONB, "postgresql"), nullable=False)
    free_param_count: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return (
            f"RuleHypothesis(id={self.id!r}, beschreibung={self.beschreibung!r}, "
            f"asset_class_id={self.asset_class_id!r})"
        )
