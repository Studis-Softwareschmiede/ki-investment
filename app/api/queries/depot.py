"""Depot-Übersicht-Query (Betriebs-Cockpit, `docs/specs/frontend-cockpit.md`
AC1/AC3/AC10, Story S-065; architecture.md §13.2/§13.7).

Read-only Query-Funktion für die Depot-View: liest ausschliesslich über
bestehende Depotmodul-Bausteine —
`app.domain.portfolio.ports.PositionRepository.alle_offenen_positionen`
(S-036, AC8/AC9) für den offenen Bestand je Titel,
`app.domain.portfolio.portfolio_aggregate.berechne_portfolio_aggregat`
(S-036, AC8) für Branchen-/Klassen-Gewichtung + Cash-Quote,
`PositionRepository.realisierter_gv_gesamt` (S-065) für den depotweiten
realisierten G/V und `app.domain.portfolio.ports.LivePriceProvider`
(Cross-Cutting Socket-Live-Kurs-Zugriff, P5) für aktuelle Kurse.

Diese Funktion bucht/entscheidet/schreibt NICHTS (Boundary-Konvention
`app/api/queries/__init__.py`, `tests/architecture/test_ui_boundary.py`
erzwingt das statisch) — reine Anzeige-Schicht (AC2). Sie wird laut
Fundament-Konvention (S-064) sowohl von der JSON-Route (`app.api.depot`)
als auch (Story S-071) von der HTML-Route (`app.api.ui`) konsumiert
(AC1/AC10, kein zweiter Datenzusammenbau).

Mehrere offene Lots desselben Titels werden je Titel aggregiert:
`menge` = Σ Lot-Mengen, `einstand_preis` = mengen-gewichteter
Ø-Einstandspreis (`Σ Lot-Wert / Σ Lot-Menge`, dieselbe Bewertungsgrundlage
wie `app.domain.portfolio.portfolio_aggregate.positionswert`),
`unrealisierter_gv` = `aggregiere_gv` über die je Lot berechneten
unrealisierten G/V (analog `app.api.dashboard`, S-054) — derselbe aktuelle
Kurs gilt für alle Lots eines Titels.

**Präzisierung (Story S-071, `docs/specs/frontend-cockpit.md` AC14):** je
Titel zusätzlich `anlageklasse` (des ältesten Lots, analog
`ermittle_titel_strategie_exit_regeln`) und `gewichtung` (Anteil an der
depotweiten Kostenbasis, dieselbe Formel wie `berechne_portfolio_aggregat`
für `klassen_gewichtung` — hier bewusst lokal nachgerechnet statt aus
`PortfolioAggregat` zurückgelesen, da diese nur je Branche/Klasse aggregiert,
nicht je Titel) sowie depotweit `portfolio_wert_kostenbasis` und
`unrealisierter_gv_gesamt` (siehe `app.contracts.depot_uebersicht`-
Docstrings für die genaue None-Semantik) — alle vier Felder sind reine
Projektionen/Summen der ohnehin gelesenen `positionen`, kein zweiter
Datenzusammenbau (AC1)."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from app.contracts.depot import Modus
from app.contracts.depot_uebersicht import (
    DepotPortfolioAggregat,
    DepotTitelBestand,
    DepotUebersichtResponse,
)
from app.domain.portfolio.portfolio_aggregate import (
    berechne_portfolio_aggregat,
    positionswert,
)
from app.domain.portfolio.ports import LivePriceProvider, PositionRepository, PositionsBestand
from app.domain.portfolio.position_booking import aggregiere_gv, berechne_unrealisierten_gv

#: Rundungsraster für die Titel-Gewichtung (NUMERIC(6,3), data-model.md
#: "Konventionen: Prozente/Scores") — kleine eigenständige Kopie von
#: `app.domain.portfolio.portfolio_aggregate._quantize_prozent` (privat,
#: kein Cross-Import, analog `_gruppiere_nach_titel` oben).
_PROZENT_QUANTUM = Decimal("0.001")


def _quantize_prozent(wert: Decimal) -> Decimal:
    return wert.quantize(_PROZENT_QUANTUM, rounding=ROUND_HALF_UP)


def _gruppiere_nach_titel(
    positionen: Iterable[PositionsBestand],
) -> dict[str, list[PositionsBestand]]:
    """Gruppiert die (lot-weise) offenen Positionen nach `titel_id`,
    Reihenfolge-stabil (Repository liefert bereits nach `titel_id`
    sortiert) — analog `app.api.dashboard._gruppiere_nach_titel` (S-054);
    hier bewusst als eigenständige, kleine Kopie statt eines
    Cross-Imports aus `app.api.dashboard`, damit die Query-Schicht
    (`app/api/queries/**`) frei von Kopplung an einen bestehenden Router
    bleibt (Boundary-Konvention, `tests/architecture/test_ui_boundary.py`)."""
    gruppiert: dict[str, list[PositionsBestand]] = {}
    for position in positionen:
        gruppiert.setdefault(position.titel_id, []).append(position)
    return gruppiert


def _baue_titel_bestand(
    titel_id: str,
    lots: list[PositionsBestand],
    *,
    live_price: LivePriceProvider,
    gesamtwert_depot: Decimal,
) -> DepotTitelBestand:
    aktueller_preis: Decimal | None = live_price.aktueller_preis(titel_id)
    menge_gesamt = sum((lot.menge for lot in lots), Decimal("0"))

    lot_wert_gesamt = sum((positionswert(lot) for lot in lots), Decimal("0"))
    einstand_preis_avg = lot_wert_gesamt / menge_gesamt if menge_gesamt != 0 else Decimal("0")

    unrealisierter_gv: Decimal | None = None
    if aktueller_preis is not None:
        unrealisierter_gv = aggregiere_gv(
            berechne_unrealisierten_gv(aktueller_preis, lot.einstand_preis, lot.menge)
            for lot in lots
        )

    gewichtung = (
        _quantize_prozent(lot_wert_gesamt / gesamtwert_depot * 100)
        if gesamtwert_depot != 0
        else Decimal("0")
    )

    return DepotTitelBestand(
        titel_id=titel_id,
        # Review-Finding Iteration 1: lesbarer Titel-Bezeichner statt der
        # rohen titel_id-UUID — analog `anlageklasse` das älteste Lot
        # (Repository liefert aufsteigend nach opened_at).
        symbol=lots[0].symbol,
        name=lots[0].name,
        menge=menge_gesamt,
        einstand_preis=einstand_preis_avg,
        aktueller_preis=aktueller_preis,
        unrealisierter_gv=unrealisierter_gv,
        # AC14: das älteste Lot repräsentiert den Titel (Repository liefert
        # aufsteigend nach opened_at, siehe `PositionRepository
        # .alle_offenen_positionen`-Docstring) — analog
        # `ermittle_titel_strategie_exit_regeln`.
        anlageklasse=lots[0].asset_class_id,
        gewichtung=gewichtung,
    )


def hole_depot_uebersicht(
    *,
    mode: Modus,
    repository: PositionRepository,
    live_price: LivePriceProvider,
) -> DepotUebersichtResponse:
    """AC3: Bestand je Titel + Portfolio-Aggregate + depotweiter
    realisierter G/V, strikt modus-isoliert (BR-130) — die einzige Stelle,
    an der diese drei Bausteine für die Depot-View zusammengeführt werden
    (AC1, kein zweiter Datenzusammenbau in HTML- vs. JSON-Route)."""
    positionen = repository.alle_offenen_positionen(mode=mode)
    aggregat = berechne_portfolio_aggregat(positionen)
    # AC14: dieselbe Kostenbasis-Bewertungsgrundlage wie `klassen_gewichtung`/
    # `cash_quote` (siehe `portfolio_aggregate`-Moduldocstring) — hier lokal
    # nachgerechnet, da `PortfolioAggregat` selbst keinen Gesamtwert liefert.
    gesamtwert_depot = sum((positionswert(p) for p in positionen), Decimal("0"))
    titel = [
        _baue_titel_bestand(
            titel_id, lots, live_price=live_price, gesamtwert_depot=gesamtwert_depot
        )
        for titel_id, lots in _gruppiere_nach_titel(positionen).items()
    ]
    realisierter_gv_gesamt = repository.realisierter_gv_gesamt(mode=mode)

    if not titel:
        # Leeres Depot: kein offener Bestand = kein Plus/Minus (bekannter
        # Fakt, nicht "nicht bewertbar") — AC14-Präzisierung.
        unrealisierter_gv_gesamt: Decimal | None = Decimal("0")
    elif any(eintrag.unrealisierter_gv is None for eintrag in titel):
        # Mindestens ein Titel ohne Live-Kurs: ein Teil-Total würde ein
        # falsches Gesamtbild vortäuschen (E2/P7) -> "nicht bewertbar".
        unrealisierter_gv_gesamt = None
    else:
        unrealisierter_gv_gesamt = aggregiere_gv(
            eintrag.unrealisierter_gv  # type: ignore[misc]
            for eintrag in titel
        )

    return DepotUebersichtResponse(
        mode=mode,
        titel=titel,
        portfolio_aggregat=DepotPortfolioAggregat(
            branchen_gewichtung=aggregat.branchen_gewichtung,
            klassen_gewichtung=aggregat.klassen_gewichtung,
            cash_quote=aggregat.cash_quote,
        ),
        realisierter_gv_gesamt=realisierter_gv_gesamt,
        portfolio_wert_kostenbasis=gesamtwert_depot,
        unrealisierter_gv_gesamt=unrealisierter_gv_gesamt,
    )
