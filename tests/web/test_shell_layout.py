"""Tests für die Cockpit-Shell (`app/api/ui.py` + `app/web/templates/**`,
Story S-064).

Covers (frontend-cockpit): AC11, AC13

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für alle fünf `/ui/**`-Routen
ab (Status-Code + gerenderte HTML-Struktur), nicht nur den Template-Aufbau
isoliert. Geprüft werden die AC11/AC13-Struktur-/A11y-Invarianten: feste
3-Zonen-Shell (genau eine `<header>`/`<nav>`/`<main>` je Seite, WCAG 2.4.1),
Skip-Link zu `<main>`, genau ein `<h1>` je View, aktiver Nav-Eintrag über
`aria-current`, Nav mit den fünf Kern-Views, die sechs Statusleisten-
Indikatoren (Ampel/Kill-Switch/Modus/Heartbeat/Drawdown/Halluzinations-KPI)
mit Text **und** Icon (D3 — nie nur Farbe) auf jeder View identisch (D2/
WCAG 3.2.3).

**S-073-Nachzug:** `/ui/trades` bezieht seit Story S-073 (AC16) echte Daten
über `PositionRepository` (`app.api.trades.get_position_repository`,
DB-Session-DI) statt eines reinen Platzhalters — die generischen
Shell-Struktur-Tests hier iterieren über alle fünf Views und liefen daher
ohne DB gegen `/ui/trades` mit einem `RuntimeError` (fehlende
`DB_*`-Env-Vars) ins Leere. Ein modulweites `dependency_overrides` auf ein
leeres Fake-Repository hält diese Datei DB-frei (identisches Test-Double-
Muster wie `tests/api/test_trades.py`/`tests/web/test_trades_view.py`) —
die Struktur-Assertions (Landmarks, `<h1>`, Statusleiste) bleiben davon
unberührt (leere Trade-Historie rendert weiterhin eine gültige Seite,
siehe Empty-State AC16).

**Story S-071 (AC14):** `/ui/depot` liest seit dieser Story real über
`app.api.queries.depot.hole_depot_uebersicht` (DI, keine Platzhalter-Route
mehr) — die `client`-Fixture überschreibt die Depot-DI deshalb mit einem
leeren Fake-Depot (analog `tests/api/test_depot_route.py`), damit diese
generischen, über alle fünf Views parametrisierten Struktur-Tests ohne
echte DB laufen. Die Depot-Inhalts-Tests (KPI-Tiles/Datentabelle/Live-
Polling) liegen dediziert in `tests/web/test_ui_depot.py`.

**Story S-076 (AC18):** `/ui/konfiguration` liest seit dieser Story real
über `lade_anlageklassen_konfiguration`/`lade_depotstrategie_konfiguration`
(DI über `app.api.config`, DB-Session-gebunden) — die `_db_freie_view_
overrides`-Fixture überschreibt beide DI-Factories deshalb mit leeren
Fake-Callables (analog `tests/api/test_config_route.py`), damit diese
generischen Struktur-Tests ohne echte DB laufen. Die Konfigurations-
Inhalts-Tests (Toggle-Liste, BR-018-Warn-Band, Depotstrategie-Anzeige)
liegen dediziert in `tests/web/test_ui_konfiguration.py`."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.config import get_anlageklassen_reader, get_depotstrategie_reader
from app.api.depot import get_live_price_provider
from app.api.depot import get_position_repository as get_depot_position_repository
from app.api.kandidaten import get_kandidaten_repository
from app.api.trades import get_position_repository
from app.main import app


class _LeeresFakePositionRepository:
    """Minimaler Fake — `/ui/trades` (S-073) braucht für die reinen
    Struktur-Tests hier keine echten Trades, nur eine DB-freie
    `historie_depotweit`-Implementierung (leere Liste, Empty-State)."""

    def historie_depotweit(self, *, mode, titel_id=None, von=None, bis=None):
        return []


class _LeereKandidatenRepository:
    """Story S-072 macht `/ui/kandidaten` zu einer echten, DB-gespeisten
    Route (AC15) — dieser Fake hält die Shell-Tests hier weiterhin DB-frei
    (analog `tests/api/test_kandidaten.py`), ohne den Struktur-/A11y-Scope
    dieser Datei (AC11/AC13) zu erweitern."""

    def liste_kandidaten(self) -> list[object]:
        return []

    def kandidat_detail(self, analysis_result_id: str) -> None:
        return None


@pytest.fixture(autouse=True)
def _db_freie_view_overrides():
    app.dependency_overrides[get_position_repository] = _LeeresFakePositionRepository
    app.dependency_overrides[get_kandidaten_repository] = _LeereKandidatenRepository
    app.dependency_overrides[get_anlageklassen_reader] = lambda: lambda: []
    app.dependency_overrides[get_depotstrategie_reader] = lambda: lambda: None
    yield
    app.dependency_overrides.clear()


_VIEW_PATHS: tuple[tuple[str, str], ...] = (
    ("/ui/depot", "nav-link-depot"),
    ("/ui/kandidaten", "nav-link-kandidaten"),
    ("/ui/trades", "nav-link-trades"),
    ("/ui/system-status", "nav-link-system-status"),
    ("/ui/konfiguration", "nav-link-konfiguration"),
)

_STATUS_TESTIDS: tuple[str, ...] = (
    "ampel",
    "killswitch",
    "modus-badge",
    "heartbeat",
    "drawdown",
    "halluzination-kpi",
)


class _LeeresDepotRepository:
    """Minimaler Fake (Story S-071): `/ui/depot` liest seit dieser Story
    real über `hole_depot_uebersicht` (AC1) statt eines DB-freien
    Platzhalters — die generischen Shell-Tests dieser Datei (parametrisiert
    über alle fünf Views) überschreiben die DI deshalb hier mit einem
    leeren Depot, analog `tests/api/test_depot_route.py`."""

    def alle_offenen_positionen(self, *, mode):
        return []

    def realisierter_gv_gesamt(self, *, mode):
        return Decimal("0")


class _KeinLivePriceProvider:
    def aktueller_preis(self, titel_id):
        return None


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_depot_position_repository] = lambda: _LeeresDepotRepository()
    app.dependency_overrides[get_live_price_provider] = lambda: _KeinLivePriceProvider()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_view_antwortet_200(client: TestClient, path: str, _active_testid: str) -> None:
    response = client.get(path)
    assert response.status_code == 200


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_genau_eine_header_nav_main_landmark_je_seite(
    client: TestClient, path: str, _active_testid: str
) -> None:
    """AC13: "Landmarks: genau eine <header>/<nav>/<main> je Seite"."""
    html = client.get(path).text
    assert html.count("<header") == 1
    assert html.count("<nav") == 1
    assert html.count("<main") == 1


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_genau_ein_h1_je_view(client: TestClient, path: str, _active_testid: str) -> None:
    """AC13: "ein <h1> je View" (WCAG 2.4.1)."""
    html = client.get(path).text
    assert html.count("<h1>") == 1


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_skip_link_zeigt_auf_main(client: TestClient, path: str, _active_testid: str) -> None:
    """AC11: Skip-Link zu <main> (WCAG 2.4.1)."""
    html = client.get(path).text
    assert 'class="skip-link" href="#main"' in html
    assert 'id="main"' in html


@pytest.mark.parametrize("path,active_testid", _VIEW_PATHS)
def test_aktiver_nav_eintrag_traegt_aria_current(
    client: TestClient, path: str, active_testid: str
) -> None:
    """AC11: Nav-Eintrag der aktuellen View trägt `aria-current="page"`;
    genau einer je Seite (nicht mehrere aktiv)."""
    html = client.get(path).text
    assert html.count('aria-current="page"') == 1
    aktiver_block_start = html.index(f'data-testid="{active_testid}"')
    umgebung = html[max(0, aktiver_block_start - 200) : aktiver_block_start]
    assert 'aria-current="page"' in umgebung


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_nav_listet_alle_fuenf_kern_views(
    client: TestClient, path: str, _active_testid: str
) -> None:
    """AC11: Nav mit den fünf Kern-Views, auf jeder Seite identisch
    (WCAG 3.2.3 Consistent Navigation)."""
    html = client.get(path).text
    for _view_path, testid in _VIEW_PATHS:
        assert f'data-testid="{testid}"' in html


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_statusleiste_zeigt_alle_sechs_indikatoren_auf_jeder_view(
    client: TestClient, path: str, _active_testid: str
) -> None:
    """AC13: Ampel/Kill-Switch/Modus/Heartbeat/Drawdown/Halluzinations-KPI
    ohne Scrollen sichtbar — auf jeder View identisch (Statusleiste ist Teil
    der Shell, D2)."""
    html = client.get(path).text
    for testid in _STATUS_TESTIDS:
        assert f'data-testid="{testid}"' in html


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_jeder_statuswert_traegt_text_und_icon_nicht_nur_farbe(
    client: TestClient, path: str, _active_testid: str
) -> None:
    """AC13/D3: jeder Status trägt zusätzlich Text/Kürzel + Icon/Glyph."""
    html = client.get(path).text
    for testid in _STATUS_TESTIDS:
        start = html.index(f'data-testid="{testid}"')
        block = html[start : start + 400]
        block_ende = block.index("</div>")
        block = block[:block_ende]
        assert 'class="status-icon"' in block
        assert 'class="status-value"' in block
        # Text-Inhalt des Werts ist nicht leer (kein reines Farbsignal).
        wert_start = block.index("data-value>") + len("data-value>")
        wert_ende = block.index("</span>", wert_start)
        assert block[wert_start:wert_ende].strip() != ""


def test_statusleiste_ist_sticky_ueber_css(client: TestClient) -> None:
    """AC13: Statusleiste bleibt beim Scrollen sichtbar (`position: sticky`
    in `shell.css`, nicht Teil des HTML selbst — hier gegen die
    ausgelieferte CSS-Datei geprüft)."""
    css = client.get("/static/css/shell.css").text
    assert ".statusleiste" in css
    assert "position: sticky" in css


@pytest.mark.parametrize("path,_active_testid", _VIEW_PATHS)
def test_modus_zeigt_simuliert_als_text_nicht_nur_icon(
    client: TestClient, path: str, _active_testid: str
) -> None:
    """MVP-Default: Modus ist immer SIMULIERT (BR-019) — als sichtbarer
    Text in der Statusleiste, nicht nur über das Schloss-Icon."""
    html = client.get(path).text
    start = html.index('data-testid="modus-badge"')
    block = html[start : start + 400]
    assert "SIMULIERT" in block
