"""Modul-Verträge Depot-Verlauf (Betriebs-Cockpit, `docs/specs/
frontend-cockpit.md` AC32/AC33, Story S-081; architecture.md §13.2/§13.7).

Response-DTOs für `GET /api/depot/verlauf` (`app.api.depot_verlauf`) —
Verträge-Tabelle `frontend-cockpit.md`: "Portfolio-Wert-Zeitreihe
(Zeitpunkt, Modus, Wert, optional Cash/Klassen-Split)". Dieses Modul führt
selbst KEINE neue Berechnung ein — die Query-Funktion
(`app.api.queries.depot_verlauf`) liest ausschliesslich über
`app.domain.portfolio_verlauf.ports.PortfolioSnapshotRepository` und
bildet das Ergebnis hier nur als Pydantic-View-DTO ab (P2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.contracts.depot import Modus


class DepotVerlaufEintrag(BaseModel):
    """Ein Zeitreihen-Punkt (AC32): Zeitpunkt, Portfolio-Wert (CHF,
    Ø-Einstand-Fallback ohne Live-Kurs, siehe `app.scheduler
    .portfolio_snapshot_job`-Moduldocstring) und Cash-Quote (%, optionales
    Zusatzfeld laut AC32 wörtlich, hier stets gesetzt)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    zeitpunkt: datetime
    portfolio_wert: Decimal
    cash_quote: Decimal


class DepotVerlaufResponse(BaseModel):
    """Antwort von `GET /api/depot/verlauf` (AC32) — die Portfolio-Wert-
    Zeitreihe im angegebenen `mode` (Mode-Isolation, → BR-130). Leere
    `eintraege`-Liste, falls (noch) keine Snapshot-Historie existiert
    (AC32-Edge-Case, deckt E2-Muster — kein Fehler, kein Fake-Wert)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Modus
    eintraege: list[DepotVerlaufEintrag]
