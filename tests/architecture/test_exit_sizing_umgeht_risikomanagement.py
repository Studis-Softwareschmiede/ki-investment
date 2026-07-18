"""Architektur-Invariante: Exit-Sizing umgeht bewusst das Risikomanagement
(Story S-042).

Covers (sizing): AC12

Spec `docs/specs/sizing.md` AC12: "Exit-Sizing übergibt den Verkaufsauftrag
direkt an das Kauf- & Verkaufsmodul und läuft dabei bewusst nicht durch das
Risikomanagement (Verkauf reduziert Risiko)." Analog zum bestehenden
LLM-Order-Pfad-Guard (`tests/architecture/test_order_pfad_invariante.py`,
`app.adapters.llm`) scannt dieser Test statisch (AST, kein Codeausführen),
dass `app/domain/sizing/**/*.py` keinen Import aus dem
Risikomanagement-Konfigurations-/Gate-Pfad enthält
(`app.contracts.risikomanagement`, `app.db.depotstrategie`, S-043) — die
strukturelle Absicherung dafür, dass Exit-Sizing kein Risiko-Gate
konsumiert/aufruft (AC12), nicht nur eine Dokumentations-Behauptung im
Moduldocstring.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_ROOT = _REPO_ROOT / "app"

#: AC12: Import-Präfixe des Risikomanagement-Konfigurations-/Gate-Pfads
#: (S-043, `app.contracts.risikomanagement.DepotstrategieKonfiguration`,
#: `app.db.depotstrategie.lade_aktive_depotstrategie`) — Exit-Sizing darf
#: keines davon importieren (umgeht das Risikomanagement bewusst).
_VERBOTENE_PRAEFIXE: tuple[str, ...] = (
    "app.contracts.risikomanagement",
    "app.db.depotstrategie",
)


def _importiert_risikomanagement(pfad: Path) -> str | None:
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


def test_exit_sizing_module_importieren_kein_risikomanagement() -> None:
    """@trace sizing#AC12 — scannt alle Module unter `app/domain/sizing/`
    (inkl. `exit_sizing.py`) auf einen Import aus
    `app.contracts.risikomanagement` oder `app.db.depotstrategie`."""
    verstoesse = {
        str(pfad.relative_to(_APP_ROOT)): treffer
        for pfad in (_APP_ROOT / "domain" / "sizing").glob("*.py")
        if (treffer := _importiert_risikomanagement(pfad)) is not None
    }
    assert not verstoesse, (
        f"Exit-Sizing darf laut AC12 nie das Risikomanagement importieren, "
        f"gefunden in: {verstoesse}"
    )


def test_scan_erkennt_risikomanagement_import_in_sizing_datei(tmp_path: Path) -> None:
    """@trace sizing#AC12 — Fixture-Beleg: `_importiert_risikomanagement`
    erkennt einen tatsächlichen Verstoss (Import aus dem Risikomanagement-
    Pfad in einer synthetischen Datei) korrekt und lässt eine unauffällige
    Datei unbeanstandet."""
    verstoss_datei = tmp_path / "exit_sizing_bad.py"
    verstoss_datei.write_text(
        "from app.contracts.risikomanagement import DepotstrategieKonfiguration\n"
        "\n\n"
        "def bestimme_exit_order() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_risikomanagement(verstoss_datei) == "app.contracts.risikomanagement"

    verstoss_datei_plain_import = tmp_path / "exit_sizing_bad_plain.py"
    verstoss_datei_plain_import.write_text(
        "import app.db.depotstrategie\n\n\ndef bestimme_exit_order() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_risikomanagement(verstoss_datei_plain_import) == "app.db.depotstrategie"

    saubere_datei = tmp_path / "exit_sizing.py"
    saubere_datei.write_text(
        "from app.contracts.sizing import Verkaufsauftrag\n\n\n"
        "def bestimme_exit_order() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_risikomanagement(saubere_datei) is None
