"""No-Evidence-No-Trade (AC6, Spec `docs/specs/llm-grounding.md`, BR-005,
C-008 Sicherung geteilt mit [[analyse-framework]]).

Fehlt für eine der 5 Analysekategorien (`AnalyseScores`) die
Datengrundlage — der Score trägt den Platzhalter `"fehlt"` statt einer
Zahl 0–10 — wird dieser Score **nie** durch eine LLM-Schätzung ersetzt;
stattdessen wird der **gesamte Titel übersprungen** (kein Gesamtscore,
kein Signal — deckt E3). `analyse-framework` AC8 formuliert dieselbe
Regel für den Fall "jeder Methodenscore einer Kategorie fehlt"; dieses
Modul entscheidet ausschließlich anhand des bereits verdichteten
`AnalyseScores`-DTOs (Ergebnis von Grounding + Cross-Check, S-012/S-013),
nicht anhand der zugrundeliegenden Methodenscores selbst.

Bewusst in `app/domain/` (reiner Kern, keine I/O, kein LLM, P1/P3,
architecture.md §4) statt in `app/adapters/llm/`: die Regel wird künftig
auch von `domain/scoring` (analyse-framework, noch nicht gebaut)
konsumiert werden — `domain/**` darf laut Boundary-Regel nicht
`app.adapters.*` importieren, ein gemeinsamer Ort dort wäre für den
künftigen Scoring-Konsumenten also nicht erreichbar.

Jeder Übersprung wird protokolliert (AC10, `app.core.audit_log`, geteilter
Sink mit S-012/S-013).

NICHT Teil dieser Story (Nicht-Ziele der Spec): keine Score-Berechnung,
kein Gesamtscore, kein Signal (→ [[analyse-framework]]) — nur die
Ja/Nein-Weiche "Titel überspringen oder nicht".
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.contracts.llm_grounding import AnalyseScores, EvidenzErgebnis, ProtokollEintrag
from app.core.audit_log import protokolliere

#: Die 5 Analysekategorien (Spec-Reihenfolge "fundamental, technisch,
#: qualitativ, makro, risiko") als Attributnamen von `AnalyseScores`.
_KATEGORIEN: tuple[str, ...] = ("fundamental", "technisch", "qualitativ", "makro", "risiko")


def pruefe_evidenzlage(scores: AnalyseScores, *, titel: str | None = None) -> EvidenzErgebnis:
    """Prüft, ob alle 5 Analysekategorien einen echten Score (0–10) tragen
    (AC6). Fehlt mindestens einer Kategorie die Datengrundlage (Score
    `"fehlt"`), wird der Titel übersprungen — der fehlende Score wird NIE
    durch eine LLM-Schätzung ersetzt — und der Übersprung protokolliert
    (AC10). `titel` ist optional (nur für den Protokoll-Detailtext); fehlt
    er, bleibt der Eintrag ohne Titel-Referenz auditierbar."""
    fehlende_kategorien = tuple(kat for kat in _KATEGORIEN if getattr(scores, kat) == "fehlt")

    if not fehlende_kategorien:
        return EvidenzErgebnis(status="vollstaendig")

    titel_praefix = f"Titel {titel!r} " if titel else "Titel "
    detail = (
        f"{titel_praefix}übersprungen (No-Evidence-No-Trade): fehlende "
        f"Datengrundlage in Kategorie(n) {', '.join(fehlende_kategorien)}."
    )
    eintrag = ProtokollEintrag(
        zeitpunkt=datetime.now(UTC),
        grund="keine_evidenz",
        kennzahl_typ=fehlende_kategorien[0],
        quellen_id=None,
        detail=detail,
    )
    protokolliere(eintrag)
    return EvidenzErgebnis(
        status="uebersprungen",
        fehlende_kategorien=fehlende_kategorien,
        protokoll_eintrag=eintrag,
    )
