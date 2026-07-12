"""Modul-Vertrag Socket → Datenquellen-Abfrage: interner Datenpunkt.

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet den
Vertrag aus `docs/specs/dateneingang.md` ("Verträge — Interner Datenpunkt
(Socket-Output)") ab: `{ wert(e), quelle, timestamp,
anlageklassen_tag: 1..11, qualitaetsindikator }`, einheitlich über alle
Quellen (AC1).

Alle vier Metadaten-Felder (quelle, timestamp, anlageklassen_tag,
qualitaetsindikator) sind Pflicht (AC2): fehlt eines oder liegt
`anlageklassen_tag` ausserhalb 1..11, verweigert pydantic die
Instanziierung (`ValidationError`) — der Adapter (`app.adapters.sockets.base
.SocketAdapter.fetch`) verwirft den Kandidaten dann, statt ihn zu schätzen
oder mit einem Default aufzufüllen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Datenpunkt(BaseModel):
    """Einheitlicher interner Socket-Datenpunkt (Vertrag, Spec `dateneingang`).

    Jede Quelle liefert nach der Adapter-Normalisierung exakt diese Form —
    unabhängig von der quellenspezifischen Rohantwort. Konsumenten erhalten
    dadurch quellen-unabhängig identisch strukturierte Datensätze (AC1).
    """

    model_config = ConfigDict(frozen=True)

    # `wert: Any` lässt bewusst auch `None` zu (z.B. Quelle liefert einen
    # expliziten Nullwert) — die Gültigkeit des Datenpunkts entscheidet sich
    # nicht am Wert, sondern an den Pflicht-Metadaten, insbesondere am
    # `qualitaetsindikator` (AC2).
    wert: Any
    quelle: str = Field(min_length=1)
    timestamp: datetime
    anlageklassen_tag: int = Field(ge=1, le=11)
    qualitaetsindikator: str = Field(min_length=1)
