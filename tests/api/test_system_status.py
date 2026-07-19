"""Tests für den System-Status-Endpunkt (`app.api.system_status`, Story
S-068, `docs/specs/frontend-cockpit.md` AC8/AC10; erweitert um AC24,
Story S-078).

Covers (frontend-cockpit): AC8, AC10, AC24

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/system/status` ab (Status-Code
+ Body-Shape) — Fake-`GateErgebnisRepository` via `app.dependency_overrides`
(fastapi/A09), keine echte DB nötig (die vier `app.core.**`-Betriebs-
zustände sind In-Process-Singletons, per `reset_fuer_tests()` isoliert).
Deckt: Cold-Start (`response_model` erfüllt, `gate_ampel=None`), einen
ausgelösten Kill-Switch spiegelt sich im Response-Body wider, `modus_je_
anlageklasse` enthält alle elf Anlageklassen als String-Keys (JSON-Encoding
von `dict[int, Modus]`) sowie (AC24, S-078) `mintrl_restlaufzeit` im
Response-Body: `null` ohne `min_trl`, sonst `{tage, klartext}`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.system_status import get_gate_ergebnis_repository
from app.contracts.betriebssicherung import KillSwitchAusloeser
from app.core import alerts, drawdown_monitor, hallucination_kpi, heartbeat, kill_switch
from app.domain.lernschleife.ports import LetztesGateErgebnis
from app.main import app


class _FakeGateErgebnisRepository:
    def __init__(self, ergebnis: LetztesGateErgebnis | None) -> None:
        self._ergebnis = ergebnis

    def letztes_ergebnis(self) -> LetztesGateErgebnis | None:
        return self._ergebnis


def _client(gate_ergebnis: LetztesGateErgebnis | None) -> TestClient:
    app.dependency_overrides[get_gate_ergebnis_repository] = lambda: _FakeGateErgebnisRepository(
        gate_ergebnis
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolieren():
    kill_switch.reset_fuer_tests()
    heartbeat.reset_fuer_tests()
    drawdown_monitor.reset_fuer_tests()
    hallucination_kpi.reset_fuer_tests()
    alerts.reset_fuer_tests()
    yield
    app.dependency_overrides.clear()
    kill_switch.reset_fuer_tests()
    heartbeat.reset_fuer_tests()
    drawdown_monitor.reset_fuer_tests()
    hallucination_kpi.reset_fuer_tests()
    alerts.reset_fuer_tests()


def test_cold_start_liefert_200_mit_leerzustaenden_und_ohne_gate_ampel():
    client = _client(None)

    resp = client.get("/api/system/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["kill_switch"]["zustand"] == "normal"
    assert body["heartbeats"] == []
    assert body["drawdown"]["ueberwachungsluecke"] is True
    assert body["halluzinations_kpi"]["llm_status"] == "aktiv"
    assert body["gate_ampel"] is None
    assert body["gate_ampel_ermittelt_am"] is None
    assert body["mintrl_restlaufzeit"] is None


def test_modus_je_anlageklasse_enthaelt_alle_elf_anlageklassen_als_json():
    client = _client(None)

    resp = client.get("/api/system/status")

    modus_je_anlageklasse = resp.json()["modus_je_anlageklasse"]
    assert set(modus_je_anlageklasse.keys()) == {str(i) for i in range(1, 12)}
    assert all(modus == "simuliert" for modus in modus_je_anlageklasse.values())
    assert resp.json()["modus_global"] == "simuliert"


def test_ausgeloester_kill_switch_spiegelt_sich_im_response_wider():
    kill_switch.ausloesen(
        KillSwitchAusloeser(
            quelle="manuell",
            zeitstempel=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
            grund="Test-Auslösung",
        )
    )
    client = _client(None)

    resp = client.get("/api/system/status")

    kill_switch_body = resp.json()["kill_switch"]
    assert kill_switch_body["zustand"] == "angehalten"
    assert kill_switch_body["quelle"] == "manuell"


def test_gate_ampel_wird_aus_dem_repository_uebernommen():
    zeitpunkt = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    client = _client(LetztesGateErgebnis(ampel="rot", ermittelt_am=zeitpunkt))

    resp = client.get("/api/system/status")

    body = resp.json()
    assert body["gate_ampel"] == "rot"
    assert body["gate_ampel_ermittelt_am"] is not None


def test_mintrl_restlaufzeit_im_response_body_wenn_min_trl_vorliegt():
    """@trace frontend-cockpit#AC24 — der volle HTTP-Pfad liefert
    `mintrl_restlaufzeit` als `{tage, klartext}`-Objekt, sobald das
    Repository ein `min_trl` liefert."""
    zeitpunkt = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    client = _client(
        LetztesGateErgebnis(ampel="gruen", ermittelt_am=zeitpunkt, min_trl=Decimal("986"))
    )

    resp = client.get("/api/system/status")

    body = resp.json()
    assert body["mintrl_restlaufzeit"] == {
        "tage": "986",
        "klartext": "noch ≈ 2.7 Jahre bis statistisch signifikant",
    }
