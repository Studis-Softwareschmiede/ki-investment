"""System-Status-Voll-View-Kontext (Story S-075, `docs/specs/frontend-
cockpit.md` AC17/AC19; `design.md` §7.2-§7.5/§7.10).

Baut aus dem geteilten `SystemStatusResponse` (S-068, `app.api.queries
.system_status.system_status_uebersicht`, dieselbe Query-Funktion wie
`GET /api/system/status`, AC1/AC10) den zusätzlichen Jinja-Kontext, den
`views/system-status.html` (Erstladung) UND `partials/
system_status_daten.html` (AC19-Live-Polling-Partial, `GET /ui/system-
status/partial`) TEILEN (kein zweiter Datenzusammenbau je Aufruf).

**Wiederverwendung statt Doppelspur (P4/DRY):** die kompakten
Icon/Label-Werte (Ampel/Kill-Switch/Modus/Heartbeat/Drawdown/Halluzination)
holt sich dieses Modul unverändert von `app.web.status_partial
.status_partial_kontext` (S-074-Fundament, HIER NUR gelesen/wiederverwendet
— keine Änderung an jener Datei, Hot-Spot-Konvention S-075: der von
`app.api.control` mitgenutzte Statusleisten-Kontextbau bleibt für parallele
Stories unangetastet). Die Voll-View braucht zusätzlich Detailwerte, die
die kompakte Statusleiste aus Platzgründen nicht zeigt: Kill-Switch-
Auslöser/-Grund/-Zeitpunkt, Gate-Ampel-Zeitstempel, Drawdown-/Halluzinations-
KPI-Rohwerte sowie **Heartbeat je Modul** (die kompakte Statusleiste
aggregiert alle Module zu einem einzigen ok/ausgefallen-Indikator).

**Reine Anzeige-Formatierung** — kein `app.domain.**`-Import (AC2-Boundary-
Geist, analog `app.web.status_partial`), keine eigene Zustandslogik: die
Heartbeat-Ausfall-Berechnung (`jetzt − letzter_ping > intervall_soll`)
spiegelt exakt den bereits in `app.core.heartbeat.pruefe_ausfaelle`
definierten Vergleich (STRIKT `>`), hier nur für die Anzeige je Modul
wiederholt statt aggregiert."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from app.contracts.system_status import SystemStatusResponse
from app.web.status_partial import status_partial_kontext


class _HeartbeatZeile(TypedDict):
    modul_id: str
    state: str
    alter_sekunden: int


def _heartbeat_zeilen(
    status: SystemStatusResponse, *, jetzt: datetime
) -> tuple[_HeartbeatZeile, ...]:
    """AC17 "Heartbeat je Modul": pro registriertem Modul einzeln, anders
    als der aggregierte Statusleisten-Indikator (`status_partial_kontext`)."""
    zeilen: list[_HeartbeatZeile] = []
    for eintrag in status.heartbeats:
        alter = jetzt - eintrag.letzter_ping_zeitstempel
        ausgefallen = alter > eintrag.intervall_soll
        zeilen.append(
            _HeartbeatZeile(
                modul_id=eintrag.modul_id,
                state="ausgefallen" if ausgefallen else "ok",
                alter_sekunden=max(int(alter.total_seconds()), 0),
            )
        )
    return tuple(zeilen)


def system_status_view_kontext(status: SystemStatusResponse) -> dict[str, object]:
    """AC17/AC19: gemeinsamer Kontextaufbau für die Voll-View UND ihr
    Live-Polling-Partial (dasselbe Markup wird neu gerendert, kein
    Layout-Sprung, `design.md` §8.3)."""
    jetzt = datetime.now(UTC)
    return {
        "status": status,
        "status_context": status_partial_kontext(status),
        "heartbeat_zeilen": _heartbeat_zeilen(status, jetzt=jetzt),
        "live_kritisch": status.kill_switch.zustand == "angehalten",
    }


__all__ = ["system_status_view_kontext"]
