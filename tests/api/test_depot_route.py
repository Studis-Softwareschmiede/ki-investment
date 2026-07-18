"""Tests für den Depot-Read-Endpunkt (`app.api.depot`, Story S-065,
`docs/specs/frontend-cockpit.md` AC1/AC3/AC10).

Covers (frontend-cockpit): AC1, AC3, AC10

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/depot` ab (Status-Code +
Body-Shape, `response_model=DepotUebersichtResponse`, AC10) — Fake-
`PositionRepository`/`LivePriceProvider` via `app.dependency_overrides`
(fastapi/A09), keine echte DB nötig, analog `tests/api/test_dashboard.py`
(S-054). Deckt: leeres Depot (Happy-Path, 200 + erwartete Body-Shape),
gefülltes Depot inkl. Portfolio-Aggregat + realisiertem G/V, Mode-Isolation
(BR-130, Query-Param wird an beide Repository-Methoden durchgereicht) und
den Validierungs-Fehlerpfad bei ungültigem `mode` (422, kein Crash)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.depot import get_live_price_provider, get_position_repository
from app.domain.portfolio.ports import ExitRegelnBestand, PositionsBestand
from app.main import app


def _exit_regeln_leer() -> ExitRegelnBestand:
    return ExitRegelnBestand(
        stop_loss_pct=None,
        take_profit_pct=None,
        stop_typ=None,
        atr_multiplikator=None,
        thesis_invalidation=None,
        time_box=None,
    )


def _position(
    titel_id: str, *, menge: Decimal, einstand_preis: Decimal, position_id: str = "lot-1"
) -> PositionsBestand:
    return PositionsBestand(
        position_id=position_id,
        titel_id=titel_id,
        asset_class_id=1,
        gics_branche="Technology",
        menge=menge,
        einstand_preis=einstand_preis,
        strategie="Index",
        exit_regeln=_exit_regeln_leer(),
    )


class _FakePositionRepository:
    """Test-Double des `PositionRepository`-Ports — implementiert nur die
    vom Endpunkt tatsächlich aufgerufenen Methoden funktional."""

    def __init__(self, positionen, realisierter_gv_gesamt: Decimal = Decimal("0")):
        self._positionen = positionen
        self._realisierter_gv_gesamt = realisierter_gv_gesamt
        self.abgefragte_modi: list[str] = []
        self.realisierter_gv_modi: list[str] = []

    def alle_offenen_positionen(self, *, mode):
        self.abgefragte_modi.append(mode)
        return self._positionen

    def realisierter_gv_gesamt(self, *, mode):
        self.realisierter_gv_modi.append(mode)
        return self._realisierter_gv_gesamt

    def aktuelle_menge(self, titel_id, *, mode):  # pragma: no cover
        raise NotImplementedError

    def offene_positionen(self, titel_id, *, mode):  # pragma: no cover
        raise NotImplementedError

    def lege_position_an(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def aktualisiere_kauf(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def verbuche_verkauf_lot(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def markiere_fill_verbucht(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def schreibe_transaktion(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def historie_je_titel(self, titel_id, *, mode):  # pragma: no cover
        raise NotImplementedError


class _FakeLivePriceProvider:
    def __init__(self, preise: dict[str, Decimal]):
        self._preise = preise

    def aktueller_preis(self, titel_id):
        return self._preise.get(titel_id)


def _client(repository, live_price) -> TestClient:
    app.dependency_overrides[get_position_repository] = lambda: repository
    app.dependency_overrides[get_live_price_provider] = lambda: live_price
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_leeres_depot_liefert_leere_titel_liste_und_leere_aggregate():
    repository = _FakePositionRepository(positionen=[])
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/api/depot")

    assert resp.status_code == 200
    assert resp.json() == {
        "mode": "echt",
        "titel": [],
        "portfolio_aggregat": {
            "branchen_gewichtung": {},
            "klassen_gewichtung": {},
            "cash_quote": "0",
        },
        "realisierter_gv_gesamt": "0",
    }
    assert repository.abgefragte_modi == ["echt"]
    assert repository.realisierter_gv_modi == ["echt"]


def test_gefuelltes_depot_liefert_bestand_aggregat_und_realisierten_gv():
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    repository = _FakePositionRepository(
        positionen=positionen, realisierter_gv_gesamt=Decimal("150")
    )
    client = _client(repository, _FakeLivePriceProvider({"titel-1": Decimal("120")}))

    resp = client.get("/api/depot")

    assert resp.status_code == 200
    body = resp.json()
    eintrag = body["titel"][0]
    assert eintrag["titel_id"] == "titel-1"
    assert eintrag["menge"] == "10"
    assert eintrag["einstand_preis"] == "100"
    assert eintrag["aktueller_preis"] == "120"
    # (120 - 100) * 10 = 200
    assert eintrag["unrealisierter_gv"] == "200"
    assert body["portfolio_aggregat"]["klassen_gewichtung"] == {"1": "100.000"}
    assert body["realisierter_gv_gesamt"] == "150"


def test_mode_query_param_wird_an_beide_repository_methoden_durchgereicht():
    repository = _FakePositionRepository(positionen=[])
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/api/depot", params={"mode": "simuliert"})

    assert resp.status_code == 200
    assert resp.json()["mode"] == "simuliert"
    assert repository.abgefragte_modi == ["simuliert"]
    assert repository.realisierter_gv_modi == ["simuliert"]


def test_ungueltiger_mode_liefert_validierungsfehler():
    repository = _FakePositionRepository(positionen=[])
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/api/depot", params={"mode": "unbekannt"})

    assert resp.status_code == 422
