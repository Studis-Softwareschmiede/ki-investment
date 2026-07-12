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

Zusätzlich (S-013, AC10): beide Ablehnungspfade dieser Story
(`schema_verletzung`, `input_fremde_zahl`) hängen jetzt an
`app.core.audit_log.protokolliere` — jede Ablehnung erzeugt einen
`ProtokollEintrag` (Grund, Zeitpunkt, betroffene Kennzahl/Quelle, soweit
bekannt).

NICHT Teil dieser Story (Nicht-Ziele der Spec, spätere Stories): der
deterministische Zahlen-Cross-Check gegen Originalquellen liegt in
`app.adapters.llm.cross_check` (AC4/AC5, S-013); No-Evidence-No-Trade
(AC6, geteilte Regel mit [[analyse-framework]]) liegt in
`app.domain.no_evidence_no_trade` (S-014); der Halluzinations-KPI (AC8/AC9)
folgt in einer späteren Story — `GroundingErgebnis` liefert dafür lediglich
die strukturierte Grundlage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.contracts.llm_grounding import (
    AnalyseInput,
    AnalyseOutput,
    GroundingAblehnungsgrund,
    GroundingErgebnis,
    ProtokollEintrag,
)
from app.core.audit_log import protokolliere


def _protokolliere_ablehnung(
    *,
    grund: GroundingAblehnungsgrund,
    detail: str,
    kennzahl_typ: str | None = None,
    quellen_id: str | None = None,
) -> None:
    """Schreibt eine Ablehnung des Grounding-Gates ins Audit-Protokoll
    (AC10) — `grund` ist eine Teilmenge des breiteren `ProtokollGrund`-
    Vokabulars (auch vom Cross-Check-Modul geteilt, S-013)."""
    protokolliere(
        ProtokollEintrag(
            zeitpunkt=datetime.now(UTC),
            grund=grund,
            kennzahl_typ=kennzahl_typ,
            quellen_id=quellen_id,
            detail=detail,
        )
    )


def pruefe_grounding(output_roh: dict[str, Any], eingabe: AnalyseInput) -> GroundingErgebnis:
    """Validiert einen rohen Analyse-Output-Kandidaten gegen das feste
    Schema (AC3 — deckt über die Pflichtfelder von `AnalyseFakt` auch AC1
    mit ab) und gegen die Input-Bindung (AC2). Liefert immer ein
    strukturiertes `GroundingErgebnis` — nie eine durchgereichte Exception.
    Jede Ablehnung wird zusätzlich ins Audit-Protokoll geschrieben (AC10)."""
    try:
        output = AnalyseOutput.model_validate(output_roh)
    except ValidationError as exc:
        detail = str(exc)
        _protokolliere_ablehnung(grund="schema_verletzung", detail=detail)
        return GroundingErgebnis(status="abgelehnt", grund="schema_verletzung", detail=detail)

    input_fakten = set(eingabe.fakten)
    for fakt in output.fakten:
        if fakt not in input_fakten:
            detail = (
                f"Fakt {fakt.kennzahl_typ}={fakt.wert} (Quelle {fakt.quellen_id}, "
                f"{fakt.timestamp.isoformat()}) kommt nicht im strukturierten Input vor."
            )
            _protokolliere_ablehnung(
                grund="input_fremde_zahl",
                detail=detail,
                kennzahl_typ=fakt.kennzahl_typ,
                quellen_id=fakt.quellen_id,
            )
            return GroundingErgebnis(status="abgelehnt", grund="input_fremde_zahl", detail=detail)

    return GroundingErgebnis(status="geerdet", output=output)
