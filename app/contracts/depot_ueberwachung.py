"""Modul-Verträge Depot-Überwachung — Monitoring-Zyklus (Story S-032,
Spec `docs/specs/depot-ueberwachung.md`, architecture.md §2 P2).

Deckt AC1 (Input-Vollständigkeit, "unvollständig protokolliert") und AC9
(Frische-Fenster, "nicht bewertbar protokolliert", deckt E1) — die
gemeinsame Protokoll-Form für beide "nicht stillschweigend übersprungen"-
Fälle der S-032-Story.

**Story S-033 (AC4-AC7)** ergänzt die Verträge für Main-Success-Scenario
Schritte 4-6 (Keyword-/Ereignis-Filter, Marktkontext-Normierung,
Ereignis-Erzeugung + Alert-Fatigue-Kennzahl):

- `RohNewsEreignis` (AC4-Input) + `TitelSignalRohdaten` (AC4-AC6-Input,
  bündelt News + die je Titel zu prüfenden numerischen Rohsignale) —
  **Cold-Start-Verträge**: es existiert noch kein News-Text-Adapter/
  Markt-Referenz-Adapter, der sie befüllt (kein Socket liefert aktuell
  Freitext oder einen Marktindex-Referenzwert, siehe
  `app.contracts.dateneingang.Datenpunkt`/`Signal` — beide tragen nur
  quantifizierte Einzelwerte). Analog `ExitRegelnBestand` (S-032): die
  konsumierende Logik (`app.domain.depot_ueberwachung.ereignis_filter`,
  `.marktkontext`, `.ereignis_erzeugung`) ist unabhängig davon bereits
  vollständig korrekt und getestet — ein künftiger Adapter befüllt diese
  Verträge, ohne sie zu ändern.
- `UeberwachungsEreignis` (AC6, Verträge "Output (Überwachungs-Ereignis)"):
  `{ titel_id, ereignistyp, rohwerte, zeitstempel, quellen_id }`.
- `MonitoringTagesKennzahl` (AC7, Verträge "Monitoring-Kennzahl"):
  `ereignisse_pro_tag` (Zählwert) + Flag `zu_sensibel`.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Protokoll-Gründe (AC1 "unvollständig" / AC9 "nicht bewertbar", deckt E1).
MonitoringProtokollGrund = Literal["unvollstaendig", "nicht_bewertbar", "marktkontext_fallback"]


class MonitoringProtokollEintrag(BaseModel):
    """Auditierbarer Protokolleintrag für einen Titel, der in einem
    Monitoring-Zyklus NICHT weiterverarbeitet wird (AC1: "wird der Titel
    als unvollständig protokolliert und nicht stillschweigend
    übersprungen"; AC9/E1: "wird der Titel als 'nicht bewertbar' markiert
    und protokolliert; es wird kein Ereignis fabriziert"). Enthält bewusst
    keine Rohdaten/Secrets — nur die für die Auditierung nötigen
    strukturierten Felder (analog `app.contracts.depot.FillProtokollEintrag`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    zeitpunkt: datetime
    titel_id: str
    grund: MonitoringProtokollGrund
    detail: str


#: Ereignistyp (AC6, Verträge "Output (Überwachungs-Ereignis)") — deckt
#: sich bewusst 1:1 mit den Namen aus
#: `app.domain.depot_ueberwachung.ueberwachte_groessen`
#: (`UEBERWACHTE_GROESSEN_STANDARD`/`_KRYPTO_ZUSATZ`, AC3), nur im Singular
#: für "news_katalysatoren" -> "news_katalysator" und
#: "on_chain_abfluesse" -> "on_chain_abfluss" (ein Ereignis, keine Menge).
Ereignistyp = Literal[
    "news_katalysator",
    "relativer_kurssturz",
    "sentiment_kippen",
    "momentum_verlust",
    "on_chain_abfluss",
]

#: Default-Auslöser-Menge des Keyword-/Ereignis-Filters (AC4: "Default-
#: Auslöser-Menge (provisorisch, konfigurierbar)").
DEFAULT_EREIGNIS_KEYWORDS: tuple[str, ...] = (
    "Insolvenz",
    "Hack",
    "Übernahme",
    "Gewinnwarnung",
    "Downgrade",
)

#: Provisorische, je Ereignistyp EINHEITLICHE (nicht Anlageklassen-
#: differenzierte) Default-Schwellen (Verträge "Konfiguration:
#: Ereignistyp-Schwellen je Anlageklasse" — konkrete Werte sind laut Spec
#: offen/provisorisch; eine Anlageklassen-Differenzierung ist eine
#: mögliche Folge-Kalibrierung, analog `app.config.DEFAULT_TOLERANZEN`).
#: `relativer_kurssturz` ist die marktkontext-normierte Übertreibung ggü.
#: dem Markt (AC5, Anteil, `0.05` = 5 Prozentpunkte Übertreibung); die
#: übrigen drei sind dimensionslose Signal-Beträge (grösser = stärker
#: ausgeprägtes Warnsignal).
DEFAULT_EREIGNIS_SCHWELLEN: dict[str, Decimal] = {
    "relativer_kurssturz": Decimal("0.05"),
    "sentiment_kippen": Decimal("0.5"),
    "momentum_verlust": Decimal("0.5"),
    "on_chain_abfluss": Decimal("0.5"),
}


class RohNewsEreignis(BaseModel):
    """Ungefilterte, rohe News-Meldung zu einem gehaltenen Titel (AC4-
    Input) — Cold-Start-Vertrag, siehe Moduldocstring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    quelle: str = Field(min_length=1)
    beobachtet_am: datetime


class TitelSignalRohdaten(BaseModel):
    """Rohdaten-Eingang für die Ereignis-Auswertung EINES Titels in einem
    Monitoring-Zyklus (AC4-AC6-Input) — Cold-Start-Vertrag, siehe
    Moduldocstring. `quelle` ist die Herkunfts-Kennung, die numerische
    Ereignisse als `quellen_id` tragen (Default `"signal_buendel"` — die
    aggregierte Datenquellen-Abfrage aus S-032/S-021, solange keine
    einzelne beitragende Quelle unterschieden wird)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    quelle: str = Field(min_length=1, default="signal_buendel")
    news: tuple[RohNewsEreignis, ...] = Field(default=())
    kursbewegung: Decimal | None = None
    marktbewegung: Decimal | None = None
    sentiment_wert: Decimal | None = None
    momentum_wert: Decimal | None = None
    on_chain_abfluss_wert: Decimal | None = None


class UeberwachungsEreignis(BaseModel):
    """Output-Vertrag AC6 (Verträge "Output (Überwachungs-Ereignis, an
    [[analyse-pipelines]] / Analyse bestehende Titel)"): `{ titel_id,
    ereignistyp, rohwerte, zeitstempel, quellen_id }`. `rohwerte` sind die
    auslösenden Rohwerte als Audit-Trail — Decimal-Werte werden als `str`
    gehalten (verlustfrei, kein Float-Rundungsrisiko, analog
    `MonitoringProtokollEintrag.detail`).

    Die tatsächliche "Weitergabe" an die Analyse bestehender Titel
    (`[[analyse-pipelines]]`, Sell-Pfad) ist noch nicht gebaut (spätere
    Story, siehe `app.contracts.analyse_pipelines`-Moduldocstring "Der
    Sell-Pfad ... hat KEIN Gegenstück in diesem Modul") — dieses DTO ist
    der vollständige, testbare Output, den diese Story liefert (analog
    `BuySignal`, das auf das noch nicht gebaute Position-Sizing wartet)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    ereignistyp: Ereignistyp
    rohwerte: dict[str, str] = Field(default_factory=dict)
    zeitstempel: datetime
    quellen_id: str = Field(min_length=1)


class MonitoringTagesKennzahl(BaseModel):
    """Monitoring-Kennzahl (AC7, Verträge "Monitoring-Kennzahl"):
    `ereignisse_pro_tag` (Zählwert) + Flag `zu_sensibel` bei
    Überschreitung des konfigurierten Schwellwerts (Default 10, STRIKT
    `>`, Edge-Case "genau am Schwellwert -> kein Alarm", analog
    `app.core.hallucination_kpi`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    datum: date
    ereignisse_pro_tag: int = Field(ge=0)
    schwellwert: int = Field(ge=0)
    zu_sensibel: bool


__all__ = [
    "DEFAULT_EREIGNIS_KEYWORDS",
    "DEFAULT_EREIGNIS_SCHWELLEN",
    "Ereignistyp",
    "MonitoringProtokollEintrag",
    "MonitoringProtokollGrund",
    "MonitoringTagesKennzahl",
    "RohNewsEreignis",
    "TitelSignalRohdaten",
    "UeberwachungsEreignis",
]
