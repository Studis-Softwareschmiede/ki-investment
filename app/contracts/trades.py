"""Modul-Verträge Trade-Historie-View (Betriebs-Cockpit, `docs/specs/
frontend-cockpit.md` AC6/AC7, Story S-067; architecture.md §13.2/§13.7
"eine Query-Funktion je View liefert ein Pydantic-View-DTO").

`TradeHistorieEintrag` bildet AC6 wörtlich ab ("Titel, Richtung, Menge,
Fill-Preis, Arrival-Price, Slippage/TCA, Kosten, FX-Split, Zeit") — reine
Response-DTOs, keine neue Geschäftslogik (P3): jedes Feld kommt 1:1 aus
`app.domain.portfolio.ports.TransaktionsEintrag` (S-035/S-053), das die
depotweite Query-Funktion (`app.api.queries.trades.hole_trade_historie`)
über `PositionRepository.historie_depotweit` (AC7-Gap-Schluss, S-067)
liest."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.contracts.depot import Modus, Richtung


class TradeHistorieEintrag(BaseModel):
    """Ein einzelner Trade der depotweiten, append-only Transaktionshistorie
    (AC6) — Slippage/TCA (`slippage` = Fill-Preis − Arrival-Price, AC7) und
    FX-Split (`fx_rate`/`kapital_gv_chf`/`waehrungs_gv_chf`, S-053/AC6, alle
    `None` bei CHF oder Kauf) sind bereits in `TransaktionsEintrag` fertig
    berechnet — dieses DTO reicht sie unverändert weiter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_id: str
    titel_id: str
    richtung: Richtung
    menge: Decimal
    fill_preis: Decimal
    arrival_price: Decimal
    slippage: Decimal
    kosten: Decimal
    waehrung: str
    zeitstempel: datetime
    #: FX-Split (S-053, → BR-129) — `None` bei CHF oder Kauf.
    fx_rate: Decimal | None = None
    kapital_gv_chf: Decimal | None = None
    waehrungs_gv_chf: Decimal | None = None


class TradesResponse(BaseModel):
    """Antwort von `GET /api/trades` (AC6) — je Modus (echt/simuliert,
    Mode-Isolation BR-130) die (optional nach Titel/Zeitraum gefilterte)
    depotweite Trade-Liste, aufsteigend nach `zeitstempel` sortiert."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Modus
    trades: list[TradeHistorieEintrag]
