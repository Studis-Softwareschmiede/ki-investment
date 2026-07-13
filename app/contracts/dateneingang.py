"""Modul-Verträge Socket → Datenquellen-Abfrage: interner Datenpunkt +
geteilte Datenquellen-Abfrage (Signal-Bündel).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet zwei
Verträge aus `docs/specs/dateneingang.md` ab:

- **Interner Datenpunkt (Socket-Output, AC1/AC2):** `{ wert(e), quelle,
  timestamp, anlageklassen_tag: 1..11, qualitaetsindikator }`, einheitlich
  über alle Quellen. Alle vier Metadaten-Felder sind Pflicht (AC2): fehlt
  eines oder liegt `anlageklassen_tag` ausserhalb 1..11, verweigert pydantic
  die Instanziierung (`ValidationError`) — der Adapter
  (`app.adapters.sockets.base.SocketAdapter.fetch`) verwirft den Kandidaten
  dann, statt ihn zu schätzen oder mit einem Default aufzufüllen.

- **Datenquellen-Abfrage (AC7/AC8, "eine Schnittstelle, drei Konsumenten"):**
  Input `SignalBuendelAnfrage` (Titel-Anfragen inkl. Anlageklasse +
  Konsumenten-Kontext neu/bestehend/research), Output `list[SignalBuendel]`
  (`{ titel, anlageklasse, signale[...], liquiditaet, volatilitaet,
  quellen_metadaten[...] }` je Titel-Anfrage). Die Aggregationslogik selbst
  lebt in `app.orchestration.datasource_query` (Modul 2) — dieses Modul
  bildet nur die typisierten Verträge (P2).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

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


#: Konsumenten-Kontext der geteilten Datenquellen-Abfrage (Vertrag
#: "Datenquellen-Abfrage", AC7): genau die drei in der Spec genannten
#: Konsumenten — Suchkriteria (neu), Depot-Suchkriterien (bestehend),
#: Research. Ein ungültiger Wert verweigert pydantic die Instanziierung von
#: `SignalBuendelAnfrage` (kein vierter, stillschweigend akzeptierter Kontext).
KonsumentenKontext = Literal["neu", "bestehend", "research"]


class TitelAnfrage(BaseModel):
    """Ein Titel/Anlageklasse-Paar innerhalb einer `SignalBuendelAnfrage`
    (Vertrag "Datenquellen-Abfrage", AC7/AC8: Input "Filterkriterien /
    Titel-Anfrage inkl. Anlageklasse"). `anlageklasse` steuert die
    Quellen-Auswahl aus der Registry (AC8)."""

    model_config = ConfigDict(frozen=True)

    titel: str = Field(min_length=1)
    anlageklasse: int = Field(ge=1, le=11)


class SignalBuendelAnfrage(BaseModel):
    """Input der geteilten Datenquellen-Abfrage (AC7): eine oder mehrere
    Titel-Anfragen inkl. Anlageklasse + der Konsumenten-Kontext (neu /
    bestehend / research). Alle drei Konsumenten (Suchkriteria,
    Depot-Suchkriterien, Research) senden denselben DTO-Typ an dieselbe
    Schnittstelle (`app.orchestration.datasource_query.hole_signal_buendel`)
    — keine parallele Zweit-Implementierung je Konsument."""

    model_config = ConfigDict(frozen=True)

    titel_anfragen: list[TitelAnfrage] = Field(min_length=1)
    konsumenten_kontext: KonsumentenKontext


class Signal(BaseModel):
    """Ein einzelner aggregierter Signalwert innerhalb eines Signal-Bündels
    (Vertragsfeld `signale[...]`) — stammt aus genau einer, anhand der
    Anlageklasse aus der Registry ausgewählten Quelle (AC8)."""

    model_config = ConfigDict(frozen=True)

    quelle: str
    wert: Decimal
    qualitaetsindikator: str | None
    beobachtet_am: datetime


class QuellenMetadatum(BaseModel):
    """Metadatum zu genau einer an einem Signal-Bündel beteiligten Quelle
    (Vertragsfeld `quellen_metadaten[...]`) — Transparenz, welche
    Registry-Quellen zur Aggregation herangezogen wurden und wie aktuell ihr
    Beitrag ist."""

    model_config = ConfigDict(frozen=True)

    data_source_id: uuid.UUID
    name: str
    kategorie: str | None
    beobachtet_am: datetime | None


class SignalBuendel(BaseModel):
    """Output je Titel-Anfrage der geteilten Datenquellen-Abfrage (AC8,
    Vertrag "Datenquellen-Abfrage"): `{ titel, anlageklasse, signale[...],
    liquiditaet, volatilitaet, quellen_metadaten[...] }`.

    `liquiditaet`/`volatilitaet` sind `None`, wenn für die Anlageklasse des
    Titels keine passende Quelle in der Registry aggregierbare Daten liefert
    (leeres `signale`) — kein geschätzter Platzhalterwert (analog AC2-Prinzip
    "nicht schätzen, sondern als fehlend kennzeichnen"). Die konkrete
    Berechnungsmethode ist ein provisorischer Default, siehe
    `app.orchestration.datasource_query`.
    """

    model_config = ConfigDict(frozen=True)

    titel: str
    anlageklasse: int = Field(ge=1, le=11)
    signale: list[Signal]
    liquiditaet: Decimal | None
    volatilitaet: Decimal | None
    quellen_metadaten: list[QuellenMetadatum]
