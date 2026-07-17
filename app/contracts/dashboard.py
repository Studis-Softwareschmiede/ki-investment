"""Modul-Verträge Depot-Dashboard (Anzeige-/Reporting-Schicht, `docs/specs/
depot.md` AC11, Story S-054, architecture.md §4 `app/api/dashboard.py`).

Reine Response-DTOs für den Dashboard-Endpunkt (`app.api.dashboard`) —
bilden AC11 wörtlich ab: **"Depot live, je Titel Kauf-Historie und
laufendes Plus/Minus"**. Beide Werte kommen ausschliesslich aus bereits
bestehenden Depotmodul-Bausteinen (`app.domain.portfolio.ports
.PositionRepository`, `app.domain.portfolio.position_booking
.berechne_unrealisierten_gv`/`aggregiere_gv`) — dieses Modul führt selbst
KEINE neue Berechnung/Geschäftslogik ein (P3, "reine Anzeige-Schicht ...
verändert weder Bestand noch Trading-Logik").

`unrealisierter_gv_gesamt: None` heisst gemäss `depot.md` Edge-Cases
"nicht bewertbar" (kein aktueller Live-Kurs verfügbar, `app.domain.portfolio
.ports.LivePriceProvider` liefert `None`) — kein Fehler."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.contracts.depot import Modus


class KaufHistorieEintrag(BaseModel):
    """Ein einzelner Kauf-Eintrag aus der append-only Transaktionshistorie
    (AC11 "je Titel Kauf-Historie") — Teilmenge von `app.domain.portfolio
    .ports.TransaktionsEintrag`, gefiltert auf `richtung == "kauf"`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_id: str
    menge: Decimal
    fill_preis: Decimal
    kosten: Decimal
    zeitstempel: datetime


class TitelDashboardEintrag(BaseModel):
    """Depot-live-Sicht auf einen gehaltenen Titel (AC11): aktuelle Menge,
    aktueller Live-Kurs (`None` = kein Kurs verfügbar), laufendes
    Plus/Minus (`unrealisierter_gv_gesamt`, über alle offenen Lots des
    Titels aggregiert per `aggregiere_gv`, `None` = "nicht bewertbar") und
    die Kauf-Historie."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str
    menge_gesamt: Decimal
    aktueller_preis: Decimal | None
    unrealisierter_gv_gesamt: Decimal | None
    kauf_historie: list[KaufHistorieEintrag]


class DepotDashboardResponse(BaseModel):
    """Antwort des Depot-Dashboard-Endpunkts (AC11) — je Modus (echt/
    simuliert, Mode-Isolation BR-130) eine Liste von `TitelDashboardEintrag`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Modus
    titel: list[TitelDashboardEintrag]
