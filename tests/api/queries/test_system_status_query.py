"""Tests für die Query-Funktion `system_status_uebersicht` (Story S-068,
`docs/specs/frontend-cockpit.md` AC8/AC10).

Covers (frontend-cockpit): AC8, AC10

Deckt: Konsolidierung aller sechs Indikatoren (Kill-Switch, Modus je
Anlageklasse, Heartbeat, Drawdown, Halluzinations-KPI, Gate-Ampel),
Cold-Start ohne jede Gate-Auswertung (`gate_ampel=None`), Read-only-
Seiteneffektfreiheit (kein Alert/Kill-Switch-Trigger durch den Aufruf
selbst — belegt über `app.core.alerts.alle_alerts()`), sowie dass ALLE elf
Anlageklassen (1..11) im `modus_je_anlageklasse`-Ergebnis auftauchen."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.queries.system_status import system_status_uebersicht
from app.contracts.llm_grounding import CrossCheckErgebnis
from app.core import alerts, drawdown_monitor, hallucination_kpi, heartbeat, kill_switch
from app.domain.lernschleife.ports import LetztesGateErgebnis


class _FakeGateErgebnisRepository:
    def __init__(self, ergebnis: LetztesGateErgebnis | None) -> None:
        self._ergebnis = ergebnis

    def letztes_ergebnis(self) -> LetztesGateErgebnis | None:
        return self._ergebnis


@pytest.fixture(autouse=True)
def _zustand_isolieren():
    kill_switch.reset_fuer_tests()
    heartbeat.reset_fuer_tests()
    drawdown_monitor.reset_fuer_tests()
    hallucination_kpi.reset_fuer_tests()
    alerts.reset_fuer_tests()
    yield
    kill_switch.reset_fuer_tests()
    heartbeat.reset_fuer_tests()
    drawdown_monitor.reset_fuer_tests()
    hallucination_kpi.reset_fuer_tests()
    alerts.reset_fuer_tests()


def test_cold_start_liefert_konsistente_leerzustaende_ohne_gate_ergebnis() -> None:
    """@trace frontend-cockpit#AC8 — ohne jede vorherige Aktivität (frischer
    Prozessstart): Kill-Switch `normal`, keine Heartbeats, Drawdown-
    Überwachungslücke, Halluzinations-KPI `aktiv`/Quote 0, keine
    Gate-Auswertung (`gate_ampel=None`)."""
    ergebnis = system_status_uebersicht(gate_ergebnis_repository=_FakeGateErgebnisRepository(None))

    assert ergebnis.kill_switch.zustand == "normal"
    assert ergebnis.heartbeats == ()
    assert ergebnis.drawdown.ueberwachungsluecke is True
    assert ergebnis.halluzinations_kpi.llm_status == "aktiv"
    assert ergebnis.gate_ampel is None
    assert ergebnis.gate_ampel_ermittelt_am is None


def test_modus_je_anlageklasse_deckt_alle_elf_anlageklassen_ab() -> None:
    """@trace frontend-cockpit#AC8 — BR-019: "aktiven Modus je
    Anlageklasse" deckt ALLE elf Anlageklassen (1..11) ab, nicht nur eine
    Teilmenge; ohne persistenten Override-Store (Cold-Start, S-074-Scope)
    lösen alle auf den globalen Default 'simuliert' auf."""
    ergebnis = system_status_uebersicht(gate_ergebnis_repository=_FakeGateErgebnisRepository(None))

    assert ergebnis.modus_global == "simuliert"
    assert set(ergebnis.modus_je_anlageklasse.keys()) == set(range(1, 12))
    assert all(modus == "simuliert" for modus in ergebnis.modus_je_anlageklasse.values())


def test_konsolidiert_kill_switch_heartbeat_drawdown_kpi_zustand() -> None:
    """@trace frontend-cockpit#AC8 — die Query spiegelt den TATSÄCHLICHEN
    Zustand der vier `app.core.**`-Module wider (kein eigener,
    abweichender Zustand)."""
    t0 = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
    heartbeat.registriere_modul("ingest", timedelta(minutes=5), jetzt=t0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), t0)
    hallucination_kpi.registriere_ergebnis(CrossCheckErgebnis(status="verworfen"), zeitpunkt=t0)

    ergebnis = system_status_uebersicht(gate_ergebnis_repository=_FakeGateErgebnisRepository(None))

    assert len(ergebnis.heartbeats) == 1
    assert ergebnis.heartbeats[0].modul_id == "ingest"
    assert ergebnis.drawdown.ueberwachungsluecke is False
    assert ergebnis.drawdown.drawdown_pct == Decimal("0")
    assert ergebnis.halluzinations_kpi.geprueft == 1
    assert ergebnis.halluzinations_kpi.verworfen == 1


def test_gate_ampel_wird_aus_dem_repository_uebernommen() -> None:
    """@trace frontend-cockpit#AC8 — liegt eine Gate-Auswertung vor, wird
    deren Ampel + Zeitpunkt unverändert übernommen (→ BR-025)."""
    zeitpunkt = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    repository = _FakeGateErgebnisRepository(
        LetztesGateErgebnis(ampel="gruen", ermittelt_am=zeitpunkt)
    )

    ergebnis = system_status_uebersicht(gate_ergebnis_repository=repository)

    assert ergebnis.gate_ampel == "gruen"
    assert ergebnis.gate_ampel_ermittelt_am == zeitpunkt


def test_aufruf_selbst_loest_keinen_alert_und_keinen_kill_switch_aus() -> None:
    """@trace frontend-cockpit#AC2/AC8 — die Query ist rein lesend: selbst
    ein Drawdown weit über der Kill-Schwelle (der `pruefe_drawdown()`
    triggern würde) darf durch den blossen Query-Aufruf KEINEN Alert und
    KEINEN Kill-Switch-Trigger auslösen (S-068 nutzt bewusst die reinen
    `status()`/`aktueller_kpi()`-Gegenstücke, nicht die alarmierenden
    Originalfunktionen)."""
    t0 = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), t0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("50000"), t0)  # -50 %, weit über Kill

    system_status_uebersicht(gate_ergebnis_repository=_FakeGateErgebnisRepository(None))

    assert alerts.alle_alerts() == ()
    assert kill_switch.status().zustand == "normal"
