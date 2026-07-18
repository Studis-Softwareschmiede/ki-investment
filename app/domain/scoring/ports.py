"""Repository-Port für das Kandidaten-Analyse-Read-Modell (architecture.md
§4: "abstrakte Protokolle in `app/domain/**/ports.py`", P1; Story S-066,
`docs/specs/frontend-cockpit.md` AC4/AC5/AC7).

Schliesst den in `architecture.md` §13.3-Fussnote benannten Read-Modell-Gap
strukturell: die reine Berechnungsschicht (`app.domain.scoring.score_engine`)
kennt keine Persistenz — dieser Port ist die Lese-Grenze zwischen der
Query-Schicht (`app.api.queries.kandidaten`, darf laut `tests/architecture/
test_ui_boundary.py` kein `sqlalchemy` importieren) und der konkreten
Implementierung (`app.adapters.repositories.analysis_result_repository
.SqlAlchemyKandidatenRepository`), analog zu `app.domain.portfolio.ports
.PositionRepository`.

`KandidatUebersicht` (AC4, `GET /api/kandidaten`): nur vollständig
bewertete Analysen (`gesamtscore`/`signal` gesetzt) — eine wegen fehlender
Evidenz übersprungene Analyse (No-Evidence-No-Trade, → BR-108) erscheint
NICHT in dieser Liste ("Liste bewerteter Kandidaten", AC4 wörtlich).

`KandidatDetail` (AC5, `GET /api/kandidaten/{id}`): liefert JEDE Analyse,
auch eine übersprungene (`gesamtscore`/`signal` dann `None`) — die fehlende
Kategorie wird über `kategorie_scores` (Kategorie ohne Score → `None`) als
fehlend ausgewiesen statt geschätzt (deckt E3, → BR-005).

**S-066 Iteration 2 (Review-Fund, Critical):** AC4/AC5 verlangen den
menschenlesbaren **Titel**, nicht nur die `instrument_id` — `titel` (=
`Instrument.symbol`) und `name` (= `Instrument.name`) ergänzen `titel_id`
(bleibt die rohe `instrument_id`, z.B. für den Detail-Link) um die
Anzeige-Werte; beide stammen 1:1 aus `Instrument`, keine neue Berechnung.

**S-072 Iteration 2 (Review-Fund, Important):** `docs/design.md` §7.7
verlangt bei aktivem Sanity-Cap (BR-008) einen Zusatz-Marker + das
`data-sanity-capped`-Anker-Attribut **auf dem Signal-Badge der
Kandidaten-Tabelle** (nicht nur im Detail-Panel) — `KandidatUebersicht`
trägt dafür `sanity_cap_angewendet` additiv (1:1 aus `AnalysisResult
.sanity_cap_applied`, keine neue Berechnung, analog `KandidatDetail`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.contracts.analyse_framework import KategorieScores, Signal


@dataclass(frozen=True)
class KandidatUebersicht:
    """Ein Eintrag der Kandidaten-Übersicht (AC4): Titel, Anlageklasse,
    Gesamtscore, abgeleitetes Signal (→ BR-007), die 5 Kategorie-Scores
    (Spinnennetz-Achsen, C-007), `as_of` (Analyse-Zeitpunkt) und der
    Sanity-Cap-Status (S-072 Iteration 2, → BR-008, design.md §7.7)."""

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


@dataclass(frozen=True)
class KandidatFakt:
    """Eine einzelne geerdete Kennzahl einer Analyse (AC5) — Quellen-ID +
    Timestamp sind strukturell Pflicht (→ BR-002/BR-107), analog
    `app.contracts.llm_grounding.AnalyseFakt`."""

    kennzahl: str
    wert: Decimal
    quellen_id: str
    zeitstempel: datetime


@dataclass(frozen=True)
class KandidatDetail:
    """Detail-Sicht auf eine einzelne Analyse (AC5): Kategorie-Fakten inkl.
    Quellen-ID + Timestamp (→ BR-002), die Begründung und der
    Sanity-Cap-Status (→ BR-008). `gesamtscore`/`signal` sind `None`, wenn
    die Analyse wegen fehlender Evidenz übersprungen wurde (No-Evidence-No-
    Trade, deckt E3)."""

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
    fakten: tuple[KandidatFakt, ...]
    as_of: datetime


class KandidatenRepository(Protocol):
    """Lese-Zugriff auf das Kandidaten-Analyse-Read-Modell (AC7)."""

    def liste_kandidaten(self) -> list[KandidatUebersicht]:
        """AC4: liefert alle vollständig bewerteten Kandidaten (`gesamtscore`
        UND `signal` gesetzt), neueste Analyse zuerst (`as_of` absteigend).
        Eine wegen fehlender Evidenz übersprungene Analyse erscheint NICHT
        in dieser Liste."""
        ...

    def kandidat_detail(self, analysis_result_id: str) -> KandidatDetail | None:
        """AC5: liefert die Detail-Sicht einer einzelnen Analyse, oder
        `None`, falls `analysis_result_id` nicht existiert (bzw. keine
        gültige UUID ist). Liefert auch eine übersprungene Analyse
        (`gesamtscore`/`signal` dann `None`, deckt E3)."""
        ...
