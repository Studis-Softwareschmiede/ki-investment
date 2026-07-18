"""Tests für die Trade-Historie-JSON-Route (`app.api.trades`), Story S-067,
`docs/specs/frontend-cockpit.md` AC6/AC7.

Covers (frontend-cockpit): AC6, AC7

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/trades` ab (Status-Code +
Body-Shape) — Fake-`PositionRepository` via `app.dependency_overrides`
(fastapi/A09), keine echte DB nötig. Deckt: leere Historie, depotweite
Fills mit allen AC6-Feldern (inkl. Slippage/TCA + FX-Split), die
Filter-Query-Parameter (`mode`/`titel`/`von`/`bis`, durchgereicht an
`PositionRepository.historie_depotweit`, AC7-Gap-Schluss) und den
Validierungs-Fehlerpfad bei ungültigem `mode`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.trades import get_position_repository
from app.domain.portfolio.ports import TransaktionsEintrag
from app.main import app


def _trade(
    *, trade_id: str, titel_id: str = "titel-1", richtung: str = "kauf"
) -> TransaktionsEintrag:
    return TransaktionsEintrag(
        trade_id=trade_id,
        titel_id=titel_id,
        richtung=richtung,
        menge=Decimal("10"),
        fill_preis=Decimal("101.5"),
        arrival_price=Decimal("100"),
        slippage=Decimal("1.5"),
        kosten=Decimal("5"),
        waehrung="CHF",
        zeitstempel=datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        fx_rate=Decimal("1.1"),
        kapital_gv_chf=Decimal("2"),
        waehrungs_gv_chf=Decimal("0.5"),
    )


class _FakePositionRepository:
    """Test-Double des `PositionRepository`-Ports — implementiert nur die
    von der Route tatsächlich aufgerufene Methode funktional, alle
    übrigen Port-Methoden würden bei Aufruf einen Test-Fehler auslösen."""

    def __init__(self, trades: list[TransaktionsEintrag]):
        self._trades = trades
        self.aufrufe: list[dict[str, object]] = []

    def historie_depotweit(self, *, mode, titel_id=None, von=None, bis=None):
        self.aufrufe.append({"mode": mode, "titel_id": titel_id, "von": von, "bis": bis})
        return self._trades

    def aktuelle_menge(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def offene_positionen(self, *args, **kwargs):  # pragma: no cover
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

    def historie_je_titel(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def alle_offenen_positionen(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError


def _client(repository) -> TestClient:
    app.dependency_overrides[get_position_repository] = lambda: repository
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_leere_historie_liefert_leere_trade_liste():
    """@trace frontend-cockpit#AC6 — kein Fill im Modus ergibt eine leere
    Liste, keinen Fehler."""
    repository = _FakePositionRepository([])
    client = _client(repository)

    resp = client.get("/api/trades")

    assert resp.status_code == 200
    assert resp.json() == {"mode": "echt", "trades": []}
    assert repository.aufrufe == [{"mode": "echt", "titel_id": None, "von": None, "bis": None}]


def test_trade_traegt_alle_ac6_felder():
    """@trace frontend-cockpit#AC6 — Titel, Richtung, Menge, Fill-Preis,
    Arrival-Price, Slippage/TCA, Kosten, FX-Split (fx_rate/kapital_gv_chf/
    waehrungs_gv_chf) und Zeit sind im Response-Body vorhanden."""
    repository = _FakePositionRepository([_trade(trade_id="t-1")])
    client = _client(repository)

    resp = client.get("/api/trades")

    assert resp.status_code == 200
    trade = resp.json()["trades"][0]
    assert trade["titel_id"] == "titel-1"
    assert trade["richtung"] == "kauf"
    assert trade["menge"] == "10"
    assert trade["fill_preis"] == "101.5"
    assert trade["arrival_price"] == "100"
    assert trade["slippage"] == "1.5"
    assert trade["kosten"] == "5"
    assert trade["fx_rate"] == "1.1"
    assert trade["kapital_gv_chf"] == "2"
    assert trade["waehrungs_gv_chf"] == "0.5"
    assert trade["zeitstempel"] == "2026-07-12T10:00:00Z"


def test_filter_query_parameter_werden_an_das_repository_durchgereicht():
    """@trace frontend-cockpit#AC6,AC7 — `mode`/`titel`/`von`/`bis`
    (Verträge: `GET /api/trades?mode=&titel=&von=&bis=`) landen unverändert
    bei `PositionRepository.historie_depotweit`."""
    repository = _FakePositionRepository([])
    client = _client(repository)

    resp = client.get(
        "/api/trades",
        params={
            "mode": "simuliert",
            "titel": "titel-42",
            "von": "2026-07-01T00:00:00Z",
            "bis": "2026-07-31T23:59:59Z",
        },
    )

    assert resp.status_code == 200
    aufruf = repository.aufrufe[0]
    assert aufruf["mode"] == "simuliert"
    assert aufruf["titel_id"] == "titel-42"
    assert aufruf["von"] == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    assert aufruf["bis"] == datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC)


def test_ungueltiger_mode_liefert_validierungsfehler():
    """@trace frontend-cockpit#AC6 — `mode` ausserhalb von echt/simuliert
    (BR-130) wird von FastAPI/pydantic abgelehnt, bevor das Repository
    aufgerufen wird."""
    repository = _FakePositionRepository([])
    client = _client(repository)

    resp = client.get("/api/trades", params={"mode": "unbekannt"})

    assert resp.status_code == 422
    assert repository.aufrufe == []
