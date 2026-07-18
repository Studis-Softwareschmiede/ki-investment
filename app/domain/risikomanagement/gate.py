"""Risikomanagement-Gate: Drei-Wege-Entscheid + Sektor-Konzentrations-Prüfung
(Story S-044, Spec `docs/specs/risikomanagement.md` AC2/AC5/AC6/AC12,
BR-014/BR-013).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB, kein eigener Grenzwert (AC11 — Grenzwerte kommen ausschliesslich als
`DepotstrategieKonfiguration`-Parameter herein, erzeugt von
`app.db.depotstrategie.lade_aktive_depotstrategie()`, S-043). Deckt:

- **AC5** — "Das Risikomanagement-Gate greift nur beim Kauf; jeder
  Verkaufsauftrag umgeht das Gate vollständig und ungeprüft." Strukturell
  umgesetzt durch Unterlassung + Signatur (analog zu `app.domain.sizing
  .exit_sizing`, S-042/AC12 der `sizing.md`-Spec, BR-013): `pruefe_kauf_gate`
  nimmt ausschliesslich eine `AnnotierteKaufOrder` (Kauf-Attribut-Bündel,
  S-040) entgegen — es gibt in diesem Modul keinen Aufrufpfad, über den ein
  `Verkaufsauftrag` (`app.contracts.sizing`) das Gate durchläuft.
  `tests/architecture/test_gate_greift_nur_beim_kauf.py` belegt zusätzlich
  strukturell (AST-Scan, spiegelbildlich zu
  `test_exit_sizing_umgeht_risikomanagement.py`), dass der Verkaufs-Pfad
  (`app/domain/sizing/`) dieses Modul nicht importiert.
- **AC6** — `pruefe_kauf_gate` liefert je Aufruf genau einen von drei
  Entscheiden (`GateEntscheid.entscheid`): `"durchwinken"` (volle geplante
  Grösse), `"deckeln"` (Kappung auf das erlaubte Maximum — **kein**
  Rück-Durchlauf ins Position-Sizing, reine Kappung des bereits fixierten
  `AnnotierteKaufOrder.ordergroesse`-Werts) oder `"blockieren"`
  (`freigegebene_groesse=0`).
- **AC2** — die (bislang einzige in dieser Story implementierte)
  Risikoprüfung ist die Sektor-/Branchen-Konzentration: bewertet **alle**
  offenen Positionen des Depots gewichtet nach Kostenbasis
  (`app.domain.portfolio.portfolio_aggregate.positionswert`), nicht die
  nominelle Anzahl Titel je Branche — eine Branche mit wenigen, aber
  wertmässig grossen Positionen wird genauso erkannt wie eine mit vielen
  kleinen. Klumpenrisiko je Anlageklasse, Korrelation, Drawdown-Limits und
  der portfolio-weite Kelly-Cap (AC8-AC10) sind NICHT Teil dieser Story.
- **AC12** — kann kein `DepotStand` geladen werden (`depot_stand=None`,
  deckt E1), liefert das Gate `"blockieren"` — "das Gate trifft keinen
  Durchwink-Entscheid; der Kauf wird sicherheitshalber nicht freigegeben".
  Analog behandelt: keine aktive Depotstrategie (`depotstrategie=None`) —
  ohne Grenzwert kein Entscheid möglich (siehe `app.db.depotstrategie
  .lade_aktive_depotstrategie`-Docstring: "ein Gate-Konsument muss diesen
  Fall analog E1 der Spec behandeln").

Edge-Case (Spec §Edge-Cases, nicht separat nummeriert, Teil der
AC6-Entscheidungslogik): eine geplante Ordergrösse `<= 0` führt ebenfalls
zu `"blockieren"` — es gibt nichts, das durchgewinkt oder gedeckelt werden
könnte.

`depot_stand`/`depotstrategie`/`gics_branche` kommen als Parameter herein
(P1, kein DB-Zugriff) — ein künftiger Orchestrierungs-Layer speist sie aus
`app.domain.portfolio.portfolio_aggregate.ermittle_depot_stand`,
`app.db.depotstrategie.lade_aktive_depotstrategie` und den
Instrument-Stammdaten (`Instrument.gics_sector`). `gics_branche` ist nicht
Teil von `AnnotierteKaufOrder` (`docs/specs/strategie-exit-regeln.md`
§Verträge "Output" führt kein Branchen-Feld) — analog zu
`PositionsBestand.gics_branche` (S-036) wird sie hier separat übergeben.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.contracts.risikomanagement import DepotstrategieKonfiguration, GateEntscheid
from app.contracts.strategie_exit_regeln import AnnotierteKaufOrder
from app.domain.portfolio.portfolio_aggregate import UNBEKANNTE_BRANCHE, DepotStand, positionswert

#: Rundungsraster für CHF-Geldbeträge (NUMERIC(20,8)-kompatibel, P7/ADR-010)
#: — kaufmännisch gerundet (`ROUND_HALF_UP`), analog zu
#: `app.domain.portfolio.position_booking._quantize_geld`.
_GELD_QUANTUM = Decimal("0.00000001")

#: 100 % als Anteil (1.0) — Grenze, ab der ein Sektor-Limit real keine
#: Deckelung/Blockade mehr bewirken kann (Division durch `1 - Anteil` in
#: `_max_erlaubte_sektor_groesse` wäre sonst durch 0).
_VOLLER_ANTEIL = Decimal("1")


def _quantize_geld(wert: Decimal) -> Decimal:
    return wert.quantize(_GELD_QUANTUM, rounding=ROUND_HALF_UP)


def _branche(gics_branche: str | None) -> str:
    """Sentinel-Behandlung analog `portfolio_aggregate.berechne_portfolio_
    aggregat` — fehlende Branchenzuordnung (`None`) fällt in den
    `UNBEKANNTE_BRANCHE`-Bucket statt aus der Prüfung zu fallen."""
    return gics_branche or UNBEKANNTE_BRANCHE


def _max_erlaubte_sektor_groesse(
    *, sektorwert_bestehend: Decimal, gesamtwert_bestehend: Decimal, max_sektor_anteil: Decimal
) -> Decimal:
    """Löst `(sektorwert_bestehend + x) / (gesamtwert_bestehend + x) ==
    max_sektor_anteil` nach `x` auf — die grösste zusätzliche
    Sektor-Investition, die das Sektor-Limit exakt trifft (AC2/A1,
    "Order genau am Limit -> gilt als eingehalten"). Vorausgesetzt:
    `sektorwert_bestehend / gesamtwert_bestehend < max_sektor_anteil`
    (sonst ist das Limit bereits ausgeschöpft, siehe Aufrufer) und
    `max_sektor_anteil < 1` (sonst kein reales Limit, siehe Aufrufer) —
    unter diesen Voraussetzungen ist das Ergebnis immer `>= 0`."""
    zaehler = max_sektor_anteil * gesamtwert_bestehend - sektorwert_bestehend
    nenner = _VOLLER_ANTEIL - max_sektor_anteil
    return zaehler / nenner


def pruefe_kauf_gate(
    kauf_order: AnnotierteKaufOrder,
    *,
    gics_branche: str | None,
    depotstrategie: DepotstrategieKonfiguration | None,
    depot_stand: DepotStand | None,
) -> GateEntscheid:
    """AC2/AC6/AC12: prüft `kauf_order` gegen die Sektor-/Branchen-Grenze
    der aktiven Depotstrategie und trifft den Drei-Wege-Entscheid.

    Args:
        kauf_order: das fixierte Attribut-Bündel (S-040) — nur
            Kauf-Orders (AC5, siehe Moduldocstring).
        gics_branche: GICS-Branche des Kauf-Kandidaten (`Instrument
            .gics_sector`, `None` falls nicht gepflegt — fällt dann in den
            `UNBEKANNTE_BRANCHE`-Bucket, siehe `_branche`).
        depotstrategie: die aktuell aktive Depotstrategie-Konfiguration
            (`app.db.depotstrategie.lade_aktive_depotstrategie`, AC11) —
            `None`, wenn keine Depotstrategie aktiv ist (kein Grenzwert
            verfügbar).
        depot_stand: der aktuelle Depot-Stand (`app.domain.portfolio
            .portfolio_aggregate.ermittle_depot_stand`) — `None`, wenn er
            nicht geladen werden konnte (AC12, E1).

    Returns:
        `GateEntscheid` mit genau einem der drei Entscheide (AC6).
    """
    if depot_stand is None:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                "Depot-Stand konnte nicht geladen werden (E1) — der Kauf wird "
                "sicherheitshalber nicht freigegeben (AC12)."
            ),
        )

    if depotstrategie is None:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                "Keine aktive Depotstrategie konfiguriert — kein Grenzwert "
                "verfügbar, der Kauf wird analog E1 nicht freigegeben (AC11, "
                "app.db.depotstrategie.lade_aktive_depotstrategie)."
            ),
        )

    if kauf_order.ordergroesse <= 0:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                f"Geplante Ordergrösse {kauf_order.ordergroesse!r} ist <= 0 — "
                "keine Freigabe (Edge-Case §Edge-Cases & Fehlerverhalten)."
            ),
        )

    branche = _branche(gics_branche)
    positionen = depot_stand.positionen
    gesamtwert_bestehend = sum((positionswert(p) for p in positionen), Decimal("0"))
    sektorwert_bestehend = sum(
        (positionswert(p) for p in positionen if _branche(p.gics_branche) == branche),
        Decimal("0"),
    )

    max_sektor_anteil = depotstrategie.max_sektor_pct / Decimal("100")

    if max_sektor_anteil >= _VOLLER_ANTEIL:
        # Limit ist 100 % (oder DB-Grenzfall darüber) — kein reales Limit,
        # jede Gewichtung <= 100 % erfüllt es trivially.
        return GateEntscheid(
            entscheid="durchwinken",
            freigegebene_groesse=_quantize_geld(kauf_order.ordergroesse),
            begruendung=(
                f"Sektor-Limit für Branche {branche!r} liegt bei "
                f"{depotstrategie.max_sektor_pct}% — kein reales Limit, volle "
                "Grösse freigegeben."
            ),
        )

    bestehende_sektor_anteil = (
        sektorwert_bestehend / gesamtwert_bestehend if gesamtwert_bestehend > 0 else Decimal("0")
    )

    if bestehende_sektor_anteil >= max_sektor_anteil:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                f"Sektor-Limit für Branche {branche!r} bereits ausgeschöpft "
                f"({bestehende_sektor_anteil * 100}% >= "
                f"{depotstrategie.max_sektor_pct}% Limit) — Kauf wird blockiert "
                "(AC2/A2)."
            ),
        )

    resultierender_gesamtwert = gesamtwert_bestehend + kauf_order.ordergroesse
    resultierender_sektorwert = sektorwert_bestehend + kauf_order.ordergroesse
    resultierende_sektor_anteil = resultierender_sektorwert / resultierender_gesamtwert

    if resultierende_sektor_anteil <= max_sektor_anteil:
        return GateEntscheid(
            entscheid="durchwinken",
            freigegebene_groesse=_quantize_geld(kauf_order.ordergroesse),
            begruendung=(
                f"Sektor-Limit für Branche {branche!r} eingehalten "
                f"(resultierende Gewichtung {resultierende_sektor_anteil * 100}% "
                f"<= {depotstrategie.max_sektor_pct}% Limit) — volle Grösse "
                "freigegeben."
            ),
        )

    max_erlaubte_groesse = _max_erlaubte_sektor_groesse(
        sektorwert_bestehend=sektorwert_bestehend,
        gesamtwert_bestehend=gesamtwert_bestehend,
        max_sektor_anteil=max_sektor_anteil,
    )

    if max_erlaubte_groesse <= 0:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                f"Sektor-Limit für Branche {branche!r} lässt keine positive "
                "zusätzliche Ordergrösse mehr zu — Kauf wird blockiert (AC2/A2)."
            ),
        )

    return GateEntscheid(
        entscheid="deckeln",
        freigegebene_groesse=_quantize_geld(max_erlaubte_groesse),
        begruendung=(
            f"Volle Grösse würde Sektor-Limit für Branche {branche!r} "
            f"({depotstrategie.max_sektor_pct}%) überschreiten — Order auf "
            f"{_quantize_geld(max_erlaubte_groesse)} CHF gedeckelt, kein "
            "Rück-Durchlauf ins Position-Sizing (AC2/A1/AC6)."
        ),
    )


__all__ = ["pruefe_kauf_gate"]
