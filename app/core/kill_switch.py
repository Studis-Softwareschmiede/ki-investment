"""Kill-Switch «flatten & halt» — manuell, Zustandsmaschine, unveränderliches
Protokoll (Story S-007, Spec `docs/specs/betriebssicherung.md` AC1/AC3/AC11).

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4: "core/
QUERSCHNITT: kill_switch, heartbeat, drawdown_monitor, secrets, logging,
errors"), analog zu `app.core.hallucination_kpi` (S-027) — dieselbe
Kategorie deterministischer Betriebszustand, kein I/O, kein DB-Zugriff in
dieser Story.

**Zustandsmaschine (AC1, AC3, architecture.md §6 "Betriebszustand
(Kill-Switch, BR-021)"):** architecture.md beschreibt den vollen Übergang
als `NORMAL → HALT_ANGEFORDERT → FLATTEN → HALTED`. Im Paper-Modus (diese
Story: keine echten Broker-/Positions-Aufrufe, Kauf-/Verkaufsmodul +
Depotmodul existieren laut Spec-Abhängigkeiten noch nicht — Cold-Start,
analog `tests/architecture/test_order_pfad_invariante.py` und
`app.core.hallucination_kpi`) läuft dieser Übergang synchron in einem
einzigen `ausloesen()`-Aufruf durch, ohne auf eine echte Order-Stornierung
zu warten. Extern sichtbar/getestet bleiben genau die zwei von der Spec
benannten Zustände (`Betriebszustand`): `normal` / `angehalten` (= `HALTED`).

**Halt (AC1):** `ist_order_erzeugung_erlaubt()` ist der Kontrollpunkt, den
ein künftiges Order-Pfad-Modul (`domain/sizing`, `orchestration/
execution_service`, noch nicht gebaut) vor jeder Order-Erzeugung abfragen
wird — `False`, solange der Betriebszustand `angehalten` ist. Analog zu
`app.core.hallucination_kpi.ist_llm_aktiv()`.

**Flatten (AC1, Paper simuliert):** Es existiert in dieser Codebasis noch
keine Positions-/Order-Domäne. Das „Einleiten" des Flatten ist daher in
dieser Story auf die Zustandsübergabe + Protokollierung reduziert (kein
echter Broker-Call, keine Positions-Zeilen zum Schliessen vorhanden) —
sobald die Positions-Domäne existiert, konsumiert sie denselben
Kill-Switch-Zustand (`status()`/`ist_order_erzeugung_erlaubt()`), um
tatsächliche Exit-Orders auszulösen (Anschluss-Pflicht der künftigen
Orchestrierung, analog zur bereits dokumentierten Bronze→Silver-Verdrahtung
in `app/db/validation.py`).

**Idempotenz (Edge-Case der Spec):** Eine erneute Auslösung, während der
Zustand bereits `angehalten` ist, verändert den Zustand NICHT (kein
Zustandssprung) und löst KEIN zweites Flatten aus — sie wird trotzdem
protokolliert (`wirkung="idempotent_bereits_angehalten"`), weil AC11 „JEDE
Auslösung" fordert, nicht nur die erste.

**Unveränderliches Protokoll (AC11):** Jeder `ausloesen()`-Aufruf hängt
einen `KillSwitchEreignis`-Eintrag an eine in-memory Historie an (analog
`app.core.audit_log`, hier als eigenes, betriebssicherung-spezifisches
Modul statt Wiederverwendung des llm-grounding-Audit-Moduls: dessen
`ProtokollEintrag`/`ProtokollGrund`-Vertrag ist an die llm-grounding-Spec
gebunden — ein fachfremdes Wiederverwenden würde beide Domänen unsauber
vermischen) UND schreibt eine strukturierte JSON-Log-Zeile über das
Standard-`logging`-Modul (fastapi-Pack-Konvention: "dabei nie den
kompletten Request-Body ... ungefiltert loggen" — hier trägt der Eintrag
ohnehin nur die Vertragsfelder, keine Secrets).

**Freigabe (AC3) bewusst NICHT Teil des AC11-Protokolls:** AC11 nennt
wörtlich "jede Auslösung und jeder Alert"; die Spec definiert keinen
eigenen Alert-`typ` für eine Freigabe (Verträge: `typ (kill|heartbeat|
drawdown|quellenausfall|halluzination)`). `freigeben()` ändert daher nur
den Zustand, ohne einen `KillSwitchEreignis`-Eintrag zu erzeugen (kein
Gold-Plating über die zugewiesenen ACs hinaus).

Nicht Teil dieser Story (Board-Item-Scope): automatische Trigger (AC2
Drawdown, AC4 Heartbeat) — nur der manuelle Pfad wird hier ausgelöst;
Benachrichtigungskanal (AC7); Heartbeat-Überwachung selbst (AC4).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime

from app.contracts.betriebssicherung import (
    Betriebszustand,
    KillSwitchAusloeser,
    KillSwitchEreignis,
    KillSwitchQuelle,
    KillSwitchStatus,
)

_logger = logging.getLogger("audit.kill_switch")

_lock = threading.Lock()
_zustand: Betriebszustand = "normal"
_grund: str | None = None
_quelle: KillSwitchQuelle | None = None
_ausgeloest_am: datetime | None = None
_ereignisse: list[KillSwitchEreignis] = []


def ausloesen(ausloeser: KillSwitchAusloeser) -> KillSwitchStatus:
    """Löst den Kill-Switch aus (AC1): stoppt sofort jede Erzeugung neuer
    Orders (halt, s. `ist_order_erzeugung_erlaubt()`) und leitet das
    Schliessen offener Positionen ein (flatten, Paper-simuliert, s.
    Modul-Docstring) — der Betriebszustand wechselt auf `angehalten` (AC3).

    Idempotent (Edge-Case): ist der Zustand bereits `angehalten`, bleibt er
    unverändert (kein doppeltes Flatten, kein Zustandssprung) — die
    Auslösung wird trotzdem protokolliert (AC11, `wirkung=
    "idempotent_bereits_angehalten"`)."""
    global _zustand, _grund, _quelle, _ausgeloest_am
    with _lock:
        bereits_angehalten = _zustand == "angehalten"
        if not bereits_angehalten:
            _zustand = "angehalten"
            _grund = ausloeser.grund
            _quelle = ausloeser.quelle
            _ausgeloest_am = ausloeser.zeitstempel
        wirkung = "idempotent_bereits_angehalten" if bereits_angehalten else "ausgeloest"
        eintrag = KillSwitchEreignis(
            quelle=ausloeser.quelle,
            zeitstempel=ausloeser.zeitstempel,
            grund=ausloeser.grund,
            kennwert=ausloeser.kennwert,
            wirkung=wirkung,
        )
        _ereignisse.append(eintrag)
        aktueller_status = _status_unlocked()

    _logger.warning(json.dumps(eintrag.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    return aktueller_status


def freigeben() -> KillSwitchStatus:
    """Explizite manuelle Wieder-Freigabe (AC3): einziger Weg zurück in den
    Normalbetrieb — nie automatisch. Idempotent (kein Fehler/keine
    Nebenwirkung, wenn der Zustand bereits `normal` ist)."""
    global _zustand, _grund, _quelle, _ausgeloest_am
    with _lock:
        _zustand = "normal"
        _grund = None
        _quelle = None
        _ausgeloest_am = None
        return _status_unlocked()


def status() -> KillSwitchStatus:
    """Reine Zustandsabfrage — verändert nichts."""
    with _lock:
        return _status_unlocked()


def ist_order_erzeugung_erlaubt() -> bool:
    """AC1-Kontrollpunkt für den (künftigen) Order-Pfad: `False`, solange
    der Betriebszustand `angehalten` ist."""
    with _lock:
        return _zustand == "normal"


def alle_ereignisse() -> tuple[KillSwitchEreignis, ...]:
    """Liefert eine unveränderliche Kopie aller bisher protokollierten
    Auslösungen (AC11, Inspektion z.B. in Tests)."""
    with _lock:
        return tuple(_ereignisse)


def reset_fuer_tests() -> None:
    """Nur für Tests: setzt Zustand UND Ereignis-Historie vollständig
    zurück, damit Assertions nicht von zuvor gelaufenen Tests beeinflusst
    werden."""
    global _zustand, _grund, _quelle, _ausgeloest_am
    with _lock:
        _zustand = "normal"
        _grund = None
        _quelle = None
        _ausgeloest_am = None
        _ereignisse.clear()


def _status_unlocked() -> KillSwitchStatus:
    return KillSwitchStatus(
        zustand=_zustand,
        quelle=_quelle,
        grund=_grund,
        ausgeloest_am=_ausgeloest_am,
    )
