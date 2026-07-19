"""Modul-Verträge Depot-Übersicht (Betriebs-Cockpit, `docs/specs/
frontend-cockpit.md` AC1/AC3/AC10, Story S-065; architecture.md §13.2/
§13.7).

Response-DTOs für `GET /api/depot` (`app.api.depot`) — generalisiert das
bestehende `GET /dashboard/depot` (`app.contracts.dashboard`, S-054, das
unverändert bestehen bleibt, Verträge-Tabelle `frontend-cockpit.md`).

AC3 wörtlich: **"Bestand je Titel (Menge, Ø-Einstand, Live-Kurs,
unrealisierter G/V), Portfolio-Aggregate (Branchen-/Klassen-Gewichtung,
Cash-Quote) und realisierten G/V; strikt modus-isoliert (→ BR-130)."**
Dieses Modul führt selbst KEINE neue Berechnung/Geschäftslogik ein — die
Query-Funktion (`app.api.queries.depot`) liest ausschliesslich über
bestehende Depotmodul-Bausteine (`PositionRepository`,
`app.domain.portfolio.portfolio_aggregate`, `LivePriceProvider`) und
bildet die Ergebnisse hier nur als Pydantic-View-DTO ab (P2).

**Präzisierung (Story S-071, AC14):** die Depot-View braucht je Titel
zusätzlich die Anlageklasse (Klassen-Chip, `design.md` §2.4) und die
Gewichtung (Datentabellen-Spalte "Gewichtung", `design.md` §7.6) sowie
depotweit den Portfolio-Wert (Kostenbasis, dieselbe Bewertungsgrundlage wie
`cash_quote`/`klassen_gewichtung`) und den aggregierten unrealisierten G/V
(KPI-Tile) — alle vier Felder sind reine Projektionen/Aggregationen der
ohnehin bereits von `hole_depot_uebersicht` gelesenen Positionen (kein
zweiter Datenzusammenbau, kein neuer Repository-/Domänen-Aufruf, AC1)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.contracts.depot import Modus


class DepotTitelBestand(BaseModel):
    """Bestand je Titel (AC3): aktuelle Gesamtmenge über alle offenen Lots,
    mengen-gewichteter Ø-Einstandspreis, aktueller Live-Kurs (`None` = kein
    Kurs verfügbar) und das daraus resultierende laufende Plus/Minus
    (`unrealisierter_gv`, über alle offenen Lots des Titels aggregiert,
    `None` = "nicht bewertbar", `frontend-cockpit.md` Edge-Cases E2).

    `anlageklasse` (AC14-Präzisierung): die Titel-repräsentierende
    Anlageklasse — bei mehreren offenen Lots desselben Titels der
    **älteste** Lot (identische Konvention zu
    `app.domain.portfolio.portfolio_aggregate
    .ermittle_titel_strategie_exit_regeln`; alle Lots eines Titels tragen
    ohnehin dieselbe `asset_class_id`, da das eine Instrument-Eigenschaft
    ist, keine Lot-Eigenschaft). `gewichtung` (AC14-Präzisierung): Anteil
    dieses Titels an der depotweiten Kostenbasis in Prozent (dieselbe
    Bewertungsgrundlage wie `DepotPortfolioAggregat.cash_quote`/
    `klassen_gewichtung`, NUMERIC(6,3)-Rundung).

    `symbol`/`name` (Story S-071, Review-Finding Iteration 1): lesbarer
    Titel-Bezeichner (`Instrument.symbol`/`.name` des ältesten Lots, analog
    `anlageklasse`) für die Datentabellen-Spalte "Titel" — `None`, falls
    das Repository sie nicht liefert (Test-Fakes ohne Instrument-Daten),
    das Template fällt dann auf `titel_id` zurück."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str
    symbol: str | None = None
    name: str | None = None
    menge: Decimal
    einstand_preis: Decimal
    aktueller_preis: Decimal | None
    unrealisierter_gv: Decimal | None
    anlageklasse: int
    gewichtung: Decimal


class DepotPortfolioAggregat(BaseModel):
    """Portfolio-Aggregate (AC3) — bildet `app.domain.portfolio
    .portfolio_aggregate.PortfolioAggregat` 1:1 als View-DTO ab: Gewichtung
    je GICS-Branche, Gewichtung je Anlageklasse und die Cash-Quote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    branchen_gewichtung: dict[str, Decimal]
    klassen_gewichtung: dict[int, Decimal]
    cash_quote: Decimal


class DepotUebersichtResponse(BaseModel):
    """Antwort von `GET /api/depot` (AC3) — je Modus (echt/simuliert,
    Mode-Isolation BR-130) Bestand je Titel, Portfolio-Aggregate und der
    depotweite realisierte G/V.

    `portfolio_wert_kostenbasis` (AC14-Präzisierung): depotweite
    Kostenbasis (Σ `menge × einstand_preis` über alle offenen Positionen,
    bewusst **keine** Live-Kurs-Bewertung — dieselbe Bewertungsgrundlage
    wie `portfolio_aggregat.cash_quote`/`klassen_gewichtung`, siehe
    `app.domain.portfolio.portfolio_aggregate`-Moduldocstring "keine
    Live-Kurs-Abfrage: die Aggregation ist reproduzierbar"). Für ein leeres
    Depot `Decimal("0")`. `unrealisierter_gv_gesamt` (AC14-Präzisierung):
    Summe von `titel[].unrealisierter_gv` — `Decimal("0")` bei leerem
    Depot (kein offener Bestand = kein Plus/Minus, ein bekannter Fakt),
    aber `None` ("nicht bewertbar", E2), sobald **mindestens ein** Titel
    keinen Live-Kurs hat (ein Teil-Total würde sonst ein falsches
    Gesamtbild vortäuschen, P7-Genauigkeitsgebot)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Modus
    titel: list[DepotTitelBestand]
    portfolio_aggregat: DepotPortfolioAggregat
    realisierter_gv_gesamt: Decimal
    portfolio_wert_kostenbasis: Decimal
    unrealisierter_gv_gesamt: Decimal | None
