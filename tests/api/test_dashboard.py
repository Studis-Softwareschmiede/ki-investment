"""Tests für den Depot-Dashboard-Endpunkt (`app.api.dashboard`, Story S-054,
`docs/specs/depot.md` AC11).

Covers (depot): AC11

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /dashboard/depot` ab (Status-Code +
Body-Shape) — Fake-`PositionRepository`/`LivePriceProvider` via
`app.dependency_overrides` (fastapi/A09), keine echte DB nötig (reine
Anzeige-Schicht, AC11: "hält keine eigene Preisanbindung"). Deckt: leeres
Depot, "nicht bewertbar" ohne Live-Kurs (`depot.md` Edge-Cases), korrekt
berechnetes laufendes Plus/Minus mit Live-Kurs, Lot-Aggregation über
mehrere offene Lots desselben Titels (FIFO, A2), Kauf-Historie-Filterung
(nur `richtung == "kauf"`), Mode-Isolation (BR-130, Query-Param
durchgereicht) und der Validierungs-Fehlerpfad bei ungültigem `mode`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.dashboard import get_live_price_provider, get_position_repository
from app.domain.portfolio.ports import ExitRegelnBestand, PositionsBestand, TransaktionsEintrag
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


def _kauf_eintrag(
    titel_id: str, *, trade_id: str, menge: Decimal, fill_preis: Decimal
) -> TransaktionsEintrag:
    return TransaktionsEintrag(
        trade_id=trade_id,
        titel_id=titel_id,
        richtung="kauf",
        menge=menge,
        fill_preis=fill_preis,
        arrival_price=fill_preis,
        slippage=Decimal("0"),
        kosten=Decimal("1"),
        waehrung="CHF",
        zeitstempel=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )


def _verkauf_eintrag(titel_id: str, *, trade_id: str) -> TransaktionsEintrag:
    return TransaktionsEintrag(
        trade_id=trade_id,
        titel_id=titel_id,
        richtung="verkauf",
        menge=Decimal("1"),
        fill_preis=Decimal("110"),
        arrival_price=Decimal("110"),
        slippage=Decimal("0"),
        kosten=Decimal("1"),
        waehrung="CHF",
        zeitstempel=datetime(2026, 7, 5, 10, 0, tzinfo=UTC),
    )


class _FakePositionRepository:
    """Test-Double des `PositionRepository`-Ports — implementiert nur die
    beiden vom Endpunkt tatsächlich aufgerufenen Methoden funktional."""

    def __init__(self, positionen, historie):
        self._positionen = positionen
        self._historie = historie
        self.abgefragte_modi: list[str] = []

    def alle_offenen_positionen(self, *, mode):
        self.abgefragte_modi.append(mode)
        return self._positionen

    def historie_je_titel(self, titel_id, *, mode):
        return self._historie.get(titel_id, [])

    def aktuelle_menge(self, titel_id, *, mode):  # pragma: no cover - vom Endpunkt nie aufgerufen
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


def test_leeres_depot_liefert_leere_titel_liste():
    repository = _FakePositionRepository(positionen=[], historie={})
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/dashboard/depot")

    assert resp.status_code == 200
    assert resp.json() == {"mode": "echt", "titel": []}
    assert repository.abgefragte_modi == ["echt"]


def test_position_ohne_live_kurs_ist_nicht_bewertbar():
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    repository = _FakePositionRepository(positionen=positionen, historie={})
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/dashboard/depot")

    assert resp.status_code == 200
    eintrag = resp.json()["titel"][0]
    assert eintrag["aktueller_preis"] is None
    assert eintrag["unrealisierter_gv_gesamt"] is None


def test_laufendes_plus_minus_mit_live_kurs():
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    repository = _FakePositionRepository(positionen=positionen, historie={})
    client = _client(repository, _FakeLivePriceProvider({"titel-1": Decimal("120")}))

    resp = client.get("/dashboard/depot")

    eintrag = resp.json()["titel"][0]
    assert eintrag["aktueller_preis"] == "120"
    # (120 - 100) * 10 = 200
    assert eintrag["unrealisierter_gv_gesamt"] == "200"


def test_mehrere_lots_desselben_titels_werden_aggregiert():
    positionen = [
        _position(
            "titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"), position_id="lot-1"
        ),
        _position("titel-1", menge=Decimal("5"), einstand_preis=Decimal("80"), position_id="lot-2"),
    ]
    repository = _FakePositionRepository(positionen=positionen, historie={})
    client = _client(repository, _FakeLivePriceProvider({"titel-1": Decimal("120")}))

    resp = client.get("/dashboard/depot")

    assert len(resp.json()["titel"]) == 1
    eintrag = resp.json()["titel"][0]
    assert eintrag["menge_gesamt"] == "15"
    # (120-100)*10 + (120-80)*5 = 200 + 200 = 400
    assert eintrag["unrealisierter_gv_gesamt"] == "400"


def test_kauf_historie_enthaelt_nur_kaeufe_keine_verkaeufe():
    positionen = [_position("titel-1", menge=Decimal("9"), einstand_preis=Decimal("100"))]
    historie = {
        "titel-1": [
            _kauf_eintrag(
                "titel-1", trade_id="t-1", menge=Decimal("10"), fill_preis=Decimal("100")
            ),
            _verkauf_eintrag("titel-1", trade_id="t-2"),
        ]
    }
    repository = _FakePositionRepository(positionen=positionen, historie=historie)
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/dashboard/depot")

    kauf_historie = resp.json()["titel"][0]["kauf_historie"]
    assert len(kauf_historie) == 1
    assert kauf_historie[0]["trade_id"] == "t-1"


def test_mode_query_param_wird_durchgereicht():
    repository = _FakePositionRepository(positionen=[], historie={})
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/dashboard/depot", params={"mode": "simuliert"})

    assert resp.status_code == 200
    assert resp.json()["mode"] == "simuliert"
    assert repository.abgefragte_modi == ["simuliert"]


def test_ungueltiger_mode_liefert_validierungsfehler():
    repository = _FakePositionRepository(positionen=[], historie={})
    client = _client(repository, _FakeLivePriceProvider({}))

    resp = client.get("/dashboard/depot", params={"mode": "unbekannt"})

    assert resp.status_code == 422
