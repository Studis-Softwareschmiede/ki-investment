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

**Modus je Anlageklasse (→ BR-019, S-074 schliesst die Cold-Start-Lücke):**
`app.core.modus_override` ist der seit S-074 existierende persistente
(In-Prozess) Modus-Override-Store, den `POST /api/control/modus`
(`app.api.control`) schreibt — diese Query liest ihn read-only (kein
`app.domain.execution`-Import hier, AC2-Boundary bleibt gewahrt: die
MVP-Live-Sperre selbst validiert bereits beim Schreiben in
`app.core.modus_override`, siehe dortiger Modul-Docstring). Jede der elf
Anlageklassen (`asset_class.id ∈ 1..11`, `docs/data-model.md` BR-100) löst
sich auf einen etwaigen Override oder sonst den globalen Modus auf.

**MinTRL-Restlaufzeit (AC24, S-078):** `mintrl_restlaufzeit` liest
`GateErgebnisRepository.letztes_ergebnis().min_trl` unverändert durch
(`None`, solange kein Stufe-B-Report vorliegt, → `[[lernschleife]]`#AC9).
`_mintrl_restlaufzeit_dto` formatiert die bereits berechnete Tage-Zahl NUR
für die Anzeige in einen Jahre-Klartext (`docs/specs/frontend-cockpit.md`
AC25-Beispiel "noch ≈ 2.7 Jahre bis statistisch signifikant") — kein
neuer statistischer Rechenpfad (AC24-Boundary: "kein neuer Rechenpfad im
Cockpit"), reine Einheiten-Umrechnung eines bereits vom Validierungs-Gate
gelieferten Werts."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.betriebssicherung import DrawdownStatus, HeartbeatEintrag, KillSwitchStatus
from app.contracts.depot import Modus
from app.contracts.llm_grounding import HalluzinationsKpiErgebnis
from app.contracts.system_status import MintrlRestlaufzeit, SystemStatusResponse
from app.core import drawdown_monitor, hallucination_kpi, heartbeat, kill_switch, modus_override
from app.domain.lernschleife.ports import GateErgebnisRepository

#: BR-100: `asset_class.id` liegt IMMER in 1..11 (DB-CHECK-Constraint,
#: `app.db.models.AssetClass`) — dieselbe Domäne, gegen die z. B.
#: `app.contracts.ausfuehrung_paper.OrderAnfrage.asset_class_id` validiert
#: (`Field(ge=1, le=11)`).
_ANLAGEKLASSEN_IDS: tuple[int, ...] = tuple(range(1, 12))

#: AC24/AC25 — reine Anzeige-Umrechnung Tage → Jahre für den MinTRL-
#: Klartext (julianisches Jahr, gängige Konvention für Tage/Jahre-
#: Umrechnungen; kein fachlicher Rechenpfad, siehe Moduldocstring).
_TAGE_PRO_JAHR = Decimal("365.25")


def _mintrl_restlaufzeit_dto(tage: Decimal) -> MintrlRestlaufzeit:
    """AC24/AC25 — formatiert die vom Validierungs-Gate gelieferte
    MinTRL-Restlaufzeit (Tage) zusätzlich als Jahre-Klartext für die
    Anzeige."""
    jahre = tage / _TAGE_PRO_JAHR
    return MintrlRestlaufzeit(
        tage=tage,
        klartext=f"noch ≈ {jahre:.1f} Jahre bis statistisch signifikant",
    )


def system_status_uebersicht(
    *, gate_ergebnis_repository: GateErgebnisRepository
) -> SystemStatusResponse:
    """AC8/AC24 — konsolidierter Betriebsstatus: Kill-Switch (→ BR-021),
    Modus global + je Anlageklasse (→ BR-019), Heartbeat je Modul,
    Drawdown, Halluzinations-KPI (→ BR-006), die zuletzt ermittelte
    Gate-Ampel (→ BR-025) und deren MinTRL-Restlaufzeit (AC24)."""
    kill_switch_status: KillSwitchStatus = kill_switch.status()
    heartbeats: tuple[HeartbeatEintrag, ...] = heartbeat.alle_heartbeats()
    drawdown_status: DrawdownStatus = drawdown_monitor.status()
    halluzinations_kpi: HalluzinationsKpiErgebnis = hallucination_kpi.aktueller_kpi()

    modus_konfiguration = modus_override.aktuelle_konfiguration()
    modus_je_anlageklasse: dict[int, Modus] = {
        asset_class_id: modus_konfiguration.modus_je_anlageklasse.get(
            asset_class_id, modus_konfiguration.global_modus
        )
        for asset_class_id in _ANLAGEKLASSEN_IDS
    }

    letztes_gate_ergebnis = gate_ergebnis_repository.letztes_ergebnis()
    mintrl_restlaufzeit = (
        _mintrl_restlaufzeit_dto(letztes_gate_ergebnis.min_trl)
        if letztes_gate_ergebnis is not None and letztes_gate_ergebnis.min_trl is not None
        else None
    )

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
        mintrl_restlaufzeit=mintrl_restlaufzeit,
    )
