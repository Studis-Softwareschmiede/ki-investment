"""Exit-Sizing — dringlichkeitsbasierte Verkaufsausführung (Story S-042,
Spec `docs/specs/sizing.md`, Alternative Flow A1, AC8/AC12) + Feintuning
(Story S-055, AC9/AC10/AC11).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB. Deckt:

- **AC8** — `bestimme_exit_order` legt Menge, Tranchierung und Order-Typ
  primär nach der Dringlichkeit des `SellSignal` fest:
  - **Hard-Exit** (`dringlichkeit == "hard"`): sofort die gesamte
    Position, Order-Typ `"stop_market"` (Edge-Cases der Spec: "Für
    kritische Not-Ausstiege (Hard-Exit) wird Stop-Market gewählt (Fill
    sicher, Preis nicht), nicht Stop-Limit" — entscheidet damit die
    AC8-Alternative "Market bzw. Stop-Market" für den Not-Ausstiegsfall),
    `ausfuehrungsprofil="sofort"`, unverändert ein Einzel-Element-`tranchen`
    (kein Abstand, `tranchen_trigger=None`) — die AC10/AC11-Feintuning-
    Logik greift bewusst nur im Soft-Exit-Zweig (TWAP ist eine über Zeit
    gestreckte Ausführung, unvereinbar mit der Hard-Exit-Dringlichkeit
    "sofort"; Tranchierung ist laut Verträge-Abschnitt ohnehin nur für
    "gestaffelte Verkäufe" definiert).
  - **Soft-Exit** (`dringlichkeit == "soft"`): gestaffelt,
    `ausfuehrungsprofil="gestaffelt"`. Order-Typ ist `"limit"`
    (AC8-Wortlaut: "Order-Typ Limit als Default"), ausser AC10 löst TWAP
    aus (siehe unten). `tranchen` zerlegt `position_menge` seit S-055 in
    `konfiguration.anzahl_tranchen` (Default 3, Spec-Bereich 3–4)
    gleichmässige Teilmengen (AC11, `_teile_in_tranchen`, Summe ==
    `position_menge`, kein Rundungsverlust), `tranchen_trigger` trägt den
    konfigurierten Abstands-Auslöser (AC11, zeit- oder ereignisbasiert).

- **AC9** — `berechne_limit_anteil_kpi` bildet die im Verträge-Abschnitt
  geforderte "messbare Betriebs-Kennzahl" ("über alle Ausführungen sollen
  ≥ 95 % Limit-Orders sein; Market-Orders nur im Notfall") über eine
  bereits erzeugte Menge von `Verkaufsauftrag`-Objekten — reine
  Aggregation, kein Bestandteil von `bestimme_exit_order` selbst (die
  KPI wird über mehrere Ausführungen hinweg geführt, nicht pro Trade
  entschieden).

- **AC10** — Für Soft-Exits, deren `position_menge` relativ zum
  übergebenen `tageshandelsvolumen` die konfigurierte
  `konfiguration.twap_schwelle_pct` erreicht oder überschreitet, liefert
  `bestimme_exit_order` `order_typ="twap"` statt `"limit"` (Spec: "Für
  grosse Positionen relativ zum Handelsvolumen wird TWAP verwendet, um
  den Marktimpact zu minimieren"). `tageshandelsvolumen` ist optional
  (P1, kein DB-Zugriff — ein künftiger Orchestrierungs-Layer speist es
  aus der Datenquellen-Abfrage, Verträge "Exit-Sizing Input: ...
  liquiditaet"); fehlt es, bleibt das S-042-Verhalten (`"limit"`)
  unverändert (Cold-Start, analog dem optionalen `ExitTriggerKontext`
  in `app.contracts.analyse_pipelines`).

- **AC11** — `_teile_in_tranchen` zerlegt eine Soft-Exit-`position_menge`
  in `konfiguration.anzahl_tranchen` (3–4, konfigurierbar) möglichst
  gleiche Teilmengen ohne Rundungsverlust (Summe der Tranchen ==
  `position_menge`, verbleibender Rest nach Ganzzahl-Teilung landet auf
  der letzten Tranche). Der Abstand zwischen den Tranchen wird laut
  `konfiguration.tranchen_abstand_art` entweder zeitbasiert
  (`tranchen_zeitabstand`) oder ereignisbasiert (`weitere -X%`,
  `tranchen_weitere_bewegung_pct`) ausgelöst — abgebildet im
  `Verkaufsauftrag.tranchen_trigger` (`TranchenAbstandsTrigger`). Die
  tatsächliche zeitgesteuerte/ereignisgesteuerte AUSLÖSUNG (Scheduler,
  Marktdaten-Polling) ist kein Domain-Kern-Bestandteil (P1/P3) — dieses
  Modul liefert nur die Konfiguration des Triggers, nicht dessen Feuern.

- **AC12** — der zurückgelieferte `Verkaufsauftrag` ist zur direkten
  Übergabe an das (in dieser Codebasis noch nicht gebaute) Kauf- &
  Verkaufsmodul bestimmt ("übergibt den Verkaufsauftrag direkt ... und
  läuft dabei bewusst nicht durch das Risikomanagement"). Strukturell
  umgesetzt durch Unterlassung: dieses Modul importiert nichts aus
  `app.contracts.risikomanagement` oder `app.db.depotstrategie` (dem
  Risikomanagement-Konfigurations-/Gate-Pfad, S-043) und ruft keine
  Risiko-Gate-Funktion auf — `bestimme_exit_order` nimmt ausschliesslich
  das `SellSignal`, die zu verkaufende Menge, optional das
  Handelsvolumen (AC10) und die Exit-Sizing-Feintuning-Konfiguration
  (AC9/AC10/AC11) entgegen, keine Depotstrategie-/Limit-Daten. Ein
  AST-Import-Scan
  (`tests/architecture/test_exit_sizing_umgeht_risikomanagement.py`,
  analog zum LLM-Order-Pfad-Guard
  `tests/architecture/test_order_pfad_invariante.py`) belegt das
  strukturell, nicht nur per Dokumentation.

`position_menge` (die aktuell gehaltene Menge des Titels) kommt als
Parameter herein (P1, kein DB-Zugriff) — ein künftiger Orchestrierungs-
Layer speist sie aus dem Depot-Bestand. Preisfindung (`preis`) ist
weiterhin explizit NICHT Teil dieser Story (`docs/specs/sizing.md`, Item
deckt AC9/AC10/AC11)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from app.contracts.analyse_pipelines import SellSignal
from app.contracts.sizing import (
    ExitSizingKonfiguration,
    LimitAnteilKpi,
    OrderTyp,
    TranchenAbstandsTrigger,
    Verkaufsauftrag,
)

#: Rundungsraster für Mengen (NUMERIC(20,8)-kompatibel, P7/ADR-010,
#: analog `app.db.models.Position.menge`).
_MENGE_QUANTUM = Decimal("0.00000001")

#: Rundungsraster für die AC9-KPI-Anteilswerte (0–1, 6 Nachkommastellen) —
#: kaufmännisch gerundet (`ROUND_HALF_UP`), analog
#: `app.domain.sizing.position_sizing._ANTEIL_QUANTUM`.
_ANTEIL_QUANTUM = Decimal("0.000001")


def _teile_in_tranchen(menge: Decimal, anzahl_tranchen: int) -> tuple[Decimal, ...]:
    """AC11: zerlegt `menge` in `anzahl_tranchen` möglichst gleiche
    Teilmengen ohne Rundungsverlust — die Summe der zurückgelieferten
    Tranchen ist exakt `menge` (der nach der Ganzzahl-Teilung
    verbleibende Rest, ein Vielfaches von `_MENGE_QUANTUM`, landet auf
    der letzten Tranche)."""
    basis = (menge / anzahl_tranchen).quantize(_MENGE_QUANTUM, rounding=ROUND_DOWN)
    tranchen = [basis] * anzahl_tranchen
    tranchen[-1] += menge - basis * anzahl_tranchen
    return tuple(tranchen)


def _bestimme_tranchen_trigger(
    konfiguration: ExitSizingKonfiguration,
) -> TranchenAbstandsTrigger:
    """AC11: baut den zur `konfiguration.tranchen_abstand_art` passenden
    Abstands-Auslöser — trägt jeweils nur das zur `art` passende Feld."""
    if konfiguration.tranchen_abstand_art == "zeitbasiert":
        return TranchenAbstandsTrigger(
            art="zeitbasiert",
            zeitabstand=konfiguration.tranchen_zeitabstand,
        )
    return TranchenAbstandsTrigger(
        art="ereignisbasiert",
        weitere_bewegung_pct=konfiguration.tranchen_weitere_bewegung_pct,
    )


def _bestimme_soft_exit_order_typ(
    position_menge: Decimal,
    tageshandelsvolumen: Decimal | None,
    konfiguration: ExitSizingKonfiguration,
) -> OrderTyp:
    """AC10: `"twap"`, wenn `position_menge` relativ zu
    `tageshandelsvolumen` die konfigurierte `twap_schwelle_pct` erreicht
    oder überschreitet; sonst der Soft-Exit-Default `"limit"` (AC8).
    Fehlt `tageshandelsvolumen` (kein Datenpunkt verfügbar), bleibt das
    Verhalten unverändert `"limit"`."""
    if tageshandelsvolumen is None:
        return "limit"
    if tageshandelsvolumen <= 0:
        raise ValueError(f"tageshandelsvolumen muss > 0 sein, war {tageshandelsvolumen!r}.")
    positionsanteil_am_volumen = position_menge / tageshandelsvolumen
    if positionsanteil_am_volumen >= konfiguration.twap_schwelle_pct:
        return "twap"
    return "limit"


def bestimme_exit_order(
    sell_signal: SellSignal,
    *,
    position_menge: Decimal,
    tageshandelsvolumen: Decimal | None = None,
    konfiguration: ExitSizingKonfiguration | None = None,
) -> Verkaufsauftrag:
    """AC8/AC10/AC11: bestimmt Menge, Tranchierung und Order-Typ primär
    nach `sell_signal.dringlichkeit` (Hard-Exit -> sofort/`stop_market`,
    Soft-Exit -> gestaffelt/`limit` bzw. `twap` ab der AC10-Schwelle) und
    liefert den Verkaufsauftrag zur direkten Übergabe an das Kauf- &
    Verkaufsmodul (AC12 — kein Risikomanagement-Gate dazwischen, siehe
    Moduldocstring).

    Raises:
        ValueError: `position_menge` ist `<= 0` (keine gültige, noch
            offene Position zum Verkauf) oder `tageshandelsvolumen` ist
            explizit übergeben und `<= 0` (kein gültiger Volumen-Datenpunkt).
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
            tranchen_trigger=None,
        )

    aktive_konfiguration = konfiguration or ExitSizingKonfiguration()
    order_typ = _bestimme_soft_exit_order_typ(
        position_menge, tageshandelsvolumen, aktive_konfiguration
    )
    return Verkaufsauftrag(
        titel_id=sell_signal.titel_id,
        menge=position_menge,
        tranchen=_teile_in_tranchen(position_menge, aktive_konfiguration.anzahl_tranchen),
        order_typ=order_typ,
        preis=None,
        ausfuehrungsprofil="gestaffelt",
        tranchen_trigger=_bestimme_tranchen_trigger(aktive_konfiguration),
    )


