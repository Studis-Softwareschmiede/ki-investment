"""Tests für die Depot-View (`app.api.ui.depot_view`/`depot_partial`,
Story S-071, `docs/specs/frontend-cockpit.md` AC14/AC19).

Covers (frontend-cockpit): AC14, AC19

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für `GET /ui/depot` UND den
Live-Polling-Partial `GET /ui/depot/partial` ab (Status-Code + gerenderte
HTML-Struktur), gegen dieselbe Query-Funktion (`hole_depot_uebersicht`) wie
`tests/api/test_depot_route.py` (AC1, kein zweiter Datenzusammenbau) — hier
über Fakes statt einer echten DB, analog `tests/api/test_depot_route.py`.

Deckt: KPI-Tiles (Portfolio-Wert/Cash-Quote/realisierter+unrealisierter
G/V, §7.1/§2.3), Depot-Datentabelle (Klassen-Chip §2.4, G/V-Kodierung §2.3,
"nicht bewertbar" = "—" E2), Empty-State je Modus (AC14), AC19-Live-
Polling-Markup (`hx-trigger`, `aria-live`, Stale-Hinweis-Element E1) sowie
den Partial-Endpunkt selbst (identisches Daten-Fragment, kein eigener
Datenzusammenbau)."""

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
    titel_id: str,
    *,
    menge: Decimal,
    einstand_preis: Decimal,
    asset_class_id: int = 1,
    position_id: str = "lot-1",
    symbol: str | None = None,
    name: str | None = None,
) -> PositionsBestand:
    return PositionsBestand(
        position_id=position_id,
        titel_id=titel_id,
        asset_class_id=asset_class_id,
        gics_branche="Technology",
        menge=menge,
        einstand_preis=einstand_preis,
        strategie="Index",
        exit_regeln=_exit_regeln_leer(),
        symbol=symbol,
        name=name,
    )


class _FakePositionRepository:
    def __init__(self, positionen, realisierter_gv_gesamt: Decimal = Decimal("0")):
        self._positionen = positionen
        self._realisierter_gv_gesamt = realisierter_gv_gesamt

    def alle_offenen_positionen(self, *, mode):
        return self._positionen

    def realisierter_gv_gesamt(self, *, mode):
        return self._realisierter_gv_gesamt


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


def test_leeres_depot_zeigt_definierten_empty_state() -> None:
    client = _client(_FakePositionRepository(positionen=[]), _FakeLivePriceProvider({}))

    resp = client.get("/ui/depot")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="depot-empty"' in html
    assert "Keine offenen Positionen im Modus ECHT" in html
    assert 'data-testid="table-depot"' not in html


def test_leeres_depot_simuliert_zeigt_modus_im_empty_state() -> None:
    client = _client(_FakePositionRepository(positionen=[]), _FakeLivePriceProvider({}))

    resp = client.get("/ui/depot", params={"mode": "simuliert"})

    assert "Keine offenen Positionen im Modus SIMULIERT" in resp.text


def test_leeres_depot_kpi_tiles_zeigen_neutrale_werte_ohne_null_vortaeuschung() -> None:
    client = _client(_FakePositionRepository(positionen=[]), _FakeLivePriceProvider({}))

    html = client.get("/ui/depot").text

    assert 'data-testid="tile-portfolio-wert"' in html
    assert 'data-testid="tile-cash-quote"' in html
    assert 'data-testid="tile-realisierter-gv"' in html
    assert 'data-testid="tile-unrealisierter-gv"' in html
    # Leeres Depot: 0 ist hier ein bekannter Fakt (kein "—"), aber mit
    # Vorzeichen (D4: "auch nicht bei 0 -> ±0").
    assert 'data-gv="neutral"' in html
    assert "±0.00" in html


def test_gefuelltes_depot_zeigt_titel_zeile_mit_klassen_chip_und_gv() -> None:
    positionen = [
        _position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"), asset_class_id=7)
    ]
    repository = _FakePositionRepository(
        positionen=positionen, realisierter_gv_gesamt=Decimal("50")
    )
    client = _client(repository, _FakeLivePriceProvider({"titel-1": Decimal("120")}))

    resp = client.get("/ui/depot")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="table-depot"' in html
    assert 'data-row-id="titel-1"' in html
    assert 'data-testid="klassen-chip"' in html
    assert 'data-anlageklasse="7"' in html
    assert "CRY" in html  # Kürzel Anlageklasse 7 (Kryptowährungen, design.md §2.4)
    # (120-100)*10 = 200 -> positiv, Vorzeichen + Glyph + Farbe (D3).
    assert 'data-gv="positiv"' in html
    assert "▲ +200.00" in html
    assert "100.0%" in html  # einziger Titel -> 100% Gewichtung (§3: 1-2 Dezimalstellen)


