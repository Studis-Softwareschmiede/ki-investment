"""Tests für das StaticFiles-Mount + die vendorten Cockpit-Assets
(`app/web/templates_setup.py`, `app/web/static/**`, Story S-064).

Covers (frontend-cockpit): AC11, AC12

Prüft die Asset-/Supply-Chain-Invariante (AC12, architecture.md §13.7-3):
`htmx.min.js` + `tokens.css` sind über `/static/**` ausgeliefert (StaticFiles-
Mount, AC11) und liegen physisch unter `app/web/static/**` (im Runtime-
Image, da der Dockerfile nur `/app/app` kopiert) — kein CDN-Download zur
Laufzeit."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.web.templates_setup import STATIC_DIR, TEMPLATES_DIR

_REPO_APP_ROOT = Path(__file__).resolve().parents[2] / "app"


def test_static_und_templates_liegen_unter_app_web() -> None:
    """AC12/ADR-013: Templates/Statics unter `app/web/**`, damit der
    Dockerfile (`COPY --from=build /app/app /app/app`) sie mitkopiert."""
    assert STATIC_DIR == _REPO_APP_ROOT / "web" / "static"
    assert TEMPLATES_DIR == _REPO_APP_ROOT / "web" / "templates"
    assert STATIC_DIR.is_dir()
    assert TEMPLATES_DIR.is_dir()


def test_htmx_ist_vendored_und_ueber_static_ausgeliefert() -> None:
    """AC11/AC12: `htmx.min.js` liegt vendored (keine leere/Platzhalter-
    Datei) und ist über `/static/vendor/htmx.min.js` erreichbar."""
    client = TestClient(app)
    response = client.get("/static/vendor/htmx.min.js")
    assert response.status_code == 200
    assert len(response.content) > 10_000
    assert b"htmx" in response.content.lower()


def test_tokens_css_ueber_static_ausgeliefert() -> None:
    """AC11: `Jinja2Templates`/`StaticFiles` sind korrekt verdrahtet —
    `tokens.css` (design.md §11 Token-/Datei-Konvention) ist erreichbar."""
    client = TestClient(app)
    response = client.get("/static/css/tokens.css")
    assert response.status_code == 200
    assert "color-scheme: light dark" in response.text


def test_kein_cdn_verweis_in_vendorten_dateien() -> None:
    """AC12: die vendorten Assets selbst referenzieren keine externe
    CDN-URL (ergänzt den Template-Scan in
    `tests/architecture/test_ui_boundary.py`)."""
    htmx_js = (STATIC_DIR / "vendor" / "htmx.min.js").read_text(encoding="utf-8")
    assert "//cdn" not in htmx_js
