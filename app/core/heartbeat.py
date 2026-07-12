"""Heartbeat-Überwachung je Pipeline-Modul (Story S-025, AC4, Spec
`docs/specs/betriebssicherung.md`).

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4: "core/
QUERSCHNITT: kill_switch, heartbeat, drawdown_monitor, secrets, logging,
errors"), analog zu `app.core.kill_switch`/`app.core.hallucination_kpi` —
kein I/O, kein DB-Zugriff in dieser Story.

**Vertrag (AC4):** `HeartbeatEintrag = {modul_id, letzter_ping_zeitstempel,
intervall_soll}`; Ausfall wenn `now − letzter_ping_zeitstempel >
intervall_soll` (STRIKT `>`). `registriere_modul()` legt einen Heartbeat
mit `letzter_ping_zeitstempel = jetzt` an; jedes überwachte (künftige)
Pipeline-Modul ruft anschließend periodisch `ping()` auf.

**Kritikalität (AC4 "je nach Kritikalität/Konfiguration"):** `kritisch`
ist bewusst KEIN Feld des `HeartbeatEintrag`-Vertrags (der Spec-Vertrag
nennt wörtlich nur die drei Austausch-Felder) — es ist reiner interner
Registrierungs-Zustand dieses Moduls, der bei `registriere_modul()`
gesetzt wird. Default `kritisch=True` (Fail-Safe: ein Modul ohne
explizite Konfiguration gilt als kill-relevant, statt einen Ausfall
stillschweigend nur zu vermelden) — ein registrierendes Modul kann sich
explizit als `kritisch=False` einstufen, wenn sein Ausfall nur einen Alert
(keinen Kill-Switch-Trigger) rechtfertigt.

**Auto-Trigger (AC4, docks an S-007 an):** `pruefe_ausfaelle()` ruft bei
jedem erkannten Ausfall eines `kritisch=True`-Moduls das BESTEHENDE
`app.core.kill_switch.ausloesen()` mit Quelle `"heartbeat"` auf — keine
neue Zustandsmaschine, keine Änderung der Kill-Switch-Semantik (dessen
Idempotenz bei Mehrfach-Auslösung im `angehalten`-Zustand deckt
wiederholte Ausfall-Checks bereits ab, ohne dass dieses Modul selbst
dedupen muss). Jeder erkannte Ausfall erzeugt zusätzlich IMMER einen
`Alert` über `app.core.alerts.melde()` — unabhängig von `kritisch`.

Cold-Start-Hinweis: kein existierender Produktionscode registriert
bislang ein Modul (die eigentlichen Pipeline-Module — Ingest-Scheduler,
Analyse-Orchestrator etc. — existieren noch nicht); ein künftiger
Scheduler ruft `pruefe_ausfaelle()` periodisch auf. Dieses Modul ist
eigenständig, deterministisch und vollständig getestet, wird aber (noch)
von keinem Scheduler aufgerufen (Nicht-Ziel dieser Story: kein
Scheduler/Cron-Loop wird hier gebaut).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.contracts.betriebssicherung import Alert, HeartbeatEintrag, KillSwitchAusloeser
from app.core import kill_switch
from app.core.alerts import melde


class HeartbeatFehler(RuntimeError):
    """Für `modul_id` liegt keine Registrierung vor (AC4) — `ping()`/
    `status()` auf einem unregistrierten Modul ist ein Aufrufer-Fehler
    (Tippfehler im `modul_id`), kein stiller No-Op/Auto-Registrieren."""


@dataclass
class _ModulZustand:
    letzter_ping_zeitstempel: datetime
    intervall_soll: timedelta
    kritisch: bool


_lock = threading.Lock()
_module: dict[str, _ModulZustand] = {}


def registriere_modul(
    modul_id: str,
    intervall_soll: timedelta,
    *,
    kritisch: bool = True,
    jetzt: datetime | None = None,
) -> HeartbeatEintrag:
    """Registriert ein Pipeline-Modul zur Heartbeat-Überwachung (AC4) mit
    initialem `letzter_ping_zeitstempel = jetzt` (Default: aktueller
    UTC-Zeitpunkt). Eine erneute Registrierung derselben `modul_id`
    überschreibt die vorherige Konfiguration (kein Fehler — z. B. bei
    App-Neustart eines Moduls)."""
    ts = jetzt or datetime.now(UTC)
    with _lock:
        _module[modul_id] = _ModulZustand(
            letzter_ping_zeitstempel=ts, intervall_soll=intervall_soll, kritisch=kritisch
        )
        return _als_eintrag(modul_id, _module[modul_id])


def ping(modul_id: str, *, zeitpunkt: datetime | None = None) -> HeartbeatEintrag:
    """Aktualisiert `letzter_ping_zeitstempel` eines registrierten Moduls
    (AC4). Wirft `HeartbeatFehler`, wenn `modul_id` nicht registriert ist."""
    ts = zeitpunkt or datetime.now(UTC)
    with _lock:
        zustand = _module.get(modul_id)
        if zustand is None:
            raise HeartbeatFehler(
                f"Kein registriertes Modul mit modul_id={modul_id!r} — "
                "registriere_modul() muss vor dem ersten ping() aufgerufen werden."
            )
        zustand.letzter_ping_zeitstempel = ts
        return _als_eintrag(modul_id, zustand)


def status(modul_id: str) -> HeartbeatEintrag:
    """Reine Zustandsabfrage EINES registrierten Moduls. Wirft
    `HeartbeatFehler`, wenn `modul_id` nicht registriert ist."""
    with _lock:
        zustand = _module.get(modul_id)
        if zustand is None:
            raise HeartbeatFehler(f"Kein registriertes Modul mit modul_id={modul_id!r}.")
        return _als_eintrag(modul_id, zustand)


def alle_heartbeats() -> tuple[HeartbeatEintrag, ...]:
    """Liefert den aktuellen Heartbeat-Zustand aller registrierten Module."""
    with _lock:
        return tuple(_als_eintrag(mid, z) for mid, z in _module.items())


def pruefe_ausfaelle(*, jetzt: datetime | None = None) -> tuple[Alert, ...]:
    """Prüft ALLE registrierten Module auf Ausfall (AC4): `now −
    letzter_ping_zeitstempel > intervall_soll` (STRIKT `>`). Für jeden
    erkannten Ausfall wird IMMER ein `Alert` gemeldet
    (`app.core.alerts.melde`); ist das Modul `kritisch`, wird zusätzlich
    der bestehende `app.core.kill_switch.ausloesen()` mit Quelle
    `"heartbeat"` aufgerufen (dessen Idempotenz deckt wiederholte Checks
    im bereits `angehalten`-Zustand ab). Liefert alle bei DIESEM Aufruf
    erzeugten Alerts (nicht die Gesamt-Historie)."""
    ts = jetzt or datetime.now(UTC)
    with _lock:
        ausgefallene = [
            (modul_id, zustand)
            for modul_id, zustand in _module.items()
            if ts - zustand.letzter_ping_zeitstempel > zustand.intervall_soll
        ]

    erzeugte_alerts: list[Alert] = []
    for modul_id, zustand in ausgefallene:
        alert = Alert(
            typ="heartbeat",
            schwere="critical" if zustand.kritisch else "warn",
            nachricht=(
                f"Heartbeat-Ausfall: Modul {modul_id!r} — letzter Ping "
                f"{zustand.letzter_ping_zeitstempel.isoformat()}, Soll-Intervall "
                f"{zustand.intervall_soll}."
            ),
            zeitstempel=ts,
        )
        melde(alert)
        erzeugte_alerts.append(alert)

        if zustand.kritisch:
            kill_switch.ausloesen(
                KillSwitchAusloeser(
                    quelle="heartbeat",
                    zeitstempel=ts,
                    grund=f"Heartbeat-Ausfall kritisches Modul {modul_id!r}",
                )
            )

    return tuple(erzeugte_alerts)


def reset_fuer_tests() -> None:
    """Nur für Tests: entfernt alle Registrierungen, damit Assertions
    nicht von zuvor gelaufenen Tests beeinflusst werden."""
    with _lock:
        _module.clear()


def _als_eintrag(modul_id: str, zustand: _ModulZustand) -> HeartbeatEintrag:
    return HeartbeatEintrag(
        modul_id=modul_id,
        letzter_ping_zeitstempel=zustand.letzter_ping_zeitstempel,
        intervall_soll=zustand.intervall_soll,
    )
