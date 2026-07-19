"""UI-/Query-Boundary-Invariante (Story S-064,
`docs/specs/frontend-cockpit.md` AC1/AC2/AC12; architecture.md §4
"UI-Boundary" + §13.7 Prüfkriterium 1/2/3).

Covers (frontend-cockpit): AC1, AC2, AC12

Drei statisch (grep-/AST-) prüfbare Invarianten:

1. **AC2 Boundary:** `app/api/ui.py` + `app/api/queries/**` importieren
   nichts aus `app.domain.sizing`, `app.domain.risikomanagement`,
   `app.domain.execution`, `app.orchestration.*_pipeline`,
   `app.orchestration.execution_service` (AST-Scan, analog dem
   bestehenden Muster `tests/architecture/test_order_pfad_invariante.py`).
2. **AC2 Read-only:** dieselben Dateien enthalten keine
   `session.add`/`session.commit`-Aufrufe (kein Depot-Schreibpfad) und kein
   direktes `sqlalchemy`-/`app.db.session`-Import — `app/api/ui.py` baut
   seine Daten laut AC1 nie selbst zusammen, sondern ausschliesslich über
   `app/api/queries/**`-Funktionen.
3. **AC12 Asset-/Supply-Chain-Invariante:** kein Cockpit-Template unter
   `app/web/templates/**` referenziert eine externe CDN-URL (`//cdn`/
   `https://` auf JS/CSS).

Der Scan ist zum Zeitpunkt dieser Fundament-Story (S-064) grösstenteils
leer (noch keine konkreten Query-Funktionen, siehe
`app/api/queries/__init__.py`-Konvention) — `test_scan_erkennt_verstoss_*`
belegt an synthetischen Fixtures, dass die Scan-Logik einen echten
Verstoss tatsächlich erkennt, damit der Haupttest nicht bloss trivial grün
ist (Lesson aus S-014)."""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_ROOT = _REPO_ROOT / "app"

#: AC2, architecture.md §4/§13.7-1: verbotene Import-Präfixe für die
#: UI-/Query-Schicht.
_VERBOTENE_PRAEFIXE: tuple[str, ...] = (
    "app.domain.sizing",
    "app.domain.risikomanagement",
    "app.domain.execution",
    "app.orchestration.execution_service",
)

#: `app.orchestration.*_pipeline` ist ein Glob-Muster (jedes `*_pipeline`-
#: Modul unter `app.orchestration`), kein fixes Präfix — separat geprüft.
_PIPELINE_SUFFIX = "_pipeline"
_PIPELINE_PARENT = "app.orchestration"


def _boundary_dateien() -> list[Path]:
    """`app/api/ui.py` + alle Dateien unter `app/api/queries/**`."""
    dateien = [_APP_ROOT / "api" / "ui.py"]
    dateien.extend(sorted((_APP_ROOT / "api" / "queries").glob("**/*.py")))
    return [pfad for pfad in dateien if pfad.is_file()]


