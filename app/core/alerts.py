"""Interne Alert-Sammlung (Story S-025, AC4/AC5-Anschlussstelle, Spec
`docs/specs/betriebssicherung.md` — Vertrag `Alert`).

Cross-Cutting-Helfer in `app/core/` (architecture.md §4 `core/`), analog zu
`app.core.audit_log` (schreibt strukturiertes Zeilen-JSON über das
Standard-`logging`-Modul PLUS in-memory Historie, damit Aufrufer/Tests einen
gemeldeten Alert ohne Log-Capture inspizieren können).

AC7 (Benachrichtigungskanal selbst, z. B. Telegram) ist Nicht-Ziel dieser
Story (S-026 baut ihn). Dieses Modul ist die interne, testbare Andockstelle
dafür: `registriere_callback()` nimmt eine beliebige Anzahl Callables
entgegen, die bei jedem `melde()`-Aufruf SYNCHRON mit dem gemeldeten
`Alert` aufgerufen werden — der künftige Benachrichtigungskanal registriert
sich hier, ohne dass `app.core.heartbeat`/`app.core.drawdown_monitor`
geändert werden müssen. Ein fehlschlagender Callback wird geloggt, aber NIE
weitergereicht — ein defekter (künftiger) Benachrichtigungskanal darf den
Kill-Switch/die Überwachung selbst nie blockieren (NFR „Verfügbarkeit" der
Spec: „Der Kill-Switch muss auch bei degradiertem System auslösbar
bleiben").
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable

from app.contracts.betriebssicherung import Alert

_logger = logging.getLogger("audit.alerts")

_lock = threading.Lock()
_alerts: list[Alert] = []
_callbacks: list[Callable[[Alert], None]] = []


def melde(alert: Alert) -> None:
    """Meldet EINEN Alert (AC4/AC5): eine Zeile strukturiertes JSON über
    `logging` PLUS in-memory Historie (`alle_alerts`), anschließend werden
    alle registrierten Callbacks synchron mit `alert` aufgerufen. Ein
    fehlschlagender Callback wird geloggt und NICHT weitergereicht (s.
    Modul-Docstring — Verfügbarkeit der Überwachung geht vor)."""
    payload = alert.model_dump(mode="json")
    _logger.warning(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    with _lock:
        _alerts.append(alert)
        callbacks = tuple(_callbacks)

    for callback in callbacks:
        try:
            callback(alert)
        except Exception:
            _logger.exception("Alert-Callback fehlgeschlagen (Alert bleibt gemeldet).")


def alle_alerts() -> tuple[Alert, ...]:
    """Liefert eine unveränderliche Kopie aller bisher gemeldeten Alerts
    (Inspektion, z. B. in Tests)."""
    with _lock:
        return tuple(_alerts)


def registriere_callback(callback: Callable[[Alert], None]) -> None:
    """Registriert einen Callback, der ab sofort bei jedem `melde()`-Aufruf
    synchron mit dem gemeldeten `Alert` aufgerufen wird — die
    Andockstelle für den künftigen Benachrichtigungskanal (S-026, AC7)."""
    with _lock:
        _callbacks.append(callback)


def entferne_callback(callback: Callable[[Alert], None]) -> None:
    """Entfernt einen zuvor registrierten Callback (No-Op, falls nicht
    registriert)."""
    with _lock:
        if callback in _callbacks:
            _callbacks.remove(callback)


def reset_fuer_tests() -> None:
    """Nur für Tests: leert die in-memory Alert-Historie UND alle
    registrierten Callbacks, damit Assertions nicht von zuvor gelaufenen
    Tests beeinflusst werden."""
    with _lock:
        _alerts.clear()
        _callbacks.clear()
