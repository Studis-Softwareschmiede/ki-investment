"""Quellenausfall-Konsum: Fallback/Alerting + No-Evidence-No-Trade-Gate
(Story S-026, AC9, Spec `docs/specs/betriebssicherung.md`).

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4 „core/
QUERSCHNITT: kill_switch, heartbeat, drawdown_monitor, secrets, logging,
errors"), analog zu `app.core.heartbeat`/`app.core.drawdown_monitor` — kein
I/O, kein DB-Zugriff in dieser Story.

**Rollenteilung (Abhängigkeiten der Spec: „Socket / Datenquellen
([[dateneingang]]) — Quellenausfall-Signale (No-Evidence-No-Trade, AC9)"):**
Die Erkennung SELBST, ob eine Datenquelle ausgefallen oder veraltet ist
(Retry/Backoff, Recalculation-Window, Staleness-Schwellen — dateneingang
AC10/AC12), ist NICHT Teil dieser Story (Nicht-Ziel der Spec: „Kein
Datenqualitäts-Layer im Detail ... sind eigene Bausteine des
Dateneingangs"). Dieses Modul ist die betriebssicherungsseitige
Konsumstelle (analog zu `app.core.hallucination_kpi`s Rolle für AC8): ein
(künftiger) Dateneingang-/Socket-Aufrufer MELDET einen erkannten
Ausfall/eine Veraltung über `melde_ausfall()`, dieses Modul (a) meldet
dafür einen `Alert(typ="quellenausfall")` über den Benachrichtigungskanal
(AC7) und (b) hält einen abfragbaren No-Evidence-No-Trade-Gate-Zustand
(`ist_evidenz_verfuegbar()`), den ein künftiges Order-Pfad-Modul vor jeder
Order-Erzeugung für Titel dieser Quelle abfragen wird — analog zu
`app.core.kill_switch.ist_order_erzeugung_erlaubt()` und
`app.core.hallucination_kpi.ist_llm_aktiv()`.

**Kein Kill-Switch-Trigger:** anders als Heartbeat-Ausfall (AC4) und
Drawdown (AC2) löst ein Quellenausfall laut Spec KEINEN automatischen
Kill-Switch aus — Verträge/Abhängigkeiten nennen für `quellenausfall` nur
„Fallback/Alerting", keinen Kill-Switch-Bezug (der eigene Alert-Typ `kill`
bleibt dem Kill-Switch selbst vorbehalten).

**Wiederherstellung:** `melde_wiederhergestellt()` hebt die Gate-Sperre für
eine Quelle wieder auf (event-getrieben durch denselben künftigen
Aufrufer, der auch `melde_ausfall()` ruft) — ohne diese Symmetrie bliebe
das No-Evidence-No-Trade-Gate nach einem einmal gemeldeten Ausfall
dauerhaft gesperrt, was die Spec nicht fordert (kein Kill-Switch-artiger
Latch mit Pflicht zur manuellen Freigabe — AC3 nennt diese Pflicht explizit
nur für den Kill-Switch). Die Wiederherstellung selbst erzeugt bewusst
KEINEN Alert (AC9 fordert nur, dass „der Ausfall gemeldet wird").

Cold-Start-Hinweis: kein existierender Produktionscode ruft dieses Modul
bislang auf (der Socket-/Dateneingang-Ausfallmelder ist noch nicht gebaut,
`app.adapters.sockets.base.SocketAdapter` kennt heute nur AC2/AC3-Verwerfen
einzelner Datenpunkte, keine quellenweite Ausfall-Erkennung) — ein
künftiger Aufrufer registriert Ausfälle/Wiederherstellungen hierüber.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from app.contracts.betriebssicherung import Alert
from app.core.alerts import melde


@dataclass(frozen=True)
class QuellenausfallEintrag:
    """Interner Zustand EINER als ausgefallen/veraltet gemeldeten Quelle
    (Inspektion, z. B. in Tests) — kein eigener Spec-Vertrag, da die Spec
    für den Austausch selbst nur `Alert` benennt."""

    quelle_id: str
    grund: str
    gemeldet_am: datetime


_lock = threading.Lock()
_ausgefallene_quellen: dict[str, QuellenausfallEintrag] = {}


def melde_ausfall(quelle_id: str, grund: str, *, zeitstempel: datetime | None = None) -> Alert:
    """Meldet, dass eine benötigte Datenquelle ausgefallen ist oder
    veraltete Daten liefert (AC9, deckt A3): meldet einen
    `Alert(typ="quellenausfall")` über den Benachrichtigungskanal (AC7,
    „der Ausfall wird gemeldet") UND setzt das No-Evidence-No-Trade-Gate
    (`ist_evidenz_verfuegbar(quelle_id)` liefert danach `False`) — kein
    Trade wird auf dieser fehlenden Datengrundlage erzeugt.

    Wird `quelle_id` erneut gemeldet, während sie bereits als ausgefallen
    gilt, wird der Zustand (Grund/Zeitpunkt) aktualisiert und trotzdem ein
    weiterer Alert gemeldet — jede Meldung ist ein eigenes, meldenswertes
    Ereignis (analog zur Kill-Switch-Idempotenz in
    `app.core.kill_switch.ausloesen()`, die ebenfalls jede Auslösung
    protokolliert/meldet)."""
    ts = zeitstempel or datetime.now(UTC)
    eintrag = QuellenausfallEintrag(quelle_id=quelle_id, grund=grund, gemeldet_am=ts)
    with _lock:
        _ausgefallene_quellen[quelle_id] = eintrag

    alert = Alert(
        typ="quellenausfall",
        schwere="warn",
        nachricht=f"Quelle {quelle_id!r} ausgefallen/veraltet: {grund}",
        zeitstempel=ts,
    )
    melde(alert)
    return alert


def melde_wiederhergestellt(quelle_id: str) -> None:
    """Hebt eine zuvor per `melde_ausfall()` gesetzte Gate-Sperre für
    `quelle_id` wieder auf (No-Op, falls die Quelle nicht als ausgefallen
    geführt wird). Erzeugt bewusst KEINEN Alert (AC9 fordert nur, dass der
    Ausfall selbst gemeldet wird, keine Wiederherstellungs-Benachrichtigung)."""
    with _lock:
        _ausgefallene_quellen.pop(quelle_id, None)


def ist_evidenz_verfuegbar(quelle_id: str) -> bool:
    """No-Evidence-No-Trade-Gate (AC9): `False`, solange für `quelle_id`
    ein Ausfall gemeldet ist und keine Wiederherstellung folgte — der
    (künftige) Order-Pfad fragt dies vor jeder Order-Erzeugung für Titel
    dieser Quelle ab."""
    with _lock:
        return quelle_id not in _ausgefallene_quellen


def alle_ausfaelle() -> tuple[QuellenausfallEintrag, ...]:
    """Liefert eine unveränderliche Kopie aller aktuell als ausgefallen
    geführten Quellen (Inspektion, z. B. in Tests)."""
    with _lock:
        return tuple(_ausgefallene_quellen.values())


def reset_fuer_tests() -> None:
    """Nur für Tests: leert den Ausfall-Zustand vollständig, damit
    Assertions nicht von zuvor gelaufenen Tests beeinflusst werden."""
    with _lock:
        _ausgefallene_quellen.clear()
