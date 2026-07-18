"""Architektur-Invariante: das Risikomanagement-Gate greift nur beim Kauf
(Story S-044).

Covers (risikomanagement): AC5

Spec `docs/specs/risikomanagement.md` AC5: "Das Risikomanagement-Gate
greift nur beim Kauf; jeder Verkaufsauftrag umgeht das Gate vollständig
und ungeprüft (harte Regel, deckt A3)." Spiegelbildlich zum bestehenden
Guard `tests/architecture/test_exit_sizing_umgeht_risikomanagement.py`
(der beweist, dass der Verkaufs-Pfad kein Risikomanagement importiert):
dieser Test scannt statisch (AST, kein Codeausführen), dass
`app/domain/sizing/**/*.py` (Exit-Sizing/Verkaufs-Pfad) auch keinen Import
aus dem Risikomanagement-Gate-Modul selbst enthält
(`app.domain.risikomanagement`, S-044) — die strukturelle Absicherung,
dass ein Verkaufsauftrag das Gate nie durchläuft, nicht nur eine
Dokumentations-Behauptung im Moduldocstring.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_ROOT = _REPO_ROOT / "app"

#: AC5: Import-Präfix des Risikomanagement-Gate-Moduls (S-044,
#: `app.domain.risikomanagement.gate.pruefe_kauf_gate`) — Exit-Sizing darf
#: es nicht importieren (Verkauf umgeht das Gate vollständig).
_VERBOTENE_PRAEFIXE: tuple[str, ...] = ("app.domain.risikomanagement",)


def _importiert_gate(pfad: Path) -> str | None:
    """Parst `pfad` per AST und liefert den ersten gefundenen Import aus
    einem der `_VERBOTENE_PRAEFIXE` (voll qualifiziert) oder `None`."""
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for alias in knoten.names:
                if alias.name.startswith(_VERBOTENE_PRAEFIXE):
                    return alias.name
        elif isinstance(knoten, ast.ImportFrom):
            modul = knoten.module or ""
            if modul.startswith(_VERBOTENE_PRAEFIXE):
                return modul
    return None


def test_sizing_module_importieren_kein_risikomanagement_gate() -> None:
    """@trace risikomanagement#AC5 — scannt alle Module unter
    `app/domain/sizing/` (Verkaufs-Pfad, `exit_sizing.py`) auf einen Import
    aus `app.domain.risikomanagement` (dem Gate-Modul dieser Story)."""
    verstoesse = {
        str(pfad.relative_to(_APP_ROOT)): treffer
        for pfad in (_APP_ROOT / "domain" / "sizing").glob("**/*.py")
        if (treffer := _importiert_gate(pfad)) is not None
    }
    assert not verstoesse, (
        f"Exit-Sizing darf laut AC5 nie das Risikomanagement-Gate importieren, "
        f"gefunden in: {verstoesse}"
    )


def test_scan_erkennt_gate_import_in_sizing_datei(tmp_path: Path) -> None:
    """@trace risikomanagement#AC5 — Fixture-Beleg: `_importiert_gate`
    erkennt einen tatsächlichen Verstoss (Import aus dem Gate-Modul in
    einer synthetischen Datei) korrekt und lässt eine unauffällige Datei
    unbeanstandet."""
    verstoss_datei = tmp_path / "exit_sizing_bad.py"
    verstoss_datei.write_text(
        "from app.domain.risikomanagement.gate import pruefe_kauf_gate\n"
        "\n\n"
        "def bestimme_exit_order() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_gate(verstoss_datei) == "app.domain.risikomanagement.gate"

    verstoss_datei_plain_import = tmp_path / "exit_sizing_bad_plain.py"
    verstoss_datei_plain_import.write_text(
        "import app.domain.risikomanagement\n\n\ndef bestimme_exit_order() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_gate(verstoss_datei_plain_import) == "app.domain.risikomanagement"

    saubere_datei = tmp_path / "exit_sizing.py"
    saubere_datei.write_text(
        "from app.contracts.sizing import Verkaufsauftrag\n\n\n"
        "def bestimme_exit_order() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_gate(saubere_datei) is None
