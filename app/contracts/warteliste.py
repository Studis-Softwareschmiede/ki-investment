"""Modul-Vertrag Warteliste-View (Betriebs-Cockpit, `docs/specs/
frontend-cockpit.md` AC26, Story S-079; architecture.md §13.2/§13.7 "eine
Query-Funktion je View liefert ein Pydantic-View-DTO").

`WartelisteEintragResponse` bildet AC26 wörtlich ab ("Titel, Anlageklasse,
geplante Grösse, Blockade-Grund ... und Zeitpunkt") — reines
Response-DTO, 1:1 aus `app.domain.warteliste.ports.WartelisteEintrag`,
keine neue Geschäftslogik (P3)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.contracts.depot import Modus

BlockadeGrund = Literal["klumpenrisiko", "korrelation", "drawdown", "kelly_cap"]


class WartelisteEintragResponse(BaseModel):
    """Ein Eintrag der Warteliste (AC26)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    titel_id: str
    titel: str
    name: str
    asset_class_id: int
    geplante_groesse: Decimal
    blockade_grund: BlockadeGrund
    blockiert_am: datetime


class WartelisteResponse(BaseModel):
    """Antwort von `GET /api/warteliste` (AC26) — je Modus (echt/simuliert,
    Mode-Isolation BR-130) die Warteliste blockierter Kauf-Kandidaten,
    neueste zuerst."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Modus
    eintraege: list[WartelisteEintragResponse]
