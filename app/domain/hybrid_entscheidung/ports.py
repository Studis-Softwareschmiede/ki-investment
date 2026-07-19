"""Read-Modell-Port „Offene Entscheide" (Hybrid-Bestätigungs-Flow, Story
S-080, `docs/specs/frontend-cockpit.md` AC29; architecture.md §13.2/§13.7
"eine Query-Funktion je View liest über einen Repository-Port, kein
direkter `sqlalchemy`-Import in `app/api/queries/**`", AC2-Boundary).

`HybridEntscheidungRepository` ist bewusst read-only (nur `offene_
entscheide()`) — der Schreibpfad des Control-POSTs (AC30, "bestätigen/
ablehnen") lebt in `app.db.hybrid_entscheide` (direkter DB-Zugriff, analog
`app.db.asset_classes.setze_toggle`), NICHT hinter diesem Port: die
UI-/Query-Schicht (AC2) darf nie schreiben, die Control-Plane (`app/api/
control.py`) liegt ausserhalb der AC2-Boundary und darf `sqlalchemy`
direkt nutzen (analoges Muster zu `app.api.control` + `app.db.asset_
classes`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.contracts.depot import Richtung


@dataclass(frozen=True)
class OffenerEntscheidZeile:
    """Eine offene, bestätigungspflichtige Hybrid-Entscheid-Zeile (AC29:
    "Titel, Richtung Kauf/Verkauf, Grösse, vorgeschlagene Order,
    Frist/Ablauf, Begründung"). `titel`/`name` sind die aufgelösten
    `Instrument.symbol`/`.name`-Werte (S-066/S-071-Lehre: ein AC, das
    wörtlich "Titel" verlangt, ist nie durch eine rohe `*_id` erfüllt) —
    `None` nur bei einem Fake-Repository ohne Join-Unterstützung."""

    entscheid_id: str
    titel_id: str
    titel: str | None
    name: str | None
    richtung: Richtung
    groesse: Decimal
    vorgeschlagene_order: str
    frist: datetime
    begruendung: str
    erstellt_am: datetime


class HybridEntscheidungRepository(Protocol):
    """AC29: liefert ausschliesslich Entscheide mit `status="offen"` **und**
    `mode="simuliert"` (BR-141/AC30 MVP-Live-Sperre — ein Repository-
    Implementierer filtert beide Kriterien selbst, keine Kandidat wird an
    den Aufrufer durchgereicht, die nicht bereits offen+simuliert ist),
    sortiert nach Frist (nächster Ablauf zuerst)."""

    def offene_entscheide(self) -> list[OffenerEntscheidZeile]: ...
