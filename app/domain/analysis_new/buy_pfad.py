"""Buy-Pfad — Analyse neue Titel (S-028, Spec `docs/specs/analyse-pipelines.md`).

`bewerte_kandidat` deckt das Main Success Scenario (a) der Spec (Schritte
2–4):

- **AC1** — Gesamtscore über das gemeinsame Framework
  (`app.domain.scoring.score_engine`, S-010); Buy-Signal genau dann, wenn
  das nach dem Risiko-Sanity-Cap ermittelte Signal KAUF ist (Gesamtscore
  ≥ 8 UND kein Cap-Downgrade — der Sanity-Cap kann ein rechnerisches KAUF
  auf HALTEN deckeln, Edge-Cases der Spec). Bei jedem anderen Signal
  (deckt A2: BEOBACHTEN/HALTEN/REDUZIEREN/VERKAUF) entsteht kein
  Buy-Signal (`None`).
- **AC2** — das erzeugte `BuySignal` (`app.contracts.analyse_pipelines
  .BuySignal`) enthält Titel + Gesamtscore + Kategorie-Scores + geerdete
  Fakten + Zeitstempel — bereit zur Übergabe an das (noch nicht gebaute)
  Position-Sizing. Die Pfad-Trennung ist strukturell: dieses Modul kennt
  keinen Sell-Signal-Typ und kann daher nie einen erzeugen.
- **AC3** — `analyse` ist eine bereits über das LLM-Grounding-Gate
  geerdete `AnalyseOutput` (Schema-Validierung + Input-Bindung, S-012;
  deterministischer Zahlen-Cross-Check, S-013) — dieses Modul selbst
  ruft kein LLM auf (Buy-Signal-Erzeugung ist deterministisch, harte NFR
  der Spec) und reicht `analyse.fakten` unverändert als
  `fakten_mit_quellen` durch.
- **AC4** — No-Evidence-No-Trade (`app.domain.no_evidence_no_trade
  .pruefe_evidenzlage`, S-014, geteilte Regel mit `analyse-framework`
  AC8): fehlt einer der 5 Analysekategorien die Datengrundlage
  (`AnalyseScores`-Wert `"fehlt"`), wird der Titel übersprungen — `None`,
  kein Gesamtscore, keine LLM-Schätzung als Ersatz.
"""

from __future__ import annotations

from datetime import datetime

from app.contracts.analyse_framework import (
    KATEGORIE_NAMEN,
    Kategoriegewichte,
    KategorieScores,
    ScoreSchwellen,
)
from app.contracts.analyse_pipelines import BuySignal
from app.contracts.llm_grounding import AnalyseOutput, AnalyseScores
from app.domain.no_evidence_no_trade import pruefe_evidenzlage
from app.domain.scoring.score_engine import (
    berechne_gesamtscore,
    leite_signal_ab,
    wende_risiko_sanity_cap_an,
)

#: Identisch zum Default in `score_engine` (dort einzige Quelle der
#: Wahrheit für AC7 aus `analyse-framework`) — hier nur als Parameter-
#: Default durchgereicht, damit Aufrufer diese Funktion ohne
#: Score-Engine-Detailwissen aufrufen können.
_RISIKO_CAP_SCHWELLE_DEFAULT = 3.0


def _zu_kategorie_scores(scores: AnalyseScores) -> KategorieScores:
    """Wandelt eine bereits vollständige (kein `"fehlt"`) `AnalyseScores`
    (Grounding-Vertrag, S-012) in eine `KategorieScores` (Score-Engine-
    Vertrag, S-010) um — beide DTOs tragen dieselben 5 Kategorie-Felder
    (`fundamental, technisch, qualitativ, makro, risiko`), stammen aber aus
    unterschiedlichen Spec-Verträgen (`llm-grounding` vs. `analyse-framework`)
    und werden bewusst nicht strukturell vermischt (architecture.md P2).

    Der Aufrufer garantiert Vollständigkeit: `bewerte_kandidat` ruft dies
    erst, nachdem `pruefe_evidenzlage` `status == "vollstaendig"` bestätigt
    hat (AC4) — kein Feld ist zu diesem Zeitpunkt `"fehlt"`.
    """
    werte = {kategorie: getattr(scores, kategorie) for kategorie in KATEGORIE_NAMEN}
    return KategorieScores(**werte)


def bewerte_kandidat(
    titel_id: str,
    analyse: AnalyseOutput,
    kategoriegewichte: Kategoriegewichte,
    zeitstempel: datetime,
    schwellen: ScoreSchwellen | None = None,
    risiko_cap_schwelle: float = _RISIKO_CAP_SCHWELLE_DEFAULT,
) -> BuySignal | None:
    """Bewertet einen Kandidaten und liefert ein `BuySignal` oder `None`.

    `analyse` MUSS bereits das LLM-Grounding-Gate (Schema + Input-Bindung,
    AC1–AC3 der Spec `llm-grounding`) sowie den deterministischen
    Zahlen-Cross-Check (AC4 ebenda) erfolgreich durchlaufen haben — dieses
    Modul führt beides nicht selbst aus (kein `app.adapters.llm`-Import;
    Buy-Signal-Erzeugung bleibt deterministisch, AC3 dieser Spec).
    `zeitstempel` wird explizit übergeben statt intern per Systemzeit
    ermittelt (architecture.md P3: keine Systemzeit-Abhängigkeit im
    deterministischen Order-Pfad außer explizitem `as_of`-Timestamp).
    """
    evidenz = pruefe_evidenzlage(analyse.scores, titel=titel_id)
    if evidenz.status == "uebersprungen":
        return None

    kategorie_scores = _zu_kategorie_scores(analyse.scores)
    gesamtscore = berechne_gesamtscore(kategorie_scores, kategoriegewichte)
    signal_vor_cap = leite_signal_ab(gesamtscore, schwellen)
    signal, _sanity_cap_angewendet = wende_risiko_sanity_cap_an(
        signal_vor_cap, kategorie_scores.risiko, risiko_cap_schwelle
    )

    if signal != "KAUF":
        return None

    return BuySignal(
        titel_id=titel_id,
        gesamtscore=gesamtscore,
        kategorie_scores=kategorie_scores,
        fakten_mit_quellen=analyse.fakten,
        zeitstempel=zeitstempel,
    )