def test_titel_zeile_zeigt_lesbaren_titel_statt_roher_uuid() -> None:
    """Review-Finding Iteration 1 (Critical): die Titel-Spalte rendert
    Symbol + Name statt der rohen `titel_id`-UUID."""
    positionen = [
        _position(
            "titel-1",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
            symbol="AAPL",
            name="Apple Inc.",
        )
    ]
    client = _client(_FakePositionRepository(positionen=positionen), _FakeLivePriceProvider({}))

    html = client.get("/ui/depot").text

    assert 'data-testid="titel-name"' in html
    assert "AAPL" in html
    assert "Apple Inc." in html


def test_titel_zeile_faellt_ohne_symbol_auf_titel_id_zurueck() -> None:
    """Kein Symbol/Name vom Repository geliefert (z.B. Instrument-Daten
    fehlen) -> Fallback auf die `titel_id`, kein leeres Feld."""
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    client = _client(_FakePositionRepository(positionen=positionen), _FakeLivePriceProvider({}))

    html = client.get("/ui/depot").text

    assert 'data-testid="titel-name"' in html
    assert "titel-1" in html


def test_titel_ohne_live_kurs_zeigt_strich_statt_null_oder_farbe() -> None:
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    client = _client(_FakePositionRepository(positionen=positionen), _FakeLivePriceProvider({}))

    html = client.get("/ui/depot").text

    assert 'data-testid="live-kurs-unbekannt"' in html
    assert 'data-gv="unbekannt"' in html
    # Depotweites Total ebenfalls "nicht bewertbar" (AC14) statt Teil-Total.
    assert html.count('data-gv="unbekannt"') >= 2


def test_negativer_gv_zeigt_minus_glyph_und_farbklasse() -> None:
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    client = _client(
        _FakePositionRepository(positionen=positionen),
        _FakeLivePriceProvider({"titel-1": Decimal("80")}),
    )

    html = client.get("/ui/depot").text

    assert 'data-gv="negativ"' in html
    assert "▼ −200.00" in html


def test_live_polling_markup_ac19() -> None:
    client = _client(_FakePositionRepository(positionen=[]), _FakeLivePriceProvider({}))

    html = client.get("/ui/depot").text

    assert 'data-testid="depot-live-region"' in html
    assert 'hx-trigger="every 12s"' in html
    assert "/ui/depot/partial" in html
    assert 'aria-live="polite"' in html
    # E1: Stale-Hinweis-Element existiert (verborgen bis ein Poll fehlschlägt).
    assert 'data-testid="depot-stale-hinweis"' in html
    assert "hidden" in html


def test_reduced_motion_deaktiviert_animationen_global() -> None:
    """AC19: `prefers-reduced-motion` schaltet Swap-Highlights ab — hier
    über die bereits global in `shell.css` geltende Regel geprüft (Story
    S-071 fügt selbst keine eigene Swap-Highlight-Animation hinzu, siehe
    `views-depot.css`)."""
    client = _client(_FakePositionRepository(positionen=[]), _FakeLivePriceProvider({}))

    css = client.get("/static/css/shell.css").text

    assert "prefers-reduced-motion: reduce" in css


def test_partial_endpoint_liefert_dasselbe_datenfragment_ohne_shell() -> None:
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    client = _client(
        _FakePositionRepository(positionen=positionen),
        _FakeLivePriceProvider({"titel-1": Decimal("120")}),
    )

    resp = client.get("/ui/depot/partial")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="table-depot"' in html
    assert 'data-row-id="titel-1"' in html
    # Partial ist kein Voll-Dokument (kein Shell-Rundherum, AC19 "kleine
    # Partial-Endpunkte").
    assert "<html" not in html
    assert "<nav" not in html


def test_partial_endpoint_gibt_mode_query_param_an_repository_weiter() -> None:
    aufgerufene_modi: list[str] = []

    class _AufzeichnendesRepository(_FakePositionRepository):
        def alle_offenen_positionen(self, *, mode):
            aufgerufene_modi.append(mode)
            return self._positionen

    client = _client(_AufzeichnendesRepository(positionen=[]), _FakeLivePriceProvider({}))

    resp = client.get("/ui/depot/partial", params={"mode": "simuliert"})

    assert resp.status_code == 200
    assert aufgerufene_modi == ["simuliert"]


def test_ungueltiger_mode_liefert_validierungsfehler_kein_crash() -> None:
    client = _client(_FakePositionRepository(positionen=[]), _FakeLivePriceProvider({}))

    resp = client.get("/ui/depot", params={"mode": "unbekannt"})

    assert resp.status_code == 422
