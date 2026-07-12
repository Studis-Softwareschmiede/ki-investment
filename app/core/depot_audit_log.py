"""Audit-Protokoll für abgelehnte Fill-Buchungen (AC1/AC10, Spec
`docs/specs/depot.md`).

Cross-Cutting-Helfer in `app/core/` (architecture.md §4: "core/ ...
logging"), analog zu `app.core.audit_log` (dortiger Sink ist an die
`llm_grounding`-Verträge gebunden — Depot bekommt einen eigenen Sink statt
diese fremde Kopplung wiederzuverwenden). Nimmt für jede abgelehnte
Fill-Buchung entlang von `app.domain.portfolio.fill_booking.pruefe_fill`
einen `FillProtokollEintrag` auf.

Schreibt strukturiertes Zeilen-JSON über das Standard-`logging`-Modul,
zusätzlich in-memory gepuffert, damit Tests/Aufrufer einen geschriebenen
Eintrag ohne Log-Capture inspizieren können (identisches Muster zu
`app.core.audit_log`).

NFR: Protokolleinträge enthalten nie Secrets/Rohdaten im Klartext — nur die
Felder aus `FillProtokollEintrag` (Zeitpunkt, Grund, Titel-ID, Richtung,
Detailtext).
"""

from __future__ import annotations

import json
import logging
import threading

from app.contracts.depot import FillProtokollEintrag

_logger = logging.getLogger("audit.depot")

_lock = threading.Lock()
_eintraege: list[FillProtokollEintrag] = []


def protokolliere(eintrag: FillProtokollEintrag) -> None:
    """Nimmt einen Protokolleintrag auf (AC1/AC10): eine Zeile
    strukturiertes JSON über `logging` PLUS in-memory Historie
    (`alle_eintraege`)."""
    payload = eintrag.model_dump(mode="json")
    _logger.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    with _lock:
        _eintraege.append(eintrag)


def alle_eintraege() -> tuple[FillProtokollEintrag, ...]:
    """Liefert eine unveränderliche Kopie aller bisher protokollierten
    Einträge (Inspektion, z.B. in Tests)."""
    with _lock:
        return tuple(_eintraege)


def reset_fuer_tests() -> None:
    """Nur für Tests: leert die in-memory Historie zwischen Testfällen,
    damit Assertions nicht von zuvor gelaufenen Tests beeinflusst werden."""
    with _lock:
        _eintraege.clear()
