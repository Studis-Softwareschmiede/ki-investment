"""Architektur-Invariante: LLM nie im Order-Pfad (Story S-014).

Covers (llm-grounding): AC7

BR-001 (architecture.md §9) + Spec `docs/specs/llm-grounding.md` AC7: Buy-
Signal, Position-/Exit-Sizing, Risiko-Gate und Order-Ausführung sind
ausschließlich deterministische Module — keines von ihnen darf
`app.adapters.llm` importieren oder sich sonst vom LLM übersteuern lassen.
architecture.md §9 nennt explizit die zu scannenden Modulpfade:
`domain/sizing`, `domain/risk`, `orchestration/*_pipeline`,
`orchestration/execution_service` — und benennt den Grep-/Import-Linter-
Test als Prüfmethode.

Cold-Start-Hinweis (S-014, estimate_note): keines dieser Order-Pfad-Module
existiert im Repo bisher (sie folgen in späteren Stories — sizing,
risikomanagement, ausfuehrung-paper). Die Prüfung läuft trotzdem schon
jetzt als AST-Scan über genau die Glob-Pfadmuster, die mit den künftigen
Modulen matchen werden: sobald `app/domain/sizing/`, `app/domain/risk/`,
`app/orchestration/*_pipeline.py` oder
`app/orchestration/execution_service.py` angelegt werden, greift dieser
Test automatisch, ohne Änderung an dieser Datei. Damit der (heute leere)
Scan nicht bloß trivial grün ist, belegt ein zweiter Test
(`test_scan_erkennt_llm_import_in_order_pfad_datei`) an einer
synthetischen Fixture, dass die Scan-Logik einen echten Verstoß tatsächlich
erkennt.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_ROOT = _REPO_ROOT / "app"

#: Order-Pfad-Modulpfade (BR-001, architecture.md §4/§9) — Glob-Muster
#: relativ zu `app/`.
_ORDER_PFAD_GLOBS: tuple[str, ...] = (
    "domain/sizing/**/*.py",
    "domain/risk/**/*.py",
    "orchestration/*_pipeline.py",
    "orchestration/execution_service.py",
)

#: Verbotenes Import-Präfix (BR-001): kein Order-Pfad-Modul darf den
#: LLM-Adapter importieren.
_VERBOTENES_PRAEFIX = "app.adapters.llm"


def _importiert_llm(pfad: Path) -> str | None:
    """Parst `pfad` per AST und liefert den ersten gefundenen Import aus
    `app.adapters.llm` (voll qualifiziert) oder `None`. Reines statisches
    Scannen (kein Ausführen von Code) — sicher auch gegen fremden/kaputten
    Code."""
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for alias in knoten.names:
                if alias.name.startswith(_VERBOTENES_PRAEFIX):
                    return alias.name
        elif isinstance(knoten, ast.ImportFrom):
            modul = knoten.module or ""
            if modul.startswith(_VERBOTENES_PRAEFIX):
                return modul
    return None


def _order_pfad_dateien() -> list[Path]:
    """Sammelt alle aktuell existierenden Order-Pfad-Dateien über die
    kanonischen BR-001-Glob-Muster (leer, solange die künftigen Module
    noch nicht angelegt sind — Cold-Start)."""
    dateien: list[Path] = []
    for muster in _ORDER_PFAD_GLOBS:
        dateien.extend(_APP_ROOT.glob(muster))
    return dateien


def test_order_pfad_module_importieren_kein_llm() -> None:
    """@trace llm-grounding#AC7 — scannt alle bereits existierenden
    Order-Pfad-Module (BR-001: domain/sizing, domain/risk,
    orchestration/*_pipeline, orchestration/execution_service) auf einen
    Import aus `app.adapters.llm`. Existieren die Module noch nicht
    (Cold-Start, S-014), ist die Dateiliste leer und die Assertion
    trivial erfüllt — der Beleg, dass der Scan bei einem echten Verstoß
    tatsächlich anschlägt, liefert
    `test_scan_erkennt_llm_import_in_order_pfad_datei`."""
    verstoesse = {
        str(pfad.relative_to(_APP_ROOT)): treffer
        for pfad in _order_pfad_dateien()
        if (treffer := _importiert_llm(pfad)) is not None
    }
    assert not verstoesse, (
        f"Order-Pfad-Module dürfen laut BR-001 nie das LLM importieren, gefunden in: {verstoesse}"
    )


def test_scan_erkennt_llm_import_in_order_pfad_datei(tmp_path: Path) -> None:
    """@trace llm-grounding#AC7 — Fixture-Beleg: `_importiert_llm` erkennt
    einen tatsächlichen Verstoß (Import aus `app.adapters.llm` in einer
    synthetischen Order-Pfad-Datei) korrekt und lässt eine unauffällige
    Datei unbeanstandet — notwendig, weil die reale Codebasis (Cold-Start)
    noch keine Order-Pfad-Module enthält und der obige Test sonst nur
    einen leeren, unbewiesenen Scan belegen würde."""
    verstoss_datei = tmp_path / "risk_gate.py"
    verstoss_datei.write_text(
        "from app.adapters.llm.grounding import pruefe_grounding\n"
        "\n\n"
        "def entscheide() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_llm(verstoss_datei) == "app.adapters.llm.grounding"

    verstoss_datei_plain_import = tmp_path / "sizing_bad.py"
    verstoss_datei_plain_import.write_text(
        "import app.adapters.llm.cross_check\n\n\ndef sizing() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_llm(verstoss_datei_plain_import) == "app.adapters.llm.cross_check"

    saubere_datei = tmp_path / "sizing.py"
    saubere_datei.write_text(
        "from app.contracts.llm_grounding import AnalyseOutput\n\n\ndef sizing() -> None: ...\n",
        encoding="utf-8",
    )
    assert _importiert_llm(saubere_datei) is None
