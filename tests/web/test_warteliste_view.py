"""Tests für die Warteliste-HTML-View (`app.api.ui.warteliste_view`),
Story S-079, `docs/specs/frontend-cockpit.md` AC27.

Covers (frontend-cockpit): AC27

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für `GET /ui/warteliste` ab
— Fake-`WartelisteRepository` via `app.dependency_overrides` (fastapi/A09,
identischer Fake wie `tests/api/test_warteliste.py`), keine echte DB
nötig. Deckt: dichte Datentabelle mit allen AC27-Spalten, Klassen-Chip,
Blockade-Grund-Badge (Text + `data-blockade-grund`-Anker, D3), definierter
Empty-State je Modus (§7.1)."""

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

    def liste_warteliste(self, *, mode):
        return self._eintraege


def _eintrag(
    *,
    id: str = "w-1",
    titel_id: str = "titel-1",
    titel: str = "CHSPI",
    name: str = "iShares Swiss Dividend ETF",
    asset_class_id: int = 2,
    geplante_groesse: Decimal = Decimal("5000"),
    blockade_grund: str = "klumpenrisiko",
    blockiert_am: datetime = datetime(2026, 6, 10, 8, 30, tzinfo=UTC),
) -> WartelisteEintrag:
    return WartelisteEintrag(
        id=id,
        titel_id=titel_id,
        titel=titel,
        name=name,
        asset_class_id=asset_class_id,
        geplante_groesse=geplante_groesse,
        blockade_grund=blockade_grund,
        blockiert_am=blockiert_am,
    )


def _client(repository) -> TestClient:
    app.dependency_overrides[get_warteliste_repository] = lambda: repository
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_warteliste_view_antwortet_200_mit_voller_shell() -> None:
    """@trace frontend-cockpit#AC27 — `GET /ui/warteliste` liefert die
    volle Seite (Shell + View-Inhalt), Status 200."""
    client = _client(_FakeWartelisteRepository([]))

    resp = client.get("/ui/warteliste")

    assert resp.status_code == 200
    assert "<header" in resp.text
    assert "<main" in resp.text


def test_warteliste_view_zeigt_alle_ac27_spalten() -> None:
    """@trace frontend-cockpit#AC27 — Titel, Klasse, geplante Grösse,
    Blockade-Grund, Zeitpunkt als Spaltenköpfe."""
    client = _client(_FakeWartelisteRepository([_eintrag()]))

    html = client.get("/ui/warteliste").text

    assert 'data-testid="table-warteliste"' in html
    for spalte in ("Titel", "Klasse", "Geplante Grösse", "Blockade-Grund", "Zeitpunkt"):
        assert spalte in html


def test_warteliste_zeile_zeigt_titel_klassen_chip_und_blockade_grund_badge() -> None:
    """@trace frontend-cockpit#AC27 — Titel + Klassen-Chip (§2.4),
    Blockade-Grund als Text/Badge mit stabilem `data-blockade-grund`-Anker
    (D3: Wortlaut führend, nicht nur Farbe)."""
    client = _client(
        _FakeWartelisteRepository(
            [_eintrag(titel="CHSPI", asset_class_id=2, blockade_grund="korrelation")]
        )
    )

    html = client.get("/ui/warteliste").text

    assert "CHSPI" in html
    assert 'data-testid="klassen-chip"' in html
    assert 'data-anlageklasse="etf"' in html
    assert 'data-testid="blockade-grund-badge"' in html
    assert 'data-blockade-grund="korrelation"' in html
    assert "Korrelation" in html


def test_leere_warteliste_zeigt_definierten_empty_state() -> None:
    """@trace frontend-cockpit#AC27 — definierter Empty-State
    "Keine blockierten Kandidaten im Modus SIMULIERT" (wörtlich)."""
    client = _client(_FakeWartelisteRepository([]))

    resp = client.get("/ui/warteliste", params={"mode": "simuliert"})

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="warteliste-empty"' in html
    assert "Keine blockierten Kandidaten im Modus SIMULIERT" in html
    assert 'data-testid="table-warteliste"' not in html


def test_mode_query_parameter_steuert_gerenderten_modus() -> None:
    """@trace frontend-cockpit#AC26,AC27 — dieselbe Query-Funktion/derselbe
    `mode`-Parameter wie `GET /api/warteliste`."""
    client = _client(_FakeWartelisteRepository([]))

    html = client.get("/ui/warteliste", params={"mode": "echt"}).text

    assert "Keine blockierten Kandidaten im Modus ECHT" in html
