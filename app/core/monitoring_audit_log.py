"""Audit-Protokoll für übersprungene Titel eines Depot-Überwachung-
Monitoring-Zyklus (AC1 "unvollständig" / AC9 "nicht bewertbar", Spec
`docs/specs/depot-ueberwachung.md`).

Cross-Cutting-Helfer in `app/core/` (architecture.md §4: "core/ ...
logging"), analog zu `app.core.depot_audit_log` (dortiger Sink ist an die
`depot`-Verträge gebunden — Depot-Überwachung bekommt einen eigenen Sink
statt diese fremde Kopplung wiederzuverwenden).

Schreibt strukturiertes Zeilen-JSON über das Standard-`logging`-Modul,
zusätzlich in-memory gepuffert, damit Tests/Aufrufer einen geschriebenen
Eintrag ohne Log-Capture inspizieren können (identisches Muster zu
`app.core.audit_log`/`app.core.depot_audit_log`).

NFR: Protokolleinträge enthalten nie Secrets/Rohdaten im Klartext — nur die
Felder aus `MonitoringProtokollEintrag` (Zeitpunkt, Titel-ID, Grund,
Detailtext).
"""

from __future__ import annotations

import json
import logging
import threading

from app.contracts.depot_ueberwachung import MonitoringProtokollEintrag

_logger = logging.getLogger("audit.depot_ueberwachung")

_lock = threading.Lock()
_eintraege: list[MonitoringProtokollEintrag] = []


def protokolliere(eintrag: MonitoringProtokollEintrag) -> None:
    """Nimmt einen Protokolleintrag auf (AC1/AC9): eine Zeile
    strukturiertes JSON über `logging` PLUS in-memory Historie
    (`alle_eintraege`)."""
    payload = eintrag.model_dump(mode="json")
    _logger.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    with _lock:
        _eintraege.append(eintrag)


def alle_eintraege() -> tuple[MonitoringProtokollEintrag, ...]:
    """Liefert eine unveränderliche Kopie aller bisher protokollierten
    Einträge (Inspektion, z.B. in Tests)."""
    with _lock:
        return tuple(_eintraege)


def reset_fuer_tests() -> None:
    """Nur für Tests: leert die in-memory Historie zwischen Testfällen,
    damit Assertions nicht von zuvor gelaufenen Tests beeinflusst werden."""
    with _lock:
        _eintraege.clear()
