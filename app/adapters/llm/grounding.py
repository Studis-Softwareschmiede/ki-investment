"""LLM-Grounding-Gate (C-008, architecture.md ADR-003 · Querschnitt).

Sitzt architektonisch VOR dem eigentlichen LLM-Adapter-Aufruf
("LLM-Adapter HINTER dem Grounding-Gate", architecture.md §4) — validiert
den rohen (untrusted) Analyse-Output-Kandidaten einer LLM-Antwort, bevor er
an einen Konsumenten (`domain/analysis_new`, `domain/analysis_existing`,
folgen in späteren Stories) weitergereicht wird.

Diese Story (S-012) deckt genau drei der fünf C-008-Sicherungen ab:

- **AC1 Grounding-Pflicht** — jede referenzierte Zahl trägt Quellen-ID +
  Timestamp (durchgesetzt über `AnalyseFakt`, `app.contracts.llm_grounding`
  — ein Fakt ohne eines von beiden lässt sich gar nicht erst instanziieren).
- **AC2 Input-Bindung** — jede Zahl im Output muss exakt (kennzahl_typ,
  wert, quellen_id, timestamp) auf eine Zahl im strukturierten Input
  rückführbar sein; eine input-fremde Zahl führt zur Ablehnung.
- **AC3 Strukturierter Output** — der Output wird gegen das feste
  JSON-Schema aus `AnalyseOutput` validiert (deckt E1).

NICHT Teil dieser Story (Nicht-Ziele der Spec, spätere Stories): der
deterministische Zahlen-Cross-Check gegen Originalquellen (AC4/AC5), No-
Evidence-No-Trade (AC6, [[analyse-framework]]), der Halluzinations-KPI
(AC8/AC9) und die Protokollierung (AC10) — `GroundingErgebnis` liefert dafür
lediglich die strukturierte Grundlage.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.contracts.llm_grounding import AnalyseInput, AnalyseOutput, GroundingErgebnis


def pruefe_grounding(output_roh: dict[str, Any], eingabe: AnalyseInput) -> GroundingErgebnis:
    """Validiert einen rohen Analyse-Output-Kandidaten gegen das feste
    Schema (AC3 — deckt über die Pflichtfelder von `AnalyseFakt` auch AC1
    mit ab) und gegen die Input-Bindung (AC2). Liefert immer ein
    strukturiertes `GroundingErgebnis` — nie eine durchgereichte Exception."""
    try:
        output = AnalyseOutput.model_validate(output_roh)
    except ValidationError as exc:
        return GroundingErgebnis(status="abgelehnt", grund="schema_verletzung", detail=str(exc))

    input_fakten = set(eingabe.fakten)
    for fakt in output.fakten:
        if fakt not in input_fakten:
            return GroundingErgebnis(
                status="abgelehnt",
                grund="input_fremde_zahl",
                detail=(
                    f"Fakt {fakt.kennzahl_typ}={fakt.wert} (Quelle {fakt.quellen_id}, "
                    f"{fakt.timestamp.isoformat()}) kommt nicht im strukturierten Input vor."
                ),
            )

    return GroundingErgebnis(status="geerdet", output=output)
