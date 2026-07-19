"""Tests für den Warteliste-Endpunkt (`app.api.warteliste`, Story S-079,
`docs/specs/frontend-cockpit.md` AC26).

Covers (frontend-cockpit): AC26

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/warteliste` ab (Status-Code +
Body-Shape) — Fake-`WartelisteRepository` via `app.dependency_overrides`
(fastapi/A09), keine echte DB nötig (reine Anzeige-Schicht). Deckt: leere
Liste, ein vollständiger Eintrag (Titel/Klasse/Grösse/Blockade-Grund/
Zeitpunkt), Mode-Query-Parameter-Durchreichung an die Query-Funktion."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.warteliste import get_warteliste_repository
from app.domain.warteliste.ports import WartelisteEintrag
from app.main import app


class _FakeWartelisteRepository:
    def __init__(self, eintraege: list[WartelisteEintrag] | None = None):
        self._eintraege = eintraege or []
        self.aufrufe: list[dict[str, object]] = []

    def liste_warteliste(self, *, mode):
        self.aufrufe.append({"mode": mode})
        return self._eintraege


def _client(repository) -> TestClient:
    app.dependency_overrides[get_warteliste_repository] = lambda: repository
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_leere_warteliste() -> None:
    client = _client(_FakeWartelisteRepository())

    resp = client.get("/api/warteliste")

    assert resp.status_code == 200
    assert resp.json() == {"mode": "echt", "eintraege": []}


def test_warteliste_liefert_titel_klasse_groesse_blockade_grund_und_zeitpunkt() -> None:
    eintrag = WartelisteEintrag(
        id="w-1",
        titel_id="titel-1",
        titel="CHSPI",
        name="iShares Swiss Dividend ETF",
        asset_class_id=2,
        geplante_groesse=Decimal("5000"),
        blockade_grund="klumpenrisiko",
        blockiert_am=datetime(2026, 6, 10, 8, 30, tzinfo=UTC),
    )
    client = _client(_FakeWartelisteRepository([eintrag]))

    resp = client.get("/api/warteliste", params={"mode": "simuliert"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "simuliert"
    eintrag_json = body["eintraege"][0]
    assert eintrag_json["titel"] == "CHSPI"
    assert eintrag_json["name"] == "iShares Swiss Dividend ETF"
    assert eintrag_json["asset_class_id"] == 2
    assert eintrag_json["geplante_groesse"] == "5000"
    assert eintrag_json["blockade_grund"] == "klumpenrisiko"
    assert eintrag_json["blockiert_am"] == "2026-06-10T08:30:00Z"


def test_mode_query_parameter_wird_an_repository_durchgereicht() -> None:
    repository = _FakeWartelisteRepository()
    client = _client(repository)

    client.get("/api/warteliste", params={"mode": "simuliert"})

    assert repository.aufrufe[0]["mode"] == "simuliert"
