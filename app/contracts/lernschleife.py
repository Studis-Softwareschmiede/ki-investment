"""Modul-Verträge Lernschleife — Validierungs-Gate Stufe A (historisch)
(Story S-060, Spec `docs/specs/lernschleife.md` AC4/AC5/AC6/AC7, →
`docs/data-model.md` §6).

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

**Bewusst NICHT Teil dieser Story:** `ampel` (AC10/AC11, S-062), `psr`/
`min_trl` (AC8/AC9, S-061) — diese Felder gehören zu `gate_result`
(`docs/data-model.md` §6), das laut §11-Migrationsreihenfolge nach
`rule_hypothesis` (S-058, noch offen) kommt und deshalb hier bewusst noch
nicht angelegt wird (kein Gold-Plating über AC4-AC7 hinaus).
"""

from __future__ import annotations

import uuid
from datetime import datetime
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
