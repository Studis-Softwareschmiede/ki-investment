"""Tests für die Query-Funktion `system_status_uebersicht` (Story S-068,
`docs/specs/frontend-cockpit.md` AC8/AC10; erweitert um AC24, Story
S-078).

Covers (frontend-cockpit): AC8, AC10, AC24

Deckt: Konsolidierung aller sechs Indikatoren (Kill-Switch, Modus je
Anlageklasse, Heartbeat, Drawdown, Halluzinations-KPI, Gate-Ampel),
Cold-Start ohne jede Gate-Auswertung (`gate_ampel=None`), Read-only-
Seiteneffektfreiheit (kein Alert/Kill-Switch-Trigger durch den Aufruf
selbst — belegt über `app.core.alerts.alle_alerts()`), dass ALLE elf
Anlageklassen (1..11) im `modus_je_anlageklasse`-Ergebnis auftauchen sowie
(AC24, S-078) die MinTRL-Restlaufzeit: `None` ohne Stufe-B-`min_trl` bzw.
ohne jede Gate-Auswertung, sonst Tage + Jahre-Klartext."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.api.queries.system_status import system_status_uebersicht
from app.contracts.llm_grounding import CrossCheckErgebnis
from app.core import (
    alerts,
    drawdown_monitor,
    hallucination_kpi,
    heartbeat,
    kill_switch,
    modus_override,
)
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
    modus_override.reset_fuer_tests()
    yield
    kill_switch.reset_fuer_tests()
    heartbeat.reset_fuer_tests()
    drawdown_monitor.reset_fuer_tests()
    hallucination_kpi.reset_fuer_tests()
    alerts.reset_fuer_tests()
    modus_override.reset_fuer_tests()


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
    Teilmenge; ohne einen zuvor über `app.core.modus_override` gesetzten
    Override (S-074) lösen alle auf den globalen Default 'simuliert' auf."""
    ergebnis = system_status_uebersicht(gate_ergebnis_repository=_FakeGateErgebnisRepository(None))

    assert ergebnis.modus_global == "simuliert"
    assert set(ergebnis.modus_je_anlageklasse.keys()) == set(range(1, 12))
    assert all(modus == "simuliert" for modus in ergebnis.modus_je_anlageklasse.values())


def test_modus_wird_aus_dem_seit_s074_existierenden_override_store_gelesen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace frontend-cockpit#AC8 — die Query liest den Modus über
    `app.core.modus_override.aktuelle_konfiguration()` (S-074-Schreibpfad
    `POST /api/control/modus`) statt eines hartkodierten Defaults; belegt
    per Monkeypatch (der reale Store lässt laut BR-019-Allowlist ohnehin
    nur `"simuliert"` zu, ein Wert-Vergleich allein könnte Delegation von
    Hardcoding nicht unterscheiden)."""
    from app.contracts.ausfuehrung_paper import ModusKonfiguration
    from app.core import modus_override

    monkeypatch.setattr(
        modus_override,
        "aktuelle_konfiguration",
        lambda: ModusKonfiguration(global_modus="echt", modus_je_anlageklasse={3: "simuliert"}),
    )

    ergebnis = system_status_uebersicht(gate_ergebnis_repository=_FakeGateErgebnisRepository(None))

    assert ergebnis.modus_global == "echt"
    assert ergebnis.modus_je_anlageklasse[3] == "simuliert"
    assert ergebnis.modus_je_anlageklasse[1] == "echt"


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


def test_mintrl_restlaufzeit_ist_none_ohne_gate_ergebnis() -> None:
    """@trace frontend-cockpit#AC24 — Cold-Start (keine Gate-Auswertung):
    `mintrl_restlaufzeit` ist `None`, nie 0/Farbzustand (E2-Muster)."""
    ergebnis = system_status_uebersicht(gate_ergebnis_repository=_FakeGateErgebnisRepository(None))

    assert ergebnis.mintrl_restlaufzeit is None


def test_mintrl_restlaufzeit_ist_none_ohne_stufe_b_min_trl() -> None:
    """@trace frontend-cockpit#AC24 — es liegt zwar eine Gate-Auswertung
    vor, aber (noch) keine Stufe-B-`min_trl` ("Stufe B nicht aktiv") →
    `None`."""
    repository = _FakeGateErgebnisRepository(
        LetztesGateErgebnis(
            ampel="gelb", ermittelt_am=datetime(2026, 7, 15, 12, 0, tzinfo=UTC), min_trl=None
        )
    )

    ergebnis = system_status_uebersicht(gate_ergebnis_repository=repository)

    assert ergebnis.mintrl_restlaufzeit is None


def test_mintrl_restlaufzeit_liefert_tage_und_jahre_klartext() -> None:
    """@trace frontend-cockpit#AC24/AC25 — liegt `min_trl` vor, trägt die
    Query sowohl den maschinenlesbaren Tage-Wert als auch den Jahre-
    Klartext (deckt exakt das Spec-Beispiel "noch ≈ 2.7 Jahre" ab,
    python/R14: nicht-runder Wert 986 Tage / 365.25 ≈ 2.6996...)."""
    repository = _FakeGateErgebnisRepository(
        LetztesGateErgebnis(
            ampel="gruen",
            ermittelt_am=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
            min_trl=Decimal("986"),
        )
    )

    ergebnis = system_status_uebersicht(gate_ergebnis_repository=repository)

    assert ergebnis.mintrl_restlaufzeit is not None
    assert ergebnis.mintrl_restlaufzeit.tage == Decimal("986")
    assert ergebnis.mintrl_restlaufzeit.klartext == "noch ≈ 2.7 Jahre bis statistisch signifikant"


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
