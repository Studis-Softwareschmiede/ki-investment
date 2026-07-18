"""Exit-Sizing — dringlichkeitsbasierte Verkaufsausführung (Story S-042,
Spec `docs/specs/sizing.md`, Alternative Flow A1, AC8/AC12).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB. Deckt:

- **AC8** — `bestimme_exit_order` legt Menge, Tranchierung und Order-Typ
  primär nach der Dringlichkeit des `SellSignal` fest:
  - **Hard-Exit** (`dringlichkeit == "hard"`): sofort die gesamte
    Position, Order-Typ `"stop_market"` (Edge-Cases der Spec: "Für
    kritische Not-Ausstiege (Hard-Exit) wird Stop-Market gewählt (Fill
    sicher, Preis nicht), nicht Stop-Limit" — entscheidet damit die
    AC8-Alternative "Market bzw. Stop-Market" für den Not-Ausstiegsfall),
    `ausfuehrungsprofil="sofort"`.
  - **Soft-Exit** (`dringlichkeit == "soft"`): gestaffelt, Order-Typ
    `"limit"` (AC8-Wortlaut: "Order-Typ Limit als Default"),
    `ausfuehrungsprofil="gestaffelt"`.

  Die tatsächliche Zerlegung eines Soft-Exit in 3-4 Tranchen samt
  zeit-/ereignisbasierter Abstands-Logik (AC11) ist NICHT Teil dieser
  Story (Item deckt ausschliesslich AC8+AC12) — `tranchen` bleibt hier in
  beiden Fällen ein Einzel-Element mit der vollen `menge`; eine Folgestory
  ergänzt die AC11-Zerlegung additiv auf demselben Vertrag
  (`app.contracts.sizing.Verkaufsauftrag`).

- **AC12** — der zurückgelieferte `Verkaufsauftrag` ist zur direkten
  Übergabe an das (in dieser Codebasis noch nicht gebaute) Kauf- &
  Verkaufsmodul bestimmt ("übergibt den Verkaufsauftrag direkt ... und
  läuft dabei bewusst nicht durch das Risikomanagement"). Strukturell
  umgesetzt durch Unterlassung: dieses Modul importiert nichts aus
  `app.contracts.risikomanagement` oder `app.db.depotstrategie` (dem
  Risikomanagement-Konfigurations-/Gate-Pfad, S-043) und ruft keine
  Risiko-Gate-Funktion auf — `bestimme_exit_order` nimmt ausschliesslich
  das `SellSignal` und die zu verkaufende Menge entgegen, keine
  Depotstrategie-/Limit-Daten. Ein AST-Import-Scan
  (`tests/architecture/test_exit_sizing_umgeht_risikomanagement.py`,
  analog zum LLM-Order-Pfad-Guard
  `tests/architecture/test_order_pfad_invariante.py`) belegt das
  strukturell, nicht nur per Dokumentation.

`position_menge` (die aktuell gehaltene Menge des Titels) kommt als
Parameter herein (P1, kein DB-Zugriff) — ein künftiger Orchestrierungs-
Layer speist sie aus dem Depot-Bestand. Preisfindung (`preis`), die
AC9-Limit-Anteil-Betriebskennzahl, die AC10-TWAP-Schwelle und die
AC11-Tranchenzahl/Abstands-Trigger-Logik sind explizit NICHT Teil dieser
Story (`docs/specs/sizing.md`, Item deckt ausschliesslich AC8 + AC12)."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.analyse_pipelines import SellSignal
from app.contracts.sizing import Verkaufsauftrag


def bestimme_exit_order(
    sell_signal: SellSignal,
    *,
    position_menge: Decimal,
) -> Verkaufsauftrag:
    """AC8: bestimmt Menge, Tranchierung und Order-Typ primär nach
    `sell_signal.dringlichkeit` (Hard-Exit -> sofort/`stop_market`,
    Soft-Exit -> gestaffelt/`limit`) und liefert den Verkaufsauftrag zur
    direkten Übergabe an das Kauf- & Verkaufsmodul (AC12 — kein
    Risikomanagement-Gate dazwischen, siehe Moduldocstring).

    Raises:
        ValueError: `position_menge` ist `<= 0` (keine gültige, noch
            offene Position zum Verkauf).
    """
    if position_menge <= 0:
        raise ValueError(f"position_menge muss > 0 sein, war {position_menge!r}.")

    if sell_signal.dringlichkeit == "hard":
        return Verkaufsauftrag(
            titel_id=sell_signal.titel_id,
            menge=position_menge,
            tranchen=(position_menge,),
            order_typ="stop_market",
            preis=None,
            ausfuehrungsprofil="sofort",
        )

    return Verkaufsauftrag(
        titel_id=sell_signal.titel_id,
        menge=position_menge,
        tranchen=(position_menge,),
        order_typ="limit",
        preis=None,
        ausfuehrungsprofil="gestaffelt",
    )


__all__ = ["bestimme_exit_order"]
