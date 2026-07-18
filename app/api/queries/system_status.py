"""Query-Funktion System-Status (Story S-068, `docs/specs/frontend-cockpit.md`
AC8/AC10; architecture.md §13.2/§13.7).

`system_status_uebersicht()` konsolidiert GENAU die sechs in AC8 benannten
Betriebsindikatoren zu einem `SystemStatusResponse` (AC1: eine
Query-Funktion je Cockpit-View, geteilt von HTML- und JSON-Route — die
HTML-Verdrahtung selbst folgt in S-075, AC10, NICHT Teil dieser Story).

**Read-only (AC2):** liest AUSSCHLIESSLICH über bereits bestehende,
reine Zustandsabfragen der `app.core.**`-Betriebssicherungs-Module
(Kill-Switch, Heartbeat-Store, KPI — Task-Vorgabe) sowie über den
`GateErgebnisRepository`-Port (S-062-Gate-Ergebnis-Store, injiziert vom
Aufrufer/Router, `app.api.system_status`) — kein `session.add`/`commit`,
kein eigener DB-Zugriff in diesem Modul, kein Import aus
`app.domain.sizing`/`app.domain.risikomanagement`/`app.domain.execution`/
`app.orchestration.*_pipeline`/`app.orchestration.execution_service`
(AC2-Boundary, `tests/architecture/test_ui_boundary.py`).

**Seiteneffektfrei (wichtig für ein GET, das künftig gepollt wird, AC19):**
`app.core.drawdown_monitor.pruefe_drawdown()` und `app.core
.hallucination_kpi.berechne_kpi()` lösen als Nebenwirkung Alerts/den
Kill-Switch bzw. einen Alarm-Übergang aus — für eine reine Status-Anzeige
ungeeignet (ein Seitenaufruf dürfte den Betriebszustand nie verändern).
Diese Query nutzt deshalb die neuen reinen Gegenstücke `app.core
.drawdown_monitor.status()` und `app.core.hallucination_kpi
.aktueller_kpi()` (S-068).

**Modus je Anlageklasse (→ BR-019):** siehe `app.contracts.system_status
.SystemStatusResponse`-Docstring für die Cold-Start-Begründung (kein
persistenter Modus-Override-Store existiert vor S-074) — jede der elf
Anlageklassen (`asset_class.id ∈ 1..11`, `docs/data-model.md` BR-100)
löst sich mangels Override auf den globalen Default `ModusKonfiguration
().global_modus` ("simuliert") auf."""

from __future__ import annotations

from app.contracts.ausfuehrung_paper import ModusKonfiguration
from app.contracts.betriebssicherung import DrawdownStatus, HeartbeatEintrag, KillSwitchStatus
from app.contracts.depot import Modus
from app.contracts.llm_grounding import HalluzinationsKpiErgebnis
from app.contracts.system_status import SystemStatusResponse
from app.core import drawdown_monitor, hallucination_kpi, heartbeat, kill_switch
from app.domain.lernschleife.ports import GateErgebnisRepository

#: BR-100: `asset_class.id` liegt IMMER in 1..11 (DB-CHECK-Constraint,
#: `app.db.models.AssetClass`) — dieselbe Domäne, gegen die z. B.
#: `app.contracts.ausfuehrung_paper.OrderAnfrage.asset_class_id` validiert
#: (`Field(ge=1, le=11)`).
_ANLAGEKLASSEN_IDS: tuple[int, ...] = tuple(range(1, 12))


def system_status_uebersicht(
    *, gate_ergebnis_repository: GateErgebnisRepository
) -> SystemStatusResponse:
    """AC8 — konsolidierter Betriebsstatus: Kill-Switch (→ BR-021), Modus
    global + je Anlageklasse (→ BR-019), Heartbeat je Modul, Drawdown,
    Halluzinations-KPI (→ BR-006) und die zuletzt ermittelte Gate-Ampel
    (→ BR-025)."""
    kill_switch_status: KillSwitchStatus = kill_switch.status()
    heartbeats: tuple[HeartbeatEintrag, ...] = heartbeat.alle_heartbeats()
    drawdown_status: DrawdownStatus = drawdown_monitor.status()
    halluzinations_kpi: HalluzinationsKpiErgebnis = hallucination_kpi.aktueller_kpi()

    modus_konfiguration = ModusKonfiguration()
    modus_je_anlageklasse: dict[int, Modus] = {
        asset_class_id: modus_konfiguration.modus_je_anlageklasse.get(
            asset_class_id, modus_konfiguration.global_modus
        )
        for asset_class_id in _ANLAGEKLASSEN_IDS
    }

    letztes_gate_ergebnis = gate_ergebnis_repository.letztes_ergebnis()

    return SystemStatusResponse(
        kill_switch=kill_switch_status,
        modus_global=modus_konfiguration.global_modus,
        modus_je_anlageklasse=modus_je_anlageklasse,
        heartbeats=heartbeats,
        drawdown=drawdown_status,
        halluzinations_kpi=halluzinations_kpi,
        gate_ampel=letztes_gate_ergebnis.ampel if letztes_gate_ergebnis is not None else None,
        gate_ampel_ermittelt_am=(
            letztes_gate_ergebnis.ermittelt_am if letztes_gate_ergebnis is not None else None
        ),
    )
