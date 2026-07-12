"""Modul-Verträge Analyse-Pipelines — Buy-Signal (S-028, C-011).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet den
Output-Vertrag aus `docs/specs/analyse-pipelines.md` ("Verträge — (a) Output
neue Titel") für den Buy-Pfad ab:

- `BuySignal` — `{ titel_id, gesamtscore, kategorie_scores, fakten_mit_quellen,
  zeitstempel }`, Ausgabe von `app.domain.analysis_new.buy_pfad.bewerte_kandidat`
  (AC1, AC2), zur Übergabe an das (noch nicht gebaute) Position-Sizing
  (`[[sizing]]`, Nicht-Ziel dieser Story).

`kategorie_scores` reicht `app.contracts.analyse_framework.KategorieScores`
durch (Score-Engine, S-010) statt eine eigene, redundante DTO-Kopie zu
definieren; `fakten_mit_quellen` reicht `app.contracts.llm_grounding
.AnalyseFakt` durch (Grounding, S-012/S-013) — beide Vorgänger-Verträge
gelten für den Buy-Pfad unverändert (AC3: für jede referenzierte Zahl
gelten die LLM-Grounding-Verträge).

Der Sell-Pfad (AC5–AC10, spätere Story S-034) hat KEIN Gegenstück in diesem
Modul — die strukturelle Pfad-Trennung aus AC2 ("ein Buy-Pfad erzeugt nie
ein Sell-Signal") ist dadurch erkennbar, dass hier ausschließlich ein
Buy-Signal-DTO existiert.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.analyse_framework import KategorieScores
from app.contracts.llm_grounding import AnalyseFakt


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
