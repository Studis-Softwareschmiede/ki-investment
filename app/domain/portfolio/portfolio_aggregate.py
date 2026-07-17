"""Portfolio-Aggregate & Depot-Stand-/Exit-Regeln-Bereitstellung (Modul 16
Depotmodul, Spec `docs/specs/depot.md`, Story S-036, AC8/AC9).

- **AC8** — `berechne_portfolio_aggregat` liefert Gewichtung je GICS-Branche,
  Gewichtung je Anlageklasse und die Cash-Quote als Input für die
  Risikoprüfung beim Kauf (`docs/specs/risikomanagement.md`). Die
  Bewertungsgrundlage je Position ist die Kostenbasis (`menge ×
  Ø-Einstandspreis`) — bewusst **keine** Live-Kurs-Abfrage: die
  Aggregation ist laut NFR "aus Positionen + Historie reproduzierbar (kein
  stiller Zustand ohne Herleitung)" — der Socket-Live-Kurs-Zugriff bleibt
  Sache der G/V-Bewertung (`app.domain.portfolio.position_booking
  .berechne_unrealisierten_gv`, S-016 AC2), nicht dieser Aggregation.
  `cash_quote` ist **kein** separates Cash-Ledger, sondern die Gewichtung
  der Anlageklasse 3 ("Cash / Geldmarkt", `docs/specs/anlageklassen-
  config.md` AC1/C-006) innerhalb `klassen_gewichtung` — Cash wird im
  Depot wie jede andere Anlageklasse als Position geführt.
- **AC9** — `ermittle_depot_stand` bündelt die offenen Positionen + das
  Aggregat für das Risikomanagement (Verträge-Vertrag "Output an
  Risikomanagement": `{ positionen[], branchen_gewichtung, klassen_
  gewichtung, cash_quote }`). `ermittle_titel_strategie_exit_regeln`
  liefert je **gehaltenem Titel** (nicht je Lot) Strategie + die beim Kauf
  fixierten Exit-Regeln für die Depot-Überwachung (Verträge-Vertrag
  "Output an Depot-Überwachung": `{ titel_id, strategie, exit_regeln }`) —
  hat ein Titel mehrere offene Lots (FIFO, A2 aus `depot.md`), wird der
  **älteste** Lot als Titel-Repräsentant verwendet (analog zur
  FIFO-Verbrauchsreihenfolge; `docs/specs/depot-ueberwachung.md` AC2
  verlangt ohnehin genau eine Abfrage je Titel, kein Duplikat je Lot).

Beide Funktionen nehmen eine bereits **mode-isoliert** gelesene
Positions-Liste entgegen (`app.domain.portfolio.ports.PositionRepository
.alle_offenen_positionen`, BR-113/BR-130) — sie filtern selbst nicht nach
`mode`, das ist Repository-Sache (Konvention identisch zu
`position_booking`/`transaction_historie`: reine Formel-/Aggregations-
Bausteine ohne DB-Zugriff, P1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.portfolio.ports import ExitRegelnBestand, PositionsBestand

#: Anlageklasse 3 = "Cash / Geldmarkt" (verbindliche Nummerierung C-006,
#: `docs/specs/anlageklassen-config.md` AC1) — `cash_quote` ist die
#: Gewichtung dieser Klasse innerhalb `klassen_gewichtung` (AC8).
CASH_ASSET_CLASS_ID = 3

#: Sentinel-Schlüssel für Positionen ohne bekannte GICS-Branche
#: (`Instrument.gics_sector` ist NULLable — die Erst-Anlage von
#: `instrument`-Zeilen ist nicht Teil dieser oder vorheriger Storys, siehe
#: `app.db.models.Instrument`-Docstring). Verhindert, dass eine solche
#: Position stillschweigend aus der Branchen-Gewichtung fällt (Σ bliebe
#: sonst < 100).
UNBEKANNTE_BRANCHE = "unbekannt"

#: Rundungsraster für Prozentwerte (NUMERIC(6,3), data-model.md
#: "Konventionen: Prozente/Scores").
_PROZENT_QUANTUM = Decimal("0.001")


def _quantize_prozent(wert: Decimal) -> Decimal:
    """Rundet einen Prozentwert an der Schreibgrenze auf 3 Nachkommastellen
    (NUMERIC(6,3)) — kaufmännisch gerundet (`ROUND_HALF_UP`), analog zu
    `position_booking._quantize_geld` (P7/ADR-010)."""
    return wert.quantize(_PROZENT_QUANTUM, rounding=ROUND_HALF_UP)


def _positionswert(position: PositionsBestand) -> Decimal:
    """Bewertungsgrundlage je Position für die Aggregation: Kostenbasis
    (`menge × Ø-Einstandspreis`) — siehe Moduldocstring, keine
    Live-Kurs-Abhängigkeit."""
    return position.menge * position.einstand_preis


@dataclass(frozen=True)
class PortfolioAggregat:
    """AC8: Portfolio-Aggregate als Risiko-Input. `branchen_gewichtung`
    (GICS-Branche → Anteil in %) und `klassen_gewichtung` (Anlageklasse
    1–11 → Anteil in %) summieren sich je auf 100 (± Rundungsdrift aus der
    unabhängigen Quantisierung je Schlüssel), sofern mindestens eine
    offene Position existiert — bei einem leeren Depot sind beide Dicts
    leer und `cash_quote` ist 0 (kein Fehler, kein Divide-by-Zero)."""

    branchen_gewichtung: dict[str, Decimal]
    klassen_gewichtung: dict[int, Decimal]
    cash_quote: Decimal


@dataclass(frozen=True)
class DepotStand:
    """AC9: Depot-Stand für das Risikomanagement — offene Positionen +
    Portfolio-Aggregate in einem Objekt (Verträge-Vertrag "Output an
    Risikomanagement")."""

    positionen: tuple[PositionsBestand, ...]
    aggregat: PortfolioAggregat


@dataclass(frozen=True)
class TitelStrategieExitRegeln:
    """AC9: Output an die Depot-Überwachung — je gehaltenem Titel
    Anlageklasse + Strategie + die beim Kauf fixierten Exit-Regeln
    (Verträge-Vertrag "Output an Depot-Überwachung"). `anlageklasse`
    ergänzt in S-032 (`docs/specs/depot-ueberwachung.md` AC1 benötigt sie
    zur Bestimmung der je Klasse überwachten Grössen, AC3) — stammt
    unverändert aus `PositionsBestand.asset_class_id` des Titel-
    repräsentierenden (ältesten) Lots."""

    titel_id: str
    anlageklasse: int
    strategie: str | None
    exit_regeln: ExitRegelnBestand


def berechne_portfolio_aggregat(positionen: Iterable[PositionsBestand]) -> PortfolioAggregat:
    """AC8: Gewichtung je GICS-Branche, je Anlageklasse und Cash-Quote aus
    den übergebenen offenen Positionen (bereits mode-isoliert gelesen,
    siehe Moduldocstring)."""
    positionsliste = list(positionen)
    gesamtwert = sum((_positionswert(p) for p in positionsliste), Decimal("0"))

    if gesamtwert == 0:
        return PortfolioAggregat(
            branchen_gewichtung={}, klassen_gewichtung={}, cash_quote=Decimal("0")
        )

    branchen_werte: dict[str, Decimal] = {}
    klassen_werte: dict[int, Decimal] = {}
    for position in positionsliste:
        branche = position.gics_branche or UNBEKANNTE_BRANCHE
        wert = _positionswert(position)
        branchen_werte[branche] = branchen_werte.get(branche, Decimal("0")) + wert
        klassen_werte[position.asset_class_id] = (
            klassen_werte.get(position.asset_class_id, Decimal("0")) + wert
        )

    branchen_gewichtung = {
        branche: _quantize_prozent(wert / gesamtwert * 100)
        for branche, wert in branchen_werte.items()
    }
    klassen_gewichtung = {
        klasse: _quantize_prozent(wert / gesamtwert * 100) for klasse, wert in klassen_werte.items()
    }
    cash_quote = klassen_gewichtung.get(CASH_ASSET_CLASS_ID, Decimal("0"))

    return PortfolioAggregat(
        branchen_gewichtung=branchen_gewichtung,
        klassen_gewichtung=klassen_gewichtung,
        cash_quote=cash_quote,
    )


def ermittle_depot_stand(positionen: Iterable[PositionsBestand]) -> DepotStand:
    """AC9: Depot-Stand (Positionen + Portfolio-Aggregate) für das
    Risikomanagement."""
    positionstupel = tuple(positionen)
    return DepotStand(
        positionen=positionstupel, aggregat=berechne_portfolio_aggregat(positionstupel)
    )


def ermittle_titel_strategie_exit_regeln(
    positionen: Iterable[PositionsBestand],
) -> list[TitelStrategieExitRegeln]:
    """AC9: je gehaltenem Titel (nicht je Lot) Strategie + Exit-Regeln für
    die Depot-Überwachung — hat ein Titel mehrere offene Lots (FIFO),
    zählt der Wert des **ersten** in `positionen` auftauchenden Lots
    (Repository liefert aufsteigend nach `opened_at`, d.h. der älteste Lot
    gewinnt, siehe `app.domain.portfolio.ports.PositionRepository
    .alle_offenen_positionen`-Docstring)."""
    ergebnis: dict[str, TitelStrategieExitRegeln] = {}
    for position in positionen:
        if position.titel_id in ergebnis:
            continue
        ergebnis[position.titel_id] = TitelStrategieExitRegeln(
            titel_id=position.titel_id,
            anlageklasse=position.asset_class_id,
            strategie=position.strategie,
            exit_regeln=position.exit_regeln,
        )
    return list(ergebnis.values())
