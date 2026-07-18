"""Tests für die Konfigurations-Read-Endpunkte `app/api/config.py` (Story
S-069, `docs/specs/frontend-cockpit.md` AC9/AC10).

Covers (frontend-cockpit): AC9, AC10

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/config/anlageklassen` +
`GET /api/config/depotstrategie` ab (Status-Code + Body-Shape) — Fake-
Lese-Callables via `app.dependency_overrides` (fastapi/A09, analog
`tests/api/test_dashboard.py`), keine echte DB nötig."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.config import get_anlageklassen_reader, get_depotstrategie_reader
from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.contracts.risikomanagement import DepotstrategieKonfiguration
from app.main import app


def _client(*, anlageklassen=None, depotstrategie=None) -> TestClient:
    app.dependency_overrides[get_anlageklassen_reader] = lambda: lambda: anlageklassen or []
    app.dependency_overrides[get_depotstrategie_reader] = lambda: lambda: depotstrategie
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_anlageklassen_liefert_toggle_zustand_und_prio() -> None:
    anlageklassen = [
        AnlageklasseEintrag(id=1, name="Aktien", aktiv=True, prio_stufe="MVP"),
        AnlageklasseEintrag(id=10, name="FX", aktiv=False, prio_stufe="Stufe3"),
    ]
    client = _client(anlageklassen=anlageklassen)

    resp = client.get("/api/config/anlageklassen")

    assert resp.status_code == 200
    assert resp.json() == [
        {"id": 1, "name": "Aktien", "aktiv": True, "prio_stufe": "MVP"},
        {"id": 10, "name": "FX", "aktiv": False, "prio_stufe": "Stufe3"},
    ]


def test_anlageklassen_liefert_leere_liste_ohne_daten() -> None:
    client = _client()

    resp = client.get("/api/config/anlageklassen")

    assert resp.status_code == 200
    assert resp.json() == []


def test_depotstrategie_liefert_aktive_grenzwerte_und_preset() -> None:
    strategie_id = uuid.uuid4()
    konfiguration = DepotstrategieKonfiguration(
        portfolio_strategy_id=strategie_id,
        risk_profile_name="ausgewogen",
        max_einzelposition_pct=Decimal("5"),
        max_sektor_pct=Decimal("20"),
        cash_quote_ziel_pct=Decimal("5"),
        gesamt_exposure_cap_pct=Decimal("25"),
        max_anlageklasse_pct={7: Decimal("10")},
    )
    client = _client(depotstrategie=konfiguration)

    resp = client.get("/api/config/depotstrategie")

    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_profile_name"] == "ausgewogen"
    assert body["max_einzelposition_pct"] == "5"
    assert body["max_anlageklasse_pct"] == {"7": "10"}


def test_depotstrategie_liefert_null_ohne_aktives_preset() -> None:
    client = _client(depotstrategie=None)

    resp = client.get("/api/config/depotstrategie")

    assert resp.status_code == 200
    assert resp.json() is None
