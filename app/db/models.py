"""ORM-Modelle — 1:1 aus docs/data-model.md (`dba`-Detailkonzept, bindend).

Diese Datei bildet bislang nur die von der laufenden Story benoetigten Tabellen ab;
weitere Entitaeten aus data-model.md kommen ueber Folge-Stories dazu (P6/ADR-008:
Anlageklassen sind Konfiguration, keine Code-Grenze).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Interval,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
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

# data-model.md §4 `strategy`: CHECK cluster ∈ {...} (C-014, 18 Strategien/4 Cluster).
# Seed der 18 Strategien je Cluster ist NICHT Teil dieser Story (S-015) —
# das Depotmodul zieht `strategy`/`time_horizon` hier nur als leere
# FK-Voraussetzung für `position` mit (analog zur `analysis_category`-
# Voraussetzung aus S-004/2da446925bbc); Katalog-Inhalt + Cluster-Gate sind
# S-037 (Spec `strategie-exit-regeln`, AC2/AC3).
STRATEGY_CLUSTER_VALUES = (
    "passiv_regelbasiert",
    "aktiv_fundamental",
    "aktiv_technisch_makro",
    "professionell_algo",
)

# data-model.md §4 `strategy`: CHECK stufe ∈ {...}
STRATEGY_STUFE_VALUES = ("MVP", "Stufe2", "Stufe3", "Stufe4")

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

# data-model.md §4 `exit_rule`: CHECK stop_typ ∈ {...}
EXIT_RULE_STOP_TYP_VALUES = ("fix_pct", "atr_trailing", "fundamental", "keiner")

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


class Strategy(Base):
    """Anlagestrategie (data-model.md §1 `strategy`, C-014, 18 Strategien in
    4 Clustern).

    **Leeres** Schema als FK-Voraussetzung für `Position.strategy_id`
    (S-015, Begründung analog zu `Instrument` oben) — der 18er-Katalog samt
    Cluster-Freischaltung (MVP nur „Passiv/Regelbasiert") ist S-037 (Spec
    `strategie-exit-regeln`, AC2), NICHT Teil dieser Story.
    """

    __tablename__ = "strategy"
    __table_args__ = (
        CheckConstraint(
            "cluster IN ('passiv_regelbasiert', 'aktiv_fundamental', "
            "'aktiv_technisch_makro', 'professionell_algo')",
            name="ck_strategy_cluster",
        ),
        CheckConstraint("stufe IN ('MVP', 'Stufe2', 'Stufe3', 'Stufe4')", name="ck_strategy_stufe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    cluster: Mapped[str | None] = mapped_column(String, nullable=True)
    stufe: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"Strategy(name={self.name!r}, cluster={self.cluster!r})"


class TimeHorizon(Base):
    """Zeithorizont (data-model.md §1 `time_horizon`, C-014, 9 Stufen).

    **Leeres** Schema als FK-Voraussetzung für `Position.time_horizon_id`
    (S-015, Begründung analog zu `Instrument`/`Strategy` oben) — die 9
    Stufen samt Break-Even-Hinweis sind S-037 (Spec `strategie-exit-regeln`,
    AC3), NICHT Teil dieser Story.
    """

    __tablename__ = "time_horizon"
    __table_args__ = (CheckConstraint("id BETWEEN 1 AND 9", name="ck_time_horizon_id_range"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    break_even_hinweis: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover — Debug-Hilfe, kein Verhalten
        return f"TimeHorizon(id={self.id!r}, name={self.name!r})"


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

    1:1 zu `Position` über `position_id`. Diese Story (S-015) liefert nur
    das Schema als Teil des Positions-Grundgerüsts (AC1 „Exit-Regeln" als
    Position-Attribut) — die inhaltliche Ableitung der Werte (Default-
    Exit-Set je Strategie/Klasse, ATR-Multiplikatoren) ist
    `strategie-exit-regeln` (S-038, AC6-AC9); die BR-111-Unveränderlichkeit
    (kein UPDATE nach Position-Open) durchzusetzen ist S-040
    („Attribut-Bündel-Fixierung, Unveränderlichkeit") — hier NICHT
    umgesetzt, um nicht in eine andere Story-Spec vorzugreifen.
    """

    __tablename__ = "exit_rule"
    __table_args__ = (
        CheckConstraint(
            "stop_typ IN ('fix_pct', 'atr_trailing', 'fundamental', 'keiner')",
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
