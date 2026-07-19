"""Tests für die Konfigurations-View (`app.api.ui.konfiguration_view`,
Story S-076, `docs/specs/frontend-cockpit.md` AC18).

Covers (frontend-cockpit): AC18

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für `GET /ui/konfiguration`
ab (Status-Code + gerenderte HTML-Struktur), gegen dieselben Query-
Funktionen (`lade_anlageklassen_konfiguration`/
`lade_depotstrategie_konfiguration`) wie `tests/api/test_config_route.py`
(AC1/AC10, kein zweiter Datenzusammenbau) — hier über Fake-Lese-Callables
via `app.dependency_overrides`, analog `tests/web/test_ui_depot.py`.

Deckt: Anlageklassen-Toggle-Liste (§7.9-Anatomie: Klassen-Chip, Name,
Prio, natives `<input type="checkbox" role="switch">` mit `<label>` +
44px-Trefferfläche-CSS-Regel, Text "aktiv"/"inaktiv" zusätzlich zur
Schalterstellung, `data-testid`/`data-active`/`data-has-open-positions`-
Anker), BR-018-Warn-Band (nur bei `hat_offene_positionen=True` UND
`aktiv=False` sichtbar, `aria-describedby`-Verdrahtung), Depotstrategie-
Anzeige (Preset-Grenzwerte + Klassen-Limits) + Empty-State ohne aktives
Preset (E2-Muster), sowie die Toggle-POST-Verdrahtung (`data-toggle-url`,
`app/web/static/js/konfiguration.js` eingebunden, `onchange`-Handler)."""

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


def _depotstrategie(**overrides: object) -> DepotstrategieKonfiguration:
    kwargs = {
        "portfolio_strategy_id": uuid.uuid4(),
        "risk_profile_name": "ausgewogen",
        "max_einzelposition_pct": Decimal("5"),
        "max_sektor_pct": Decimal("20"),
        "cash_quote_ziel_pct": Decimal("5"),
        "gesamt_exposure_cap_pct": Decimal("25"),
        "max_anlageklasse_pct": {7: Decimal("10")},
    }
    kwargs.update(overrides)
    return DepotstrategieKonfiguration(**kwargs)


def test_leere_anlageklassenliste_zeigt_definierten_empty_state() -> None:
    client = _client(anlageklassen=[])

    resp = client.get("/ui/konfiguration")

    assert resp.status_code == 200
    assert 'data-testid="anlageklassen-empty"' in resp.text
    assert 'data-testid="anlageklassen-liste"' not in resp.text


def test_aktive_klasse_ohne_offene_positionen_zeigt_kein_warnband() -> None:
    anlageklassen = [AnlageklasseEintrag(id=1, name="Aktien", aktiv=True, prio_stufe="MVP")]
    client = _client(anlageklassen=anlageklassen)

    resp = client.get("/ui/konfiguration")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="toggle-zeile-1"' in html
    assert 'data-testid="toggle-ac-1"' in html
    assert 'data-active="true"' in html
    assert 'data-has-open-positions="false"' in html
    assert "checked" in html
    assert ">aktiv<" in html
    assert 'data-testid="warnband-ac-1"' not in html


def test_inaktive_klasse_mit_offenen_positionen_zeigt_br018_warnband_sichtbar() -> None:
    """@trace frontend-cockpit#AC18,BR-018 — deckt A3: eine deaktivierte
    Klasse mit offenen Positionen trägt das Warn-Band sichtbar (kein
    `hidden`-Attribut) + `aria-describedby`-Verdrahtung auf dem Switch."""
    anlageklassen = [
        AnlageklasseEintrag(
            id=7, name="Kryptowährungen", aktiv=False, prio_stufe="MVP", hat_offene_positionen=True
        )
    ]
    client = _client(anlageklassen=anlageklassen)

    resp = client.get("/ui/konfiguration")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="warnband-ac-7"' in html
    assert "inaktiv – Positionen bleiben überwacht" in html
    assert 'aria-describedby="warnband-ac-7"' in html
    assert 'data-has-open-positions="true"' in html
    assert 'data-active="false"' in html
    # Warn-Band-Absatz selbst trägt bei aktiver Klasse "hidden" — hier
    # (inaktiv) darf das Attribut auf DIESEM Element nicht gesetzt sein.
    warnband_start = html.index('data-testid="warnband-ac-7"')
    warnband_tag = html[max(0, warnband_start - 200) : warnband_start + 40]
    assert "hidden" not in warnband_tag