def berechne_limit_anteil_kpi(
    auftraege: Sequence[Verkaufsauftrag],
    konfiguration: ExitSizingKonfiguration | None = None,
) -> LimitAnteilKpi:
    """AC9: berechnet die Limit-Anteil-Betriebskennzahl über `auftraege`
    (Spec: "über alle Ausführungen sollen ≥ 95 % Limit-Orders sein;
    Market-Orders nur im Notfall (Hard-Exit)"). Zählt ausschliesslich
    `order_typ == "limit"` als Limit-Order (`"twap"`, `"stop_market"` und
    `"market"` zählen nicht mit — beide sind laut Vertrag eigenständige
    Order-Typen).

    Bei `auftraege == ()` (keine Ausführungen) gilt `limit_anteil == 1`
    und `ziel_erreicht == True` (vakuose Wahrheit, siehe
    `app.contracts.sizing.LimitAnteilKpi`-Docstring)."""
    aktive_konfiguration = konfiguration or ExitSizingKonfiguration()
    anzahl_gesamt = len(auftraege)
    anzahl_limit = sum(1 for auftrag in auftraege if auftrag.order_typ == "limit")

    if anzahl_gesamt == 0:
        limit_anteil = Decimal(1)
    else:
        limit_anteil = (Decimal(anzahl_limit) / Decimal(anzahl_gesamt)).quantize(
            _ANTEIL_QUANTUM, rounding=ROUND_HALF_UP
        )

    return LimitAnteilKpi(
        anzahl_gesamt=anzahl_gesamt,
        anzahl_limit=anzahl_limit,
        limit_anteil=limit_anteil,
        ziel=aktive_konfiguration.limit_anteil_ziel,
        ziel_erreicht=limit_anteil >= aktive_konfiguration.limit_anteil_ziel,
    )


__all__ = ["berechne_limit_anteil_kpi", "bestimme_exit_order"]
