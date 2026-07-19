"""Tests für die Offene-Entscheide-HTML-View (`app.api.ui.entscheide_view`),
Story S-080, `docs/specs/frontend-cockpit.md` AC29/AC30/AC31.

Covers (frontend-cockpit): AC29, AC30, AC31

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für `GET /ui/entscheide` ab
— Fake-`HybridEntscheidungRepository` via `app.dependency_overrides`
(fastapi/A09, identischer Fake wie `tests/api/test_entscheide.py`),
`Settings`-Override für das AC31-Feature-Gate, keine echte DB nötig.
Deckt: volle Shell (AC13), AC31-"autonom — keine offenen Entscheide"-
Zustand bei inaktivem Flag (inkl. FEHLENDER Bestätigen-/Ablehnen-Buttons —
"Control-POSTs sind inaktiv/gesperrt" gilt bereits auf Markup-Ebene),
AC29-Empty-State bei aktivem Flag ohne Einträge, AC30-Karten mit allen
Feldern + nativem `<dialog>`-Bestätigungs-Pattern (`command`/`commandfor`,
design.md §7.11) je Bestätigen/Ablehnen, HTMX-POST-Ziele der
Dialog-Bestätigen-Buttons."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.entscheide import get_hybrid_entscheidung_repository
from app.config import Settings, get_settings
from app.domain.hybrid_entscheidung.ports import OffenerEntscheidZeile
from app.main import app


def _zeile(**overrides: object) -> OffenerEntscheidZeile:
    basis: dict[str, object] = {
        "entscheid_id": "e-1",
        "titel_id": "titel-1",
        "titel": "ROG",
        "name": "Roche Holding AG",
        "richtung": "kauf",
        "groesse": Decimal("5"),
        "vorgeschlagene_order": "Market-Buy 5 Stk. Roche Holding AG",
        "frist": datetime(2026, 7, 20, 16, 0, tzinfo=UTC),
        "begruendung": "Gesamtscore 8.5 (KAUF-Schwelle).",
        "erstellt_am": datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    }
    basis.update(overrides)
    return OffenerEntscheidZeile(**basis)  # type: ignore[arg-type]


class _FakeHybridEntscheidungRepository:
    def __init__(self, eintraege: list[OffenerEntscheidZeile]):
        self._eintraege = eintraege

    def offene_entscheide(self) -> list[OffenerEntscheidZeile]:
        return self._eintraege


def _client(eintraege: list[OffenerEntscheidZeile], *, feature_aktiv: bool) -> TestClient:
    app.dependency_overrides[get_hybrid_entscheidung_repository] = lambda: (
        _FakeHybridEntscheidungRepository(eintraege)
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        hybrid_bestaetigung_aktiv=feature_aktiv
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_entscheide_view_antwortet_200_mit_voller_shell():
    """@trace frontend-cockpit#AC30 — `GET /ui/entscheide` liefert die
    volle Seite (Shell + View-Inhalt), Status 200."""
    client = _client([], feature_aktiv=True)

    resp = client.get("/ui/entscheide")

    assert resp.status_code == 200
    assert "<header" in resp.text
    assert "<nav" in resp.text
    assert "<main" in resp.text


def test_feature_inaktiv_zeigt_autonom_zustand_ohne_control_buttons():
    """@trace frontend-cockpit#AC31 — deaktivierter Flow zeigt den
    definierten "autonom — keine offenen Entscheide"-Zustand; die
    Control-POSTs sind bereits auf Markup-Ebene inaktiv/gesperrt (kein
    Bestätigen-/Ablehnen-Button, unabhängig davon, dass ein offener
    Entscheid im (Fake-)Repository existiert)."""
    client = _client([_zeile()], feature_aktiv=False)

    html = client.get("/ui/entscheide").text

    assert 'data-testid="entscheide-autonom"' in html
    assert "autonom" in html.lower()
    assert 'data-testid="entscheid-bestaetigen-oeffnen"' not in html
    assert 'data-testid="entscheid-ablehnen-oeffnen"' not in html


def test_feature_aktiv_ohne_eintraege_zeigt_definierten_empty_state():
    """@trace frontend-cockpit#AC29 — solange keine offenen Entscheide
    existieren, zeigt die View den definierten Empty-State (Modus
    SIMULIERT), keine leere Tabelle/Karte."""
    client = _client([], feature_aktiv=True)

    resp = client.get("/ui/entscheide")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="entscheide-empty"' in html
    assert "SIMULIERT" in html
    assert 'data-testid="entscheide-autonom"' not in html


def test_entscheid_karte_zeigt_alle_ac29_felder():
    """@trace frontend-cockpit#AC29,AC30 — Titel, Richtung, Grösse,
    vorgeschlagene Order, Frist, Begründung sind in der Karte sichtbar."""
    client = _client([_zeile()], feature_aktiv=True)

    html = client.get("/ui/entscheide").text

    assert 'data-testid="entscheid-karte"' in html
    assert 'data-entscheid-id="e-1"' in html
    assert "ROG" in html
    assert "Roche Holding AG" in html
    assert 'data-testid="entscheid-richtung"' in html
    assert 'data-richtung="kauf"' in html
    assert "Kauf" in html
    assert "5.0000" in html
    assert "Market-Buy 5 Stk. Roche Holding AG" in html
    assert "Gesamtscore 8.5 (KAUF-Schwelle)." in html


def test_entscheid_karte_faellt_auf_titel_id_zurueck_wenn_titel_fehlt():
    """@trace frontend-cockpit#AC29 — liefert die Quelle keinen
    aufgelösten Titel, zeigt die Karte die rohe `titel_id` als Fallback."""
    client = _client([_zeile(titel_id="titel-42", titel=None, name=None)], feature_aktiv=True)

    html = client.get("/ui/entscheide").text

    assert "titel-42" in html


def test_entscheid_karte_traegt_natives_dialog_bestaetigungs_pattern():
    """@trace frontend-cockpit#AC30 — Bestätigen/Ablehnen laufen über ein
    natives modales `<dialog>` (html/R08 `command`/`commandfor`,
    design.md §7.11), der eigentliche HTMX-POST liegt auf dem
    Bestätigen-Button IM Dialog (nicht auf dem öffnenden Button)."""
    client = _client([_zeile()], feature_aktiv=True)

    html = client.get("/ui/entscheide").text

    assert '<dialog id="dialog-bestaetigen-e-1"' in html
    assert '<dialog id="dialog-ablehnen-e-1"' in html
    assert 'command="show-modal"' in html
    assert 'commandfor="dialog-bestaetigen-e-1"' in html
    assert 'commandfor="dialog-ablehnen-e-1"' in html
    assert 'hx-post="/api/control/entscheide/e-1/bestaetigen"' in html
    assert 'hx-post="/api/control/entscheide/e-1/ablehnen"' in html
    assert 'hx-target="#entscheide-liste"' in html


def test_verkauf_richtung_zeigt_verkauf_badge():
    """@trace frontend-cockpit#AC29 — Richtung Kauf/Verkauf als Badge mit
    Wortlaut (D3, nie nur Farbe)."""
    client = _client([_zeile(richtung="verkauf")], feature_aktiv=True)

    html = client.get("/ui/entscheide").text

    assert 'data-richtung="verkauf"' in html
    assert "Verkauf" in html
