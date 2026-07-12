"""Audit-Protokoll für abgelehnte/verworfene Analysen (AC10, Spec
`docs/specs/llm-grounding.md`).

Cross-Cutting-Helfer in `app/core/` (architecture.md §4: "core/ ...
logging"). Nimmt für **jede** Ablehnung entlang des LLM-Grounding-Pfads
einen `ProtokollEintrag` (Grund, Zeitpunkt, betroffene Kennzahl/Quelle,
AC10) auf — sowohl die S-012-Ablehnungspfade des Grounding-Gates
(Schema-Verletzung, input-fremde Zahl) als auch die S-013-Ablehnungsgründe
des deterministischen Cross-Checks (AC4).

Schreibt strukturiertes Zeilen-JSON über das Standard-`logging`-Modul
(`fastapi`-Pack Coder-Guidance: "Für dateibasiertes Logging ... empfiehlt
sich das Standard-`logging`-Modul mit einem Zeilen-JSON-Formatter") — kein
DB-Schema wird hier erfunden (`docs/data-model.md` §3 kennt mit
`hallucination_log` bereits eine mögliche spätere Persistenzform; ihre
Anbindung ist keine Coder-Aufgabe dieser Story). Zusätzlich in-memory
gepuffert, damit Tests/Aufrufer einen geschriebenen Eintrag ohne
Log-Capture inspizieren können.

NFR: Protokolleinträge enthalten nie Secrets/API-Keys im Klartext — sie
tragen ausschließlich die Felder aus `ProtokollEintrag` (Kennzahl-Typ,
Quellen-ID, Grund, Zeitpunkt, Detailtext).
"""

from __future__ import annotations

import json
import logging
import threading

from app.contracts.llm_grounding import ProtokollEintrag

_logger = logging.getLogger("audit.grounding")

_lock = threading.Lock()
_eintraege: list[ProtokollEintrag] = []


def protokolliere(eintrag: ProtokollEintrag) -> None:
    """Nimmt einen Protokolleintrag auf (AC10): eine Zeile strukturiertes
    JSON über `logging` PLUS in-memory Historie (`alle_eintraege`)."""
    payload = eintrag.model_dump(mode="json")
    _logger.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    with _lock:
        _eintraege.append(eintrag)


def alle_eintraege() -> tuple[ProtokollEintrag, ...]:
    """Liefert eine unveränderliche Kopie aller bisher protokollierten
    Einträge (Inspektion, z.B. in Tests)."""
    with _lock:
        return tuple(_eintraege)


def reset_fuer_tests() -> None:
    """Nur für Tests: leert die in-memory Historie zwischen Testfällen,
    damit Assertions nicht von zuvor gelaufenen Tests beeinflusst werden."""
    with _lock:
        _eintraege.clear()
