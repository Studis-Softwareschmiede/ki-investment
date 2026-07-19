"""Modul-Verträge Offene-Entscheide-Read-Modell + Control-Antwort (Story
S-080, `docs/specs/frontend-cockpit.md` AC29/AC30/AC31; architecture.md
§13.2/§13.7 "eine Query-Funktion je View liefert ein Pydantic-View-DTO").

`OffenerEntscheidResponse` bildet AC29 wörtlich ab ("Titel, Richtung
Kauf/Verkauf, Grösse, vorgeschlagene Order, Frist/Ablauf, Begründung") —
reines Response-DTO, keine neue Geschäftslogik (P3). `OffeneEntscheideResponse
.feature_aktiv` transportiert AC31 (Feature-Gate-Zustand) direkt im
Response-Body, damit HTML- **und** JSON-Konsument denselben definierten
"autonom — keine offenen Entscheide"-Zustand erkennen können, ohne den
Konfig-Wert selbst nochmal abzufragen.

`EntscheidStatusResponse` ist die schlanke Antwort der Control-POSTs
(AC30 "bestätigen"/"ablehnen") — bewusst OHNE die vollen AC29-Felder
(Titel/Grösse/…): der Aufrufer kennt den Entscheid bereits (er hat gerade
den Dialog dafür bestätigt), die Antwort bestätigt nur den neuen
Zustand."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.contracts.depot import Richtung


class OffenerEntscheidResponse(BaseModel):
    """Ein einzelner offener, bestätigungspflichtiger Hybrid-Entscheid
    (AC29). `titel`/`name` sind die aufgelösten `Instrument.symbol`/`.name`
    -Werte (S-066/S-071-Lehre) — `None` nur bei einer Quelle ohne
    Join-Unterstützung (nie bei einem echten Read über die Datenbank)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entscheid_id: str
    titel_id: str
    titel: str | None = None
    name: str | None = None
    richtung: Richtung
    groesse: Decimal
    vorgeschlagene_order: str
    frist: datetime
    begruendung: str
    erstellt_am: datetime


class OffeneEntscheideResponse(BaseModel):
    """Antwort von `GET /api/entscheide/offen` (AC29) — `feature_aktiv`
    transportiert den AC31-Feature-Gate-Zustand: ist er `false`, ist
    `entscheide` IMMER leer (unabhängig vom DB-Inhalt, Default-aus-
    Invariante)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_aktiv: bool
    entscheide: list[OffenerEntscheidResponse]


class EntscheidStatusResponse(BaseModel):
    """Antwort der Control-POSTs `POST /api/control/entscheide/{id}/
    bestaetigen`/`.../ablehnen` (AC30) — der neue, persistierte Zustand."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entscheid_id: str
    status: Literal["bestaetigt", "abgelehnt"]
    entschieden_am: datetime
