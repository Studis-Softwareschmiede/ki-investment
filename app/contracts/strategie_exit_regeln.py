"""Modul-Verträge Exit-Regel-Ableitung (Spec `docs/specs/strategie-exit-regeln.md`
§Verträge „Konfigurationsdaten (provisorische Defaults)", Story S-038,
AC6-AC9).

`ExitDefaultVorschlag` ist der provisorische, konfigurierbare Default-
Vorschlag, den `app.db.exit_regel_ableitung.leite_exit_regeln_ab` liefert —
bewusst ein EIGENES DTO, nicht `app.contracts.depot.ExitRegeln`: Letzteres
bildet das beim Kauf bereits FIXIERTE, minimale Bündel ab (numerische
Felder, `float`-typisiert, Depot prüft nur Präsenz), während dieses DTO die
noch nicht fixierte ABLEITUNG mit Freitext-Begründung (`stop_hinweis`,
`take_profit_hinweis`) und einem expliziten Unvollständigkeits-Flag
(`stop_unbestimmt`, ATR-Edge-Case) trägt — unterschiedliche Lebenszyklus-
Stufe desselben Spec-Verträge, keine strukturelle Duplikation
(architecture.md P2: verschiedene Zwecke, kein gemeinsamer Aufrufer).
Story S-040 (AC1/AC5/AC10/AC11, „Attribut-Bündel-Fixierung") ist dafür
zuständig, aus einem `ExitDefaultVorschlag` (oder einer manuellen
Override-Eingabe) das fixierte `ExitRegeln`-Bündel abzuleiten und in
`exit_rule` zu persistieren — NICHT Teil dieser Story.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Literal

#: Die 5 Default-Exit-Set-Kategorien der AC8-Tabelle plus der generische
#: AC7-Fallback für Strategien ohne eigene Tabellenzeile (siehe
#: AC8-Präzisierung in der Spec).
ExitKategorie = Literal[
    "value_aktien",
    "growth_momentum",
    "index_buy_and_hold",
    "krypto",
    "daytrade_swing",
    "generisch",
]

#: Stop-Mechanismus-Typen — deckungsgleich mit den in AC8 genannten
#: Mechanismen. Bewusst NICHT identisch mit
#: `app.db.models.EXIT_RULE_STOP_TYP_VALUES` (jenes Enum ist die bereits in
#: S-015 fixierte Persistenz-Spalte `exit_rule.stop_typ`) — die Erweiterung
#: um 'technisch' bei der tatsächlichen Fixierung ist Sache von S-040.
StopTyp = Literal["fundamental", "atr_trailing", "fix_pct", "technisch", "keiner"]


@dataclass(frozen=True)
class ExitDefaultVorschlag:
    """Ergebnis von `app.db.exit_regel_ableitung.leite_exit_regeln_ab` — der
    provisorische, konfigurierbare Default-Vorschlag (AC8/AC9) für die drei
    beim Kauf immer zu dokumentierenden Exit-Regel-Kategorien (AC6):

    - **Thesis-Breakpoint** (`thesis_invalidierung`) — Pflicht, hier nur
      validiert (nicht leer); die inhaltliche Herleitung ist NICHT Teil
      dieser Story (kommt vom Aufrufer/Analyst).
    - **Drawdown-/Stop-Trigger** (`stop_typ` + `stop_hinweis` +
      `stop_parameter`) — Pflicht, hier immer gesetzt (`stop_hinweis` ist
      nie leer); `stop_parameter` kann `None` sein (siehe
      `stop_unbestimmt`).
    - **Time-Box** (`time_box`) — optional, darf `None` sein (A2).

    `stop_unbestimmt`: `True`, wenn der ATR-Wert nicht berechenbar war
    (Edge-Case „ATR nicht berechenbar (zu wenig Kurshistorie)") — die
    Exit-Regel gilt dann laut Spec als unvollständig, auch wenn `stop_typ`/
    `stop_hinweis` (die Kategorie-Zuordnung selbst) gesetzt bleiben.
    """

    kategorie: ExitKategorie
    stop_typ: StopTyp
    stop_hinweis: str
    stop_parameter: Decimal | None
    stop_unbestimmt: bool
    take_profit_hinweis: str | None
    time_box: timedelta | None
    thesis_invalidierung: str
