"""Modul-Verträge Kandidaten-Cockpit-Endpunkte (Anzeige-/Reporting-Schicht,
`docs/specs/frontend-cockpit.md` AC4/AC5, Story S-066, architecture.md §4
`app/api/kandidaten.py`).

Reine Response-DTOs für die Kandidaten-Endpunkte (`app.api.kandidaten`) —
bilden AC4 ("Liste bewerteter Kandidaten: Titel, Anlageklasse, Gesamtscore,
Signal, 5 Kategorie-Scores, `as_of`") und AC5 ("Kategorie-Fakten inkl.
Quellen-ID + Timestamp, Begründung, Sanity-Cap-Status") wörtlich ab. Beide
Routen konsumieren ausschliesslich `app.api.queries.kandidaten` (P4/DRY,
AC1/AC10) — dieses Modul führt selbst KEINE Berechnung ein.

`titel`/`name` (S-066 Iteration 2, Review-Fund): der menschenlesbare Titel
(`Instrument.symbol`/`.name`) — `titel_id` bleibt zusätzlich die rohe
`instrument_id` (z.B. für den Detail-Link).

`sanity_cap_angewendet` auf `KandidatUebersichtResponse` (S-072
Iteration 2, Review-Fund): `docs/design.md` §7.7 verlangt den Zusatz-
Marker + das `data-sanity-capped`-Attribut bereits auf dem Signal-Badge
der Kandidaten-TABELLE (AC15), nicht erst im Detail-Panel — additive
Erweiterung, 1:1 aus dem Read-Modell (→ BR-008)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.contracts.analyse_framework import KategorieScores, Signal


class KandidatUebersichtResponse(BaseModel):
    """Ein Eintrag der Kandidaten-Übersicht (AC4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_result_id: str
    titel_id: str
    titel: str
    name: str
    asset_class_id: int
    gesamtscore: float
    signal: Signal
    kategorie_scores: KategorieScores
    as_of: datetime
    sanity_cap_angewendet: bool


class KandidatFaktResponse(BaseModel):
    """Eine einzelne geerdete Kennzahl der Detail-Sicht (AC5) — Quellen-ID
    + Timestamp sind Pflicht (→ BR-002/BR-107)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kennzahl: str
    wert: Decimal
    quellen_id: str
    zeitstempel: datetime


class KandidatDetailResponse(BaseModel):
    """Detail-Sicht auf eine einzelne Analyse (AC5). `gesamtscore`/`signal`
    sind `None`, wenn die Analyse wegen fehlender Evidenz einer Kategorie
    übersprungen wurde (No-Evidence-No-Trade, deckt E3, → BR-005) — die
    fehlende Kategorie ist in `kategorie_scores` als `None` ausgewiesen,
    nie geschätzt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_result_id: str
    titel_id: str
    titel: str
    name: str
    asset_class_id: int
    gesamtscore: float | None
    signal: Signal | None
    kategorie_scores: KategorieScores
    sanity_cap_angewendet: bool
    begruendung: str | None
    fakten: list[KandidatFaktResponse]
    as_of: datetime
