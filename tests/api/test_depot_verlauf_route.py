"""Tests für den Depot-Verlauf-Endpunkt (`app.api.depot_verlauf`, Story
S-081, `docs/specs/frontend-cockpit.md` AC32/AC33).

Covers (frontend-cockpit): AC10, AC32

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/depot/verlauf` ab (Status-Code +
Body-Shape) — Fake-`PortfolioSnapshotRepository` via
`app.dependency_overrides` (fastapi/A09), keine echte DB nötig (reine
Anzeige-Schicht). Deckt: leere Liste (E2-Muster), ein vollständiger
Eintrag, Mode-/Zeitraum-Query-Parameter-Durchreichung, ungültiger `mode`
-> 422 (kein Crash)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.depot_verlauf import get_portfolio_snapshot_repository
from app.domain.portfolio_verlauf.ports import PortfolioSnapshotEintrag
from app.main import app


class _FakePortfolioSnapshotRepository:
    def __init__(self, eintraege: list[PortfolioSnapshotEintrag] | None = None):
        self._eintraege = eintraege or []
        self.aufrufe: list[dict[str, object]] = []

    def verlauf(self, *, mode, von=None, bis=None):
        self.aufrufe.append({"mode": mode, "von": von, "bis": bis})
        return self._eintraege


def _client(repository) -> TestClient:
    app.dependency_overrides[get_portfolio_snapshot_repository] = lambda: repository
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_leerer_verlauf() -> None:
    client = _client(_FakePortfolioSnapshotRepository())

    resp = client.get("/api/depot/verlauf")

    assert resp.status_code == 200
    assert resp.json() == {"mode": "echt", "eintraege": []}


def test_verlauf_liefert_zeitpunkt_wert_und_cash_quote() -> None:
    eintrag = PortfolioSnapshotEintrag(
        zeitpunkt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        portfolio_wert=Decimal("5000.00"),
        cash_quote=Decimal("9.500"),
    )
    client = _client(_FakePortfolioSnapshotRepository([eintrag]))

    resp = client.get("/api/depot/verlauf", params={"mode": "simuliert"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "simuliert"
    eintrag_json = body["eintraege"][0]
    assert eintrag_json["zeitpunkt"] == "2026-07-01T22:00:00Z"
    assert eintrag_json["portfolio_wert"] == "5000.00"
    assert eintrag_json["cash_quote"] == "9.500"


def test_mode_und_zeitraum_query_parameter_werden_durchgereicht() -> None:
    repository = _FakePortfolioSnapshotRepository()
    client = _client(repository)

    client.get(
        "/api/depot/verlauf",
        params={"mode": "simuliert", "von": "2026-06-01T00:00:00Z", "bis": "2026-06-30T00:00:00Z"},
    )

    aufruf = repository.aufrufe[0]
    assert aufruf["mode"] == "simuliert"
    assert aufruf["von"] is not None
    assert aufruf["bis"] is not None


def test_ungueltiger_mode_liefert_validierungsfehler_kein_crash() -> None:
    client = _client(_FakePortfolioSnapshotRepository())

    resp = client.get("/api/depot/verlauf", params={"mode": "unbekannt"})

    assert resp.status_code == 422
