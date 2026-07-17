"""Modul-Verträge Depot-Überwachung — Monitoring-Zyklus (Story S-032,
Spec `docs/specs/depot-ueberwachung.md`, architecture.md §2 P2).

Deckt AC1 (Input-Vollständigkeit, "unvollständig protokolliert") und AC9
(Frische-Fenster, "nicht bewertbar protokolliert", deckt E1) — die
gemeinsame Protokoll-Form für beide "nicht stillschweigend übersprungen"-
Fälle dieser Story. NICHT Teil dieses Vertrags: die Ereignis-Erzeugung/
-Weitergabe an die Analyse bestehender Titel (AC6/AC7, Folge-Story) — dort
lebt ein eigener, noch zu bauender Vertrag (`{ titel_id, ereignistyp,
rohwerte, zeitstempel, quellen_id }`, Verträge "Output (Überwachungs-
Ereignis)").
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

#: Protokoll-Gründe (AC1 "unvollständig" / AC9 "nicht bewertbar", deckt E1).
MonitoringProtokollGrund = Literal["unvollstaendig", "nicht_bewertbar"]


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


__all__ = ["MonitoringProtokollEintrag", "MonitoringProtokollGrund"]