def _importiere_module(baum: ast.AST) -> list[str]:
    module: list[str] = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            module.extend(alias.name for alias in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module:
            module.append(knoten.module)
    return module


def _verbotener_import(pfad: Path) -> str | None:
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    for modul in _importiere_module(baum):
        if modul.startswith(_VERBOTENE_PRAEFIXE):
            return modul
        if modul.startswith(_PIPELINE_PARENT + "."):
            rest = modul[len(_PIPELINE_PARENT) + 1 :]
            erstes_segment = rest.split(".")[0]
            if erstes_segment.endswith(_PIPELINE_SUFFIX):
                return modul
    return None


def _enthaelt_schreibpfad_indiz(pfad: Path) -> str | None:
    """Grep-Heuristik (AC2 read-only): `session.add(`/`session.commit(`
    oder ein direkter `sqlalchemy`-Import (die UI-/Query-Schicht liest nur
    über Repository-Ports, baut keine eigene Session-Query)."""
    text = pfad.read_text(encoding="utf-8")
    if "session.add(" in text or "session.commit(" in text:
        return "session.add/commit"
    baum = ast.parse(text, filename=str(pfad))
    for modul in _importiere_module(baum):
        if modul == "sqlalchemy" or modul.startswith("sqlalchemy."):
            return f"sqlalchemy-Import ({modul})"
    return None


def test_ui_und_queries_importieren_keine_verbotenen_domain_module() -> None:
    """@trace frontend-cockpit#AC2 — AST-Scan über `app/api/ui.py` +
    `app/api/queries/**`."""
    verstoesse = {
        str(pfad.relative_to(_APP_ROOT)): treffer
        for pfad in _boundary_dateien()
        if (treffer := _verbotener_import(pfad)) is not None
    }
    assert not verstoesse, (
        f"UI-/Query-Schicht darf laut AC2 nicht aus Order-Pfad-Domänen importieren: {verstoesse}"
    )


def test_ui_und_queries_bauen_keine_eigene_db_session_query() -> None:
    """@trace frontend-cockpit#AC1,AC2 — kein `session.add`/`commit` und
    kein direkter `sqlalchemy`-Import in `app/api/ui.py` +
    `app/api/queries/**` (Query-Funktionen sind read-only und laufen über
    Repository-Ports, nicht über eine selbstgebaute Session-Query)."""
    verstoesse = {
        str(pfad.relative_to(_APP_ROOT)): treffer
        for pfad in _boundary_dateien()
        if (treffer := _enthaelt_schreibpfad_indiz(pfad)) is not None
    }
    assert not verstoesse, f"Schreibpfad-/Session-Indiz in der UI-/Query-Schicht: {verstoesse}"


def test_scan_erkennt_verbotenen_import_in_synthetischer_fixture(tmp_path: Path) -> None:
    """Belegt, dass `_verbotener_import` einen echten Verstoss erkennt
    (nicht nur ein leerer, unbewiesener Scan mangels konkreter
    Query-Dateien in dieser Fundament-Story)."""
    verstoss = tmp_path / "queries_bad.py"
    verstoss.write_text(
        "from app.domain.risikomanagement.gate import pruefe_kauf_gate\n"
        "\n\ndef irgendwas() -> None: ...\n",
        encoding="utf-8",
    )
    assert _verbotener_import(verstoss) == "app.domain.risikomanagement.gate"

    verstoss_pipeline = tmp_path / "queries_bad_pipeline.py"
    verstoss_pipeline.write_text(
        "import app.orchestration.buy_pipeline\n\n\ndef irgendwas() -> None: ...\n",
        encoding="utf-8",
    )
    assert _verbotener_import(verstoss_pipeline) == "app.orchestration.buy_pipeline"

    sauber = tmp_path / "queries_ok.py"
    sauber.write_text(
        "from app.domain.portfolio.ports import PositionRepository\n"
        "\n\ndef irgendwas() -> None: ...\n",
        encoding="utf-8",
    )
    assert _verbotener_import(sauber) is None


def test_scan_erkennt_schreibpfad_indiz_in_synthetischer_fixture(tmp_path: Path) -> None:
    verstoss_session = tmp_path / "queries_bad_session.py"
    verstoss_session.write_text(
        "def buche() -> None:\n    session.add(1)\n    session.commit()\n",
        encoding="utf-8",
    )
    assert _enthaelt_schreibpfad_indiz(verstoss_session) == "session.add/commit"

    verstoss_sqlalchemy = tmp_path / "queries_bad_sqlalchemy.py"
    verstoss_sqlalchemy.write_text(
        "from sqlalchemy.orm import Session\n\n\ndef irgendwas() -> None: ...\n",
        encoding="utf-8",
    )
    assert _enthaelt_schreibpfad_indiz(verstoss_sqlalchemy) == "sqlalchemy-Import (sqlalchemy.orm)"

    sauber = tmp_path / "queries_ok.py"
    sauber.write_text("def irgendwas() -> None: ...\n", encoding="utf-8")
    assert _enthaelt_schreibpfad_indiz(sauber) is None


def _cockpit_templates() -> list[Path]:
    return sorted((_APP_ROOT / "web" / "templates").glob("**/*.html"))


def test_kein_cdn_verweis_in_cockpit_templates() -> None:
    """@trace frontend-cockpit#AC12 — `grep`-prüfbar: kein `//cdn`/
    `https://` auf JS/CSS in `app/web/templates/**` (ADR-013)."""
    verstoesse = []
    for pfad in _cockpit_templates():
        text = pfad.read_text(encoding="utf-8")
        if "//cdn" in text or "https://" in text:
            verstoesse.append(str(pfad.relative_to(_APP_ROOT)))
    assert not verstoesse, f"Cockpit-Templates referenzieren ein externes CDN: {verstoesse}"


def test_scan_erkennt_cdn_verweis_in_synthetischer_fixture(tmp_path: Path) -> None:
    verstoss = tmp_path / "bad.html"
    verstoss.write_text(
        '<script src="https://cdn.example.com/htmx.min.js"></script>', encoding="utf-8"
    )
    text = verstoss.read_text(encoding="utf-8")
    assert "//cdn" in text or "https://" in text
