"""Modul-Verträge Analyse-Pipelines — Buy-/Sell-Signal (S-028/S-034, C-011).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet die
Output-Verträge aus `docs/specs/analyse-pipelines.md` ab:

- `BuySignal` — "(a) Output neue Titel": `{ titel_id, gesamtscore,
  kategorie_scores, fakten_mit_quellen, zeitstempel }`, Ausgabe von
  `app.domain.analysis_new.buy_pfad.bewerte_kandidat` (AC1, AC2), zur
  Übergabe an das (noch nicht gebaute) Position-Sizing (`[[sizing]]`,
  Nicht-Ziel dieser Story).
- `SellSignal` — "(b) Output bestehende Titel" (S-034, AC5-AC7): `{
  titel_id, dringlichkeit, ausloeser, rohwerte, zeitstempel }`, Ausgabe von
  `app.domain.analysis_existing.sell_pfad.bewerte_bestehenden_titel`, zur
  Übergabe an das (noch nicht gebaute) Exit-Sizing (`[[sizing]]`,
  Nicht-Ziel dieser Story).

`kategorie_scores` reicht `app.contracts.analyse_framework.KategorieScores`
durch (Score-Engine, S-010) statt eine eigene, redundante DTO-Kopie zu
definieren; `fakten_mit_quellen` reicht `app.contracts.llm_grounding
.AnalyseFakt` durch (Grounding, S-012/S-013) — beide Vorgänger-Verträge
gelten für den Buy-Pfad unverändert (AC3: für jede referenzierte Zahl
gelten die LLM-Grounding-Verträge).

Die strukturelle Pfad-Trennung aus AC2 ("ein Buy-Pfad erzeugt nie ein
Sell-Signal und umgekehrt") ist dadurch erkennbar, dass `BuySignal` und
`SellSignal` disjunkte DTOs ohne gemeinsame Felder-Obermenge sind (kein
Basis-/Union-Typ) und aus zwei getrennten Domain-Paketen stammen
(`domain/analysis_new` bzw. `domain/analysis_existing`, architecture.md §4).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.analyse_framework import KategorieScores
from app.contracts.llm_grounding import AnalyseFakt

#: AC7: die zwei Dringlichkeitsstufen eines Sell-Signals (Verträge "(b)
#: Output bestehende Titel").
Dringlichkeit = Literal["hard", "soft"]


class BuySignal(BaseModel):
    """Buy-Signal → Position-Sizing (Verträge, Spec `analyse-pipelines`,
    AC1/AC2): entsteht ausschließlich, wenn `app.domain.analysis_new
    .buy_pfad.bewerte_kandidat` nach Score-Berechnung (`analyse-framework`)
    und Risiko-Sanity-Cap das Signal KAUF ermittelt (Gesamtscore ≥ 8, AC1).

    `fakten_mit_quellen` sind die im Output referenzierten, bereits über
    das LLM-Grounding-Gate + den deterministischen Zahlen-Cross-Check
    geerdeten Fakten (AC3) — jede trägt Quellen-ID + Zeitstempel
    (`AnalyseFakt`, S-012/S-013).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    gesamtscore: float = Field(ge=0, le=10)
    kategorie_scores: KategorieScores
    fakten_mit_quellen: tuple[AnalyseFakt, ...] = Field(default=())
    zeitstempel: datetime


class SellSignal(BaseModel):
    """Sell-Signal → Exit-Sizing (Verträge, Spec `analyse-pipelines`,
    AC5/AC6/AC7): entsteht ausschließlich, wenn `app.domain.analysis_existing
    .sell_pfad.bewerte_bestehenden_titel` ein eingehendes `UeberwachungsEreignis`
    (aus `[[depot-ueberwachung]]`) gegen die beim Kauf fixierten Exit-Regeln
    des Titels auswertet (AC5, BR-011: "kein moving the goalposts").

    `dringlichkeit` (AC7, BR-012): `"hard"`, wenn die Kauf-These fundamental
    gebrochen ist (mindestens: Hack, Betrug, Delisting, Insolvenz) →
    "sofort"; sonst `"soft"` bei Verschlechterung ohne Katastrophe →
    "gestaffelt möglich". `ausloeser` ist der auslösende Ereignistyp
    (`app.contracts.depot_ueberwachung.Ereignistyp`); `rohwerte` sind die
    unverändert durchgereichten Rohwerte des auslösenden
    `UeberwachungsEreignis` (Audit-Trail, analog `UeberwachungsEreignis
    .rohwerte`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    dringlichkeit: Dringlichkeit
    ausloeser: str = Field(min_length=1)
    rohwerte: dict[str, str] = Field(default_factory=dict)
    zeitstempel: datetime


__all__ = ["BuySignal", "Dringlichkeit", "SellSignal"]