def test_aktive_klasse_mit_offenen_positionen_rendert_warnband_aber_verborgen() -> None:
    """Die Klasse ist (noch) aktiv, hat aber offene Positionen — das
    Warn-Band-Element existiert bereits im DOM (für den späteren
    Client-seitigen Toggle-Fall), ist aber initial `hidden` (nicht
    Bestandteil des sichtbaren A3-Zustands, solange die Klasse aktiv
    ist)."""
    anlageklassen = [
        AnlageklasseEintrag(
            id=7, name="Kryptowährungen", aktiv=True, prio_stufe="MVP", hat_offene_positionen=True
        )
    ]
    client = _client(anlageklassen=anlageklassen)

    html = client.get("/ui/konfiguration").text

    warnband_start = html.index('data-testid="warnband-ac-7"')
    warnband_tag = html[max(0, warnband_start - 200) : warnband_start + 60]
    assert "hidden" in warnband_tag


def test_toggle_switch_traegt_stabile_data_testid_und_toggle_url() -> None:
    anlageklassen = [AnlageklasseEintrag(id=3, name="Cash/Geldmarkt", aktiv=True, prio_stufe="MVP")]
    client = _client(anlageklassen=anlageklassen)

    html = client.get("/ui/konfiguration").text

    assert 'data-testid="toggle-ac-3"' in html
    assert 'data-toggle-url="/api/control/anlageklassen/3/toggle"' in html
    assert 'role="switch"' in html
    assert 'onchange="konfigurationToggleAnlageklasse(this)"' in html
    assert 'for="toggle-ac-3"' in html  # <label> assoziiert (A11y)


def test_toggle_fehler_element_ist_initial_verborgen() -> None:
    anlageklassen = [AnlageklasseEintrag(id=1, name="Aktien", aktiv=True, prio_stufe="MVP")]
    client = _client(anlageklassen=anlageklassen)

    html = client.get("/ui/konfiguration").text

    fehler_start = html.index('data-testid="toggle-fehler-1"')
    fehler_tag = html[max(0, fehler_start - 80) : fehler_start + 60]
    assert 'role="alert"' in fehler_tag
    assert "hidden" in fehler_tag


def test_konfiguration_js_und_css_werden_eingebunden() -> None:
    client = _client(anlageklassen=[])

    html = client.get("/ui/konfiguration").text

    assert "js/konfiguration.js" in html
    assert "css/views-konfiguration.css" in html


def test_44px_trefferflaeche_regel_in_der_view_css() -> None:
    """A11y (`design.md` §7.9: "Schalter >= 44px Trefferfläche") —
    verifiziert über die tatsächlich ausgelieferte CSS-Regel, analog dem
    bestehenden `test_reduced_motion_deaktiviert_animationen_global`-Muster
    (`tests/web/test_ui_depot.py`)."""
    client = _client(anlageklassen=[])

    css = client.get("/static/css/views-konfiguration.css").text

    assert "width: 44px" in css
    assert "height: 44px" in css


def test_depotstrategie_leer_zeigt_definierten_empty_state() -> None:
    client = _client(depotstrategie=None)

    resp = client.get("/ui/konfiguration")

    assert resp.status_code == 200
    assert 'data-testid="depotstrategie-empty"' in resp.text
    assert 'data-testid="depotstrategie"' not in resp.text


def test_depotstrategie_zeigt_grenzwerte_und_preset() -> None:
    client = _client(depotstrategie=_depotstrategie())

    resp = client.get("/ui/konfiguration")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="depotstrategie"' in html
    assert "ausgewogen" in html
    assert 'data-testid="depotstrategie-max-einzelposition"' in html
    assert "5.0%" in html
    assert 'data-testid="depotstrategie-max-sektor"' in html
    assert "20.0%" in html


def test_depotstrategie_zeigt_klassen_limits() -> None:
    client = _client(depotstrategie=_depotstrategie(max_anlageklasse_pct={7: Decimal("10")}))

    html = client.get("/ui/konfiguration").text

    assert 'data-testid="depotstrategie-klassen-limit-7"' in html
    assert "CRY: 10.0%" in html
