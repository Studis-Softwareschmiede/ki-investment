"""Tests für die Offene-Entscheide-JSON-Route (`app.api.entscheide`),
Story S-080, `docs/specs/frontend-cockpit.md` AC29/AC31.

Covers (frontend-cockpit): AC29, AC31

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/entscheide/offen` ab
(Status-Code + Body-Shape) — Fake-`HybridEntscheidungRepository` via
`app.dependency_overrides`, `Settings`-Override für das AC31-Feature-Gate
(keine echte DB nötig)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.entscheide import get_hybrid_entscheidung_repository
from app.config import Settings, get_settings
from app.domain.hybrid_entscheidung.ports import OffenerEntscheidZeile
from app.main import app


class _FakeHybridEntscheidungRepository:
    def __init__(self, eintraege: list[OffenerEntscheidZeile]):
        self._eintraege = eintraege

    def offene_entscheide(self) -> list[OffenerEntscheidZeile]:
        return self._eintraege


def _zeile() -> OffenerEntscheidZeile:
    return OffenerEntscheidZeile(
        entscheid_id="e-1",
        titel_id="titel-1",
        titel="ROG",
        name="Roche Holding AG",
        richtung="kauf",
        groesse=Decimal("5"),
        vorgeschlagene_order="Market-Buy 5 Stk. Roche Holding AG",
        frist=datetime(2026, 7, 20, 16, 0, tzinfo=UTC),
        begruendung="Gesamtscore 8.5 (KAUF-Schwelle).",
        erstellt_am=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    )


def _client(repository, *, feature_aktiv: bool) -> TestClient:
    app.dependency_overrides[get_hybrid_entscheidung_repository] = lambda: repository
    app.dependency_overrides[get_settings] = lambda: Settings(
        hybrid_bestaetigung_aktiv=feature_aktiv
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_feature_inaktiv_liefert_leere_liste():
    """@trace frontend-cockpit#AC31 — Default-aus: leere Liste,
    `feature_aktiv=false` im Body."""
    client = _client(_FakeHybridEntscheidungRepository([_zeile()]), feature_aktiv=False)

    resp = client.get("/api/entscheide/offen")

    assert resp.status_code == 200
    assert resp.json() == {"feature_aktiv": False, "entscheide": []}


def test_feature_aktiv_liefert_offene_entscheide_mit_allen_ac29_feldern():
    """@trace frontend-cockpit#AC29 — Titel, Richtung, Grösse,
    vorgeschlagene Order, Frist, Begründung im Response-Body."""
    client = _client(_FakeHybridEntscheidungRepository([_zeile()]), feature_aktiv=True)

    resp = client.get("/api/entscheide/offen")

    assert resp.status_code == 200
    body = resp.json()
    assert body["feature_aktiv"] is True
    assert len(body["entscheide"]) == 1
    eintrag = body["entscheide"][0]
    assert eintrag["entscheid_id"] == "e-1"
    assert eintrag["titel"] == "ROG"
    assert eintrag["name"] == "Roche Holding AG"
    assert eintrag["richtung"] == "kauf"
    assert eintrag["groesse"] == "5"
    assert eintrag["vorgeschlagene_order"] == "Market-Buy 5 Stk. Roche Holding AG"
    assert eintrag["begruendung"] == "Gesamtscore 8.5 (KAUF-Schwelle)."


def test_feature_aktiv_ohne_eintraege_liefert_leere_liste():
    """@trace frontend-cockpit#AC29 — solange der autonome Paper-Modus
    aktiv ist (keine offenen Entscheide), ist die Liste leer."""
    client = _client(_FakeHybridEntscheidungRepository([]), feature_aktiv=True)

    resp = client.get("/api/entscheide/offen")

    assert resp.status_code == 200
    assert resp.json() == {"feature_aktiv": True, "entscheide": []}
