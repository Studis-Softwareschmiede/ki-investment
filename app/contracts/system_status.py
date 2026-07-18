"""Modul-Verträge System-Status (Betriebs-Cockpit, Story S-068, Spec
`docs/specs/frontend-cockpit.md` AC8/AC10).

architecture.md §2 P2 ("Explizite Modul-Verträge"): das View-DTO, das
`GET /api/system/status` liefert und das die (künftige, S-075) HTML-Route
mitnutzt (AC10, P4/DRY). Konsolidiert GENAU die sechs in AC8 benannten
Betriebsindikatoren — Kill-Switch (→ BR-021), aktiver Modus je
Anlageklasse (→ BR-019), Heartbeat je Modul, Drawdown-Überwachung,
Halluzinations-KPI (→ BR-006) und die Gate-Ampel (→ BR-025) — aus
bereits bestehenden Betriebssicherungs-/llm-grounding-/lernschleife-
Verträgen, OHNE sie zu duplizieren.

- `SystemStatusResponse.kill_switch` — direkt `app.contracts
  .betriebssicherung.KillSwitchStatus` (`app.core.kill_switch.status()`).
- `SystemStatusResponse.modus_global`/`modus_je_anlageklasse` — der
  gemäss BR-019 aufgelöste Modus «echt/simuliert»: global + je
  Anlageklasse (1..11). **Cold-Start (Board-Item-Scope):** es existiert
  noch kein persistenter Modus-Override-Store (die Control-Plane, die
  einen solchen Store schreiben würde, ist S-074, Nicht-Ziel dieser
  Story und hängt selbst von S-068 ab) — `app.api.queries.system_status`
  liest deshalb ausschliesslich die (Default-)Werte des bestehenden
  `app.contracts.ausfuehrung_paper.ModusKonfiguration`-Vertrags (global
  `"simuliert"`, keine Overrides), OHNE `app.domain.execution`
  zu importieren (AC2-Boundary verbietet das explizit für die
  UI-/Query-Schicht) — die MVP-Live-Sperre selbst
  (`app.domain.execution.order_ausfuehrung.bestimme_wirksamen_modus`,
  AC3/BR-019) bleibt dadurch unerreicht, ist hier aber auch nicht nötig:
  ohne Override-Store kann sich mangels jeglichen Schreibpfads ohnehin nie
  ein anderer Wert als `"simuliert"` ergeben.
- `SystemStatusResponse.heartbeats` — Tupel aller `app.contracts
  .betriebssicherung.HeartbeatEintrag` (`app.core.heartbeat
  .alle_heartbeats()`).
- `SystemStatusResponse.drawdown` — direkt `app.contracts
  .betriebssicherung.DrawdownStatus` (`app.core.drawdown_monitor.status()`,
  neuer reiner Read-Pfad, S-068 — siehe dortiger Moduldocstring).
- `SystemStatusResponse.halluzinations_kpi` — direkt `app.contracts
  .llm_grounding.HalluzinationsKpiErgebnis` (`app.core.hallucination_kpi
  .aktueller_kpi()`, neuer reiner Read-Pfad, S-068).
- `SystemStatusResponse.gate_ampel`/`gate_ampel_ermittelt_am` — die
  zuletzt persistierte Ampel aus `app.db.models.GateResult`
  (`app.domain.lernschleife.ports.GateErgebnisRepository
  .letztes_ergebnis()`) — `None`, solange noch keine Gate-Auswertung
  vorliegt (Cold-Start, kein Trial ausgewertet; AC4/A3-"kein Urteil"-Fall
  wird laut `app.db.gate_result`-Docstring ohnehin nie persistiert).

Nicht Teil dieser Story (Board-Item-Scope): `mintrl_restlaufzeit` (AC24,
S-078 — eigenes Feld/eigene Story, siehe dortige Spec-Sektion "Betriebs-
Cockpit-Lücken")."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.contracts.betriebssicherung import DrawdownStatus, HeartbeatEintrag, KillSwitchStatus
from app.contracts.depot import Modus
from app.contracts.kandidatensuche import Ampel
from app.contracts.llm_grounding import HalluzinationsKpiErgebnis


class SystemStatusResponse(BaseModel):
    """AC8/AC10 — das konsolidierte System-Status-View-DTO. `response_model`
    von `GET /api/system/status` (`app.api.system_status`); dieselbe Query-
    Funktion (`app.api.queries.system_status.system_status_uebersicht`)
    speist künftig auch die HTML-Statusleiste/-View (S-075, AC10, P4/DRY —
    die HTML-Verdrahtung selbst ist NICHT Teil dieser Story)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kill_switch: KillSwitchStatus
    modus_global: Modus
    modus_je_anlageklasse: dict[int, Modus]
    heartbeats: tuple[HeartbeatEintrag, ...]
    drawdown: DrawdownStatus
    halluzinations_kpi: HalluzinationsKpiErgebnis
    gate_ampel: Ampel | None = None
    gate_ampel_ermittelt_am: datetime | None = None
