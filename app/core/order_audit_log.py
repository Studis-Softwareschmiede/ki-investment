"""Audit-Protokoll für Teilfills/Rejects/Timeouts der Order-Ausführung (AC8,
Spec `docs/specs/ausfuehrung-paper.md`, Story S-048).

Cross-Cutting-Helfer in `app/core/` (architecture.md §4: "core/ ...
logging"), analog zu `app.core.depot_audit_log` (dortiger Sink ist an die
`depot`-Verträge gebunden — Order-Ausführung bekommt einen eigenen Sink
statt diese fremde Kopplung wiederzuverwenden). Nimmt für jedes
Fill-Handling-Ergebnis mit `status ∈ {"partial", "rejected", "timeout"}`
entlang von `app.domain.execution.order_ausfuehrung.verarbeite_fill` ein
`Ausfuehrungsergebnis` auf (Spec-Wortlaut AC8: "Teilfills, abgelehnte Orders
(Rejects) und Timeouts werden definiert behandelt und protokolliert" —
`"filled"` ist bewusst NICHT Teil dieses Protokolls, kein Fehlerfall).

Schreibt strukturiertes Zeilen-JSON über das Standard-`logging`-Modul,
zusätzlich in-memory gepuffert, damit Tests/Aufrufer einen geschriebenen
Eintrag ohne Log-Capture inspizieren können (identisches Muster zu
`app.core.depot_audit_log`/`app.core.audit_log`).

NFR: Protokolleinträge enthalten nie Secrets/Rohdaten im Klartext — nur die
Felder aus `Ausfuehrungsergebnis` (kein Broker-Credential-Bezug)."""

from __future__ import annotations

import json
import logging
import threading

from app.contracts.ausfuehrung_paper import Ausfuehrungsergebnis

_logger = logging.getLogger("audit.ausfuehrung")

_lock = threading.Lock()
_eintraege: list[Ausfuehrungsergebnis] = []

#: AC8: nur diese drei Stati werden protokolliert (Spec-Wortlaut "Teilfills,
#: abgelehnte Orders (Rejects) und Timeouts") — `"filled"` ist kein
#: Fehlerfall und daher nicht Teil dieses Audit-Protokolls.
_PROTOKOLLIERTE_STATI: tuple[str, ...] = ("partial", "rejected", "timeout")


def protokolliere(ergebnis: Ausfuehrungsergebnis) -> None:
    """Nimmt ein Fill-Handling-Ergebnis auf (AC8), sofern
    `ergebnis.status ∈ {"partial", "rejected", "timeout"}` — eine Zeile
    strukturiertes JSON über `logging` PLUS in-memory Historie
    (`alle_eintraege`). Ein `"filled"`-Ergebnis wird NICHT protokolliert
    (kein Aufruf nötig, aber auch harmlos, falls ein Aufrufer es dennoch
    übergibt — dann ein reines No-Op)."""
    if ergebnis.status not in _PROTOKOLLIERTE_STATI:
        return
    payload = ergebnis.model_dump(mode="json")
    _logger.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    with _lock:
        _eintraege.append(ergebnis)


def alle_eintraege() -> tuple[Ausfuehrungsergebnis, ...]:
    """Liefert eine unveränderliche Kopie aller bisher protokollierten
    Einträge (Inspektion, z.B. in Tests)."""
    with _lock:
        return tuple(_eintraege)


def reset_fuer_tests() -> None:
    """Nur für Tests: leert die in-memory Historie zwischen Testfällen,
    damit Assertions nicht von zuvor gelaufenen Tests beeinflusst werden."""
    with _lock:
        _eintraege.clear()
