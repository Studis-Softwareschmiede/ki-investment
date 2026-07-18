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
bildet die Ergebnisse hier nur als Pydantic-View-DTO ab (P2)."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.contracts.depot import Modus


class DepotTitelBestand(BaseModel):
    """Bestand je Titel (AC3): aktuelle Gesamtmenge über alle offenen Lots,
    mengen-gewichteter Ø-Einstandspreis, aktueller Live-Kurs (`None` = kein
    Kurs verfügbar) und das daraus resultierende laufende Plus/Minus
    (`unrealisierter_gv`, über alle offenen Lots des Titels aggregiert,
    `None` = "nicht bewertbar", `frontend-cockpit.md` Edge-Cases E2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str
    menge: Decimal
    einstand_preis: Decimal
    aktueller_preis: Decimal | None
    unrealisierter_gv: Decimal | None


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
    depotweite realisierte G/V."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Modus
    titel: list[DepotTitelBestand]
    portfolio_aggregat: DepotPortfolioAggregat
    realisierter_gv_gesamt: Decimal
