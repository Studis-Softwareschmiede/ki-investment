"""Modul-Verträge Lernschleife — Validierungs-Gate Stufe A (historisch,
Story S-060, AC4/AC5/AC6/AC7) und Stufe B (Paper-Bewährung, Story S-061,
AC8/AC9), Spec `docs/specs/lernschleife.md`, → `docs/data-model.md` §6.

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet
den Verträge-Abschnitt der Spec ab:

- **`TradeErgebnis`** — ein einzelner, abgeschlossener historischer Trade
  einer Hypothesen-Variante (Datum + Rendite), Eingabe für Stufe A. Kommt
  aus der Point-in-Time-sauberen Historie (Spec-Abhängigkeit
  "Point-in-Time-saubere Historie"), deren Beschaffung ausserhalb dieser
  Story liegt — `app.domain.lernschleife.stage_a` konsumiert nur bereits
  aufbereitete Trades.
- **`StufeAKonfiguration`** — die laut AC12 konfigurierbaren Schwellen, die
  Stufe A betreffen (Mindest-Stichprobe, Bewertungs-Untergrenze,
  Embargo-Dauer, WF-Effizienz-Schwelle); die genannten Werte sind die
  beschlossenen Defaults.
- **`WalkForwardSplitErgebnis`** — ein einzelner sequentieller
  Walk-Forward-Split (Trainings-/Validierungsfenster + deren Renditen,
  AC5/AC6).
- **`StufeAReport`** — der volle Output-Vertrag aus der Spec ("Stufe-A-
  Report: `{ n_trades, walk_forward_effizienz, embargo_tage, dsr }`"),
  ergänzt um das Bewertungsergebnis (`ergebnis`) und eine `begruendung`
  (analog `docs/data-model.md` §6 `gate_result.begruendung`) — beide sind
  in dieser Story notwendig, um AC4 ("nicht bewertet" vs. "durchgefallen"
  vs. "bestanden") und AC6 ("besteht Stufe A nicht") überhaupt abbilden zu
  können; die Spec nennt diese Zustände in Fliesstext (Main Success
  Scenario Schritt 4-5, Alternative Flows A2/A3), auch wenn der
  "Verträge"-Abschnitt nur die vier Metrik-Felder explizit auflistet.
- **`StufeBKonfiguration`** — die laut AC12 konfigurierbare Schwelle, die
  Stufe B betrifft (`psr_schwelle`, AC8); Default ist der von der Spec
  beschlossene Wert (95%).
- **`StufeBReport`** — der volle Output-Vertrag von Stufe B (Spec
  "Verträge": `{ psr, benchmark_sharpe (=0), mintrl_restlaufzeit }`),
  ergänzt um `hypothesis_id`, `n_trades`, `psr_schwelle`, `psr_bestanden`
  (AC8-Bestehen-Flag: PSR >= Schwelle) und `begruendung` (Audit-Trail
  analog `StufeAReport`). `psr`/`mintrl_restlaufzeit` sind `None`, wenn
  die zugrunde liegende Renditeverteilung degeneriert ist (< 2 Trades,
  Standardabweichung 0, Sharpe Ratio 0) — analog der S-060-DSR-
  Robustheits-Konvention wird dann kontrolliert gewertet statt
  abzustürzen (siehe `app.domain.lernschleife.stage_b`).

**Bewusst NICHT Teil dieser Story:** `ampel` (AC10/AC11, S-062) — dieses
Feld gehört zu `gate_result` (`docs/data-model.md` §6), dessen Persistenz
(inkl. der `psr`/`min_trl`-Spalten) laut Ampel-Umsetzung (AC10/AC11)
weiterhin S-062-Scope ist (kein Gold-Plating über AC8/AC9 hinaus). S-061
(unten: `StufeBKonfiguration`, `StufeBReport`) liefert PSR/MinTRL als
reinen Domain-Kern-Output (P1, kein I/O/DB) — die DB-Spalten `gate_result.
psr`/`gate_result.min_trl` entstehen erst mit der `gate_result`-Migration
in S-062.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: AC4-Bewertungsergebnis einer Hypothese in Stufe A.
#: - "bestanden": Stichprobe ausreichend, WFE-Schwelle erfüllt.
#: - "durchgefallen": entweder Stichprobe im Bereich
#:   [bewertungsuntergrenze, mindest_stichprobe) ("A3, aber gezählt") oder
#:   WFE-Schwelle unterschritten (AC6, Overfit-Verdacht).
#: - "nicht_bewertet": Stichprobe < bewertungsuntergrenze — kein Urteil,
#:   keine Übernahme (AC4/A3).
StufeAErgebnis = Literal["bestanden", "durchgefallen", "nicht_bewertet"]


class TradeErgebnis(BaseModel):
    """Ein abgeschlossener historischer Trade einer Hypothesen-Variante —
    Eingabe für Stufe A (`datum` = Referenzzeitpunkt für Walk-Forward-
    Sequenzierung/Embargo, `rendite_pct` = Trade-Rendite in Prozent,
    analog `docs/data-model.md`-Konvention "Prozente/Scores:
    NUMERIC(6,3)")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    datum: datetime
    rendite_pct: Decimal


class StufeAKonfiguration(BaseModel):
    """AC12-Schwellen, die Stufe A betreffen — konfigurierbar, Defaults
    sind die von der Spec beschlossenen Werte:

    - `mindest_stichprobe` (AC4): ≥ diese Anzahl Trades → Hypothese wird
      bewertet.
    - `bewertungsuntergrenze` (AC4/A3): < diese Anzahl Trades → gar nicht
      bewertet (kein Urteil).
    - `embargo_tage` (AC5): Embargo zwischen Trainings- und
      Validierungsfenster.
    - `wfe_schwelle` (AC6): Mindest-Walk-Forward-Effizienz.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mindest_stichprobe: int = Field(default=100, gt=0)
    bewertungsuntergrenze: int = Field(default=30, gt=0)
    embargo_tage: int = Field(default=30, ge=0)
    wfe_schwelle: Decimal = Field(default=Decimal("0.5"))


class WalkForwardSplitErgebnis(BaseModel):
    """Ein einzelner sequentieller Walk-Forward-Split (AC5): Trainings-
    und Validierungsfenster (durch das Embargo getrennt) mit ihrer
    jeweiligen kumulierten Rendite (Basis für AC6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    split_index: int = Field(ge=0)
    train_von: datetime
    train_bis: datetime
    validierung_von: datetime
    validierung_bis: datetime
    n_trades_train: int = Field(ge=0)
    n_trades_validierung: int = Field(ge=0)
    is_rendite: Decimal
    oos_rendite: Decimal


class StufeAReport(BaseModel):
    """Der volle Output-Vertrag von Stufe A (Spec "Verträge": `{ n_trades,
    walk_forward_effizienz, embargo_tage, dsr }`), ergänzt um
    `hypothesis_id`, `ergebnis`, `begruendung` und `splits` (Audit-Trail
    der einzelnen Walk-Forward-Splits, AC5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: uuid.UUID
    n_trades: int = Field(ge=0)
    embargo_tage: int = Field(ge=0)
    walk_forward_effizienz: Decimal | None = None
    dsr: Decimal | None = None
    ergebnis: StufeAErgebnis
    begruendung: str
    splits: list[WalkForwardSplitErgebnis] = Field(default_factory=list)


class StufeBKonfiguration(BaseModel):
    """AC12-Schwelle, die Stufe B betrifft — konfigurierbar, Default ist
    der von der Spec beschlossene Wert:

    - `psr_schwelle` (AC8): Probabilistic Sharpe Ratio (gegen Benchmark-
      Sharpe 0) muss >= diese Schwelle sein, damit Stufe B besteht.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    psr_schwelle: Decimal = Field(default=Decimal("0.95"))


class StufeBReport(BaseModel):
    """Der volle Output-Vertrag von Stufe B (Spec "Verträge": `{ psr,
    benchmark_sharpe (=0), mintrl_restlaufzeit }`), ergänzt um
    `hypothesis_id`, `n_trades`, `psr_schwelle`, `psr_bestanden` (AC8:
    PSR >= Schwelle) und `begruendung` (Audit-Trail analog
    `StufeAReport`).

    `psr`/`mintrl_restlaufzeit` sind `None`, wenn die zugrunde liegende
    Renditeverteilung degeneriert ist (< 2 Trades, Standardabweichung 0,
    Sharpe Ratio 0) — die Bewertung bricht dann NICHT ab, sondern weist
    dies kontrolliert aus (analog der S-060-DSR-Robustheits-Konvention,
    `psr_bestanden` ist in diesem Fall `False`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: uuid.UUID
    n_trades: int = Field(ge=0)
    psr: Decimal | None = None
    benchmark_sharpe: Decimal = Decimal("0")
    psr_schwelle: Decimal
    psr_bestanden: bool
    mintrl_restlaufzeit: timedelta | None = None
    begruendung: str
