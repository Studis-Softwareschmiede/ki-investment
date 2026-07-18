"""Tests für die Trade-Historie-HTML-View (`app.api.ui.trades_view` +
`app.api.ui.trades_tabelle_partial`), Story S-073,
`docs/specs/frontend-cockpit.md` AC16.

Covers (frontend-cockpit): AC16

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für `GET /ui/trades`
(volle View) **und** `GET /ui/trades/tabelle` (HTMX-Partial-Swap-Ziel) ab
— Fake-`PositionRepository` via `app.dependency_overrides` (fastapi/A09,
identischer Fake wie `tests/api/test_trades.py`), keine echte DB nötig.
Deckt: dichte Datentabelle mit allen AC16-Spalten, Richtungs-Badge,
Slippage/TCA-Vorzeichen-Kodierung (positiv/negativ/exakt Null, §2.3),
FX-Split (vorhanden/`None`), Filter-Formular inkl. Query-Parameter-
Durchreichung an dieselbe Query-Funktion wie die JSON-Route (AC1/AC7),
Empty-State (§7.1) und dass das Partial-Ziel kein volles Seiten-Layout
zurückliefert (reiner HTMX-Swap-Fragment)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.trades import get_position_repository
from app.domain.portfolio.ports import TransaktionsEintrag
from app.main import app


def _trade(
    *,
    trade_id: str = "t-1",
    titel_id: str = "titel-1",
    titel: str | None = "ACME",
    name: str | None = "Acme Corp",
    richtung: str = "kauf",
    slippage: Decimal = Decimal("1.5"),
    fx_rate: Decimal | None = Decimal("1.1"),
    kapital_gv_chf: Decimal | None = Decimal("2"),
    waehrungs_gv_chf: Decimal | None = Decimal("0.5"),
) -> TransaktionsEintrag:
    return TransaktionsEintrag(
        trade_id=trade_id,
        titel_id=titel_id,
        richtung=richtung,
        menge=Decimal("10"),
        fill_preis=Decimal("101.5"),
        arrival_price=Decimal("100"),
        slippage=slippage,
        kosten=Decimal("5"),
        waehrung="CHF",
        zeitstempel=datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        fx_rate=fx_rate,
        kapital_gv_chf=kapital_gv_chf,
        waehrungs_gv_chf=waehrungs_gv_chf,
        titel=titel,
        name=name,
    )


class _FakePositionRepository:
    """Test-Double des `PositionRepository`-Ports — identisches Muster wie
    `tests/api/test_trades.py::_FakePositionRepository` (nur die tatsächlich
    aufgerufene Methode implementiert)."""

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


def test_trades_view_antwortet_200_mit_voller_shell():
    """@trace frontend-cockpit#AC16 — `GET /ui/trades` liefert die volle
    Seite (Shell + View-Inhalt), Status 200."""
    client = _client(_FakePositionRepository([]))

    resp = client.get("/ui/trades")

    assert resp.status_code == 200
    assert "<header" in resp.text
    assert "<main" in resp.text


def test_trades_view_zeigt_alle_ac16_spalten():
    """@trace frontend-cockpit#AC16 — Titel, Richtung, Menge, Fill-Preis,
    Arrival-Price, Slippage/TCA, Kosten, FX-Split, Zeit als Spaltenköpfe."""
    client = _client(_FakePositionRepository([_trade()]))

    html = client.get("/ui/trades").text

    assert 'data-testid="table-trades"' in html
    for spalte in (
        "Titel",
        "Richtung",
        "Menge",
        "Fill-Preis",
        "Arrival-Price",
        "Slippage/TCA",
        "Kosten",
        "FX-Split",
        "Zeit",
    ):
        assert spalte in html


def test_trade_zeile_zeigt_aufgeloesten_titel_und_richtungs_badge():
    """@trace frontend-cockpit#AC16 — Review-Fix Iteration 2 (Critical):
    die "Titel"-Spalte zeigt den aufgelösten Titel (Symbol), NICHT die
    rohe `titel_id`-UUID; Richtung Kauf/Verkauf als Badge mit stabilem
    Test-Anker."""
    client = _client(
        _FakePositionRepository([_trade(titel_id="titel-42", titel="ACME", richtung="verkauf")])
    )

    html = client.get("/ui/trades").text

    assert "ACME" in html
    assert "titel-42" not in html
    assert 'data-testid="richtung-badge"' in html
    assert 'data-richtung="verkauf"' in html
    assert "Verkauf" in html


def test_trade_zeile_faellt_auf_titel_id_zurueck_wenn_titel_fehlt():
    """@trace frontend-cockpit#AC16 — liefert die Quelle (Fake-Repository)
    keinen aufgelösten Titel (`titel=None`), zeigt die Zeile die rohe
    `titel_id` als Fallback statt eines leeren Felds."""
    client = _client(_FakePositionRepository([_trade(titel_id="titel-42", titel=None, name=None)]))

    html = client.get("/ui/trades").text

    assert "titel-42" in html


@pytest.mark.parametrize(
    "slippage,erwartetes_vorzeichen,erwarteter_glyph,erwartete_farbklasse",
    [
        (Decimal("1.5"), "+", "▲", "num-gain"),
        (Decimal("-1.5"), "−", "▼", "num-loss"),
        (Decimal("0"), "±0", "▬", "num-neutral"),
    ],
)
def test_slippage_vorzeichen_kodierung(
    slippage: Decimal, erwartetes_vorzeichen: str, erwarteter_glyph: str, erwartete_farbklasse: str
):
    """@trace frontend-cockpit#AC16 — Slippage/TCA-Dreifach-Kodierung
    (design.md §2.3): Vorzeichen (auch bei 0 → ±0) + Richtungs-Glyph +
    Farbklasse, nie nur Farbe."""
    client = _client(_FakePositionRepository([_trade(slippage=slippage)]))

    html = client.get("/ui/trades").text
    testid_start = html.index('data-testid="slippage"')
    block = html[max(0, testid_start - 100) : testid_start + 300]

    assert erwartetes_vorzeichen in block
    assert erwarteter_glyph in block
    assert erwartete_farbklasse in block


def test_fx_split_zeigt_kurs_und_gv_anteile_wenn_vorhanden():
    """@trace frontend-cockpit#AC16 — FX-Split-Spalte zeigt FX-Kurs +
    Kapital-/Währungs-G/V-Anteil, wenn vorhanden."""
    client = _client(
        _FakePositionRepository(
            [
                _trade(
                    fx_rate=Decimal("1.234"),
                    kapital_gv_chf=Decimal("3.5"),
                    waehrungs_gv_chf=Decimal("-0.25"),
                )
            ]
        )
    )

    html = client.get("/ui/trades").text

    assert 'data-testid="fx-split"' in html
    assert "1.2340" in html
    assert "3.50" in html


def test_fx_split_zeigt_leerwert_wenn_none():
    """@trace frontend-cockpit#AC16 — kein FX-Split (CHF oder Kauf) → `—`,
    kein Farbzustand/Nullwert (E2-Muster)."""
    client = _client(
        _FakePositionRepository([_trade(fx_rate=None, kapital_gv_chf=None, waehrungs_gv_chf=None)])
    )

    html = client.get("/ui/trades").text

    assert 'data-testid="fx-split"' not in html
    assert "text-3" in html


def test_leere_historie_zeigt_definierten_empty_state():
    """@trace frontend-cockpit#AC16 — leere Trade-Liste zeigt den
    definierten Empty-State je Modus statt einer leeren Tabelle (§7.1)."""
    client = _client(_FakePositionRepository([]))

    resp = client.get("/ui/trades", params={"mode": "simuliert"})

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="trades-empty"' in html
    assert "SIMULIERT" in html
    assert 'data-testid="table-trades"' not in html


def test_filter_form_zeigt_stabile_test_anker_und_aktuelle_werte():
    """@trace frontend-cockpit#AC16 — Filter-Formular (Modus/Titel/
    Zeitraum) mit stabilen `data-testid`-Ankern, vorbelegt mit den
    aktuellen Query-Parametern."""
    client = _client(_FakePositionRepository([]))

    html = client.get("/ui/trades", params={"mode": "simuliert", "titel": "titel-9"}).text

    assert 'data-testid="trades-filter-form"' in html
    assert 'data-testid="filter-mode"' in html
    assert 'data-testid="filter-titel"' in html
    assert 'data-testid="filter-von"' in html
    assert 'data-testid="filter-bis"' in html
    assert 'data-testid="filter-submit"' in html
    assert 'value="titel-9"' in html
    assert 'value="simuliert" selected' in html


def test_filter_query_parameter_werden_an_die_query_funktion_durchgereicht():
    """@trace frontend-cockpit#AC16,AC1,AC7 — dieselben Filter-Parameter
    (`mode`/`titel`/`von`/`bis`) wie `GET /api/trades` landen unverändert
    beim `PositionRepository` (geteilte Query-Funktion, kein eigener
    Datenzusammenbau)."""
    repository = _FakePositionRepository([])
    client = _client(repository)

    client.get(
        "/ui/trades",
        params={
            "mode": "simuliert",
            "titel": "titel-42",
            "von": "2026-07-01T00:00:00Z",
            "bis": "2026-07-31T23:59:59Z",
        },
    )

    aufruf = repository.aufrufe[0]
    assert aufruf["mode"] == "simuliert"
    assert aufruf["titel_id"] == "titel-42"
    assert aufruf["von"] == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    assert aufruf["bis"] == datetime(2026, 7, 31, 23, 59, 59, tzinfo=UTC)


def test_tabelle_partial_liefert_kein_volles_seiten_layout():
    """@trace frontend-cockpit#AC16 — `GET /ui/trades/tabelle` (HTMX-Swap-
    Ziel) rendert ausschliesslich das Tabellen-Fragment, kein `<header>`/
    `<nav>`/vollständiges Dokument."""
    client = _client(_FakePositionRepository([_trade()]))

    resp = client.get("/ui/trades/tabelle")

    assert resp.status_code == 200
    assert "<header" not in resp.text
    assert "<nav" not in resp.text
    assert 'id="trades-tabelle-container"' in resp.text
    assert 'data-testid="table-trades"' in resp.text


def test_tabelle_partial_reicht_filter_an_dieselbe_query_funktion_durch():
    """@trace frontend-cockpit#AC16,AC1 — das Partial-Swap-Ziel nutzt
    dieselbe Query-Funktion/dieselben Filter wie die volle View."""
    repository = _FakePositionRepository([])
    client = _client(repository)

    client.get("/ui/trades/tabelle", params={"mode": "simuliert", "titel": "titel-7"})

    aufruf = repository.aufrufe[0]
    assert aufruf["mode"] == "simuliert"
    assert aufruf["titel_id"] == "titel-7"
