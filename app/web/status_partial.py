"""HTMX-Status-Partial-Kontext (Story S-074, Review-Fix Iteration 2 — AC20
"HTMX rendert nach dem POST das aktualisierte Status-Partial zurück
(§13.7-5)", `docs/specs/frontend-cockpit.md`).

Baut aus dem geteilten View-DTO (`app.contracts.system_status
.SystemStatusResponse`, gespeist von `app.api.queries.system_status
.system_status_uebersicht`, S-068) genau den Jinja-Kontext, den
`app/web/templates/partials/statusleiste.html` für die sechs Indikatoren
(design.md §7.2-§7.5) braucht.

**Wiederverwendung statt Doppelspur:** `app/api/control.py` nutzt dieses
Modul, um nach jedem Control-POST (Toggle/Modus/Kill-Switch) bei einem
HTMX-Aufruf (`HX-Request: true`) dieselbe Statusleiste mit frischen Daten
zurückzurendern (AC20); Story S-075 (AC19 Live-Polling der Statusleiste)
kann dieselbe Funktion für ihre Polling-Partial-Endpunkte weiterverwenden,
statt den Kontextaufbau ein zweites Mal zu bauen.

**Reine Anzeige-Formatierung** (Text/Icon/`data-*`-Werte gemäss
design.md §7.2-§7.5) — keine eigene Zustandslogik/Domain-Berechnung,
importiert nichts aus `app.domain.**` (AC2-Boundary-Geist, auch wenn
dieses Modul unter `app/web/**` nicht vom `test_ui_boundary.py`-Scan
erfasst ist, siehe dortiger `_boundary_dateien()`-Scope).

**Leer-/Platzhalterzustand (E2-Muster):** fehlt für einen Indikator noch
jede Datengrundlage (Cold-Start — kein Gate-Ergebnis, keine registrierten
Heartbeat-Module, `ueberwachungsluecke`, keine geprüften Analysen), bleibt
der jeweilige Schlüssel im zurückgegebenen Kontext-Dict UNBESETZT — das
Template zeigt dafür weiterhin seinen bestehenden statischen „—"/
„unbekannt"-Platzhalter (kein vorgetäuschter Nullwert)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from app.contracts.system_status import SystemStatusResponse


class _StatusItemKontext(TypedDict):
    icon: str
    state: str
    label: str


#: Ampel-Icon + Text je Zustand (design.md §7.2, D3: Farbe + Form + Text).
_AMPEL_TEXT: dict[str, tuple[str, str]] = {
    "gruen": ("●", "GRÜN – Regel aktiv"),
    "gelb": ("◐", "GELB – nur Paper"),
    "rot": ("▲", "ROT – archiviert"),
}

#: Kill-Switch-Icon + Text je Betriebszustand — deckt genau die zwei
#: aktuell im Vertrag (`app.contracts.betriebssicherung.Betriebszustand`)
#: existierenden Werte ab; der vollere Vier-Zustands-Wortschatz aus
#: design.md §7.3 (`HALT_ANGEFORDERT`/`FLATTEN`) ist Zielbild eines
#: künftigen Vertrags-Ausbaus, kein Teil dieses Fixes.
_KILLSWITCH_TEXT: dict[str, tuple[str, str]] = {
    "normal": ("●", "NORMAL"),
    "angehalten": ("▲", "HALTED"),
}


def _item(icon: str, state: str, label: str) -> _StatusItemKontext:
    return {"icon": icon, "state": state, "label": label}


def status_partial_kontext(status: SystemStatusResponse) -> dict[str, _StatusItemKontext]:
    """Baut den Jinja-Kontext (`status_context`) für
    `partials/statusleiste.html` aus dem konsolidierten System-Status-DTO
    (AC8, S-068) — je Indikator `{icon, state, label}`. Ein Indikator ohne
    Datengrundlage fehlt bewusst im Ergebnis-Dict (siehe Moduldocstring)."""
    kontext: dict[str, _StatusItemKontext] = {}

    if status.gate_ampel is not None:
        icon, label = _AMPEL_TEXT[status.gate_ampel]
        kontext["ampel"] = _item(icon, status.gate_ampel, label)

    ks_icon, ks_label = _KILLSWITCH_TEXT[status.kill_switch.zustand]
    kontext["killswitch"] = _item(ks_icon, status.kill_switch.zustand, ks_label)

    kontext["modus"] = _item("🔒", status.modus_global, status.modus_global.upper())

    if status.heartbeats:
        jetzt = datetime.now(UTC)
        ausgefallen = any(
            jetzt - eintrag.letzter_ping_zeitstempel > eintrag.intervall_soll
            for eintrag in status.heartbeats
        )
        if ausgefallen:
            kontext["heartbeat"] = _item("▲", "ausgefallen", "AUSGEFALLEN")
        else:
            kontext["heartbeat"] = _item("●", "ok", "OK")

    if not status.drawdown.ueberwachungsluecke and status.drawdown.drawdown_pct is not None:
        prozent = status.drawdown.drawdown_pct * 100
        kontext["drawdown"] = _item("●", "ok", f"−{prozent:.1f}%")

    if status.halluzinations_kpi.geprueft > 0:
        alarm = status.halluzinations_kpi.alarm
        kontext["halluzination"] = _item(
            "▲" if alarm else "●",
            "alarm" if alarm else "ok",
            f"{status.halluzinations_kpi.quote:.2%}",
        )

    return kontext


__all__ = ["status_partial_kontext"]
