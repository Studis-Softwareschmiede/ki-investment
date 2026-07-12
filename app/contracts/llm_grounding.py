"""Modul-Verträge LLM-Grounding-Gate: Analyse-Input/-Output + Grounding-Ergebnis.

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang läuft
über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet die Verträge
aus `docs/specs/llm-grounding.md` ("Verträge") ab, für den Ausschnitt dieser
Story (S-012, AC1-AC3):

- `AnalyseInput` — was das LLM als strukturierten, geerdeten Input erhält
  (`{ titel, anlageklasse, fakten: [...] }`).
- `AnalyseOutput` — der vom LLM zurückgelieferte Analyse-Output, gegen ein
  festes JSON-Schema validiert (AC3): Score je Kategorie 0–10 oder "fehlt",
  Fakten mit Quellen-IDs, Begründung.
- `AnalyseFakt` — eine einzelne geerdete Kennzahl, identisch strukturiert in
  Input UND Output (`kennzahl_typ, wert, quellen_id, timestamp`). Fehlt
  `quellen_id` oder `timestamp`, verweigert pydantic die Instanziierung —
  ein Analyse-Output mit einem solchen Fakt gilt strukturell als ungültig
  (Grounding-Pflicht, AC1).
- `GroundingErgebnis` — strukturiertes Ergebnis des Grounding-Gates
  (`app.adapters.llm.grounding.pruefe_grounding`), an das Folge-Stories
  (Protokollierung AC10, Cross-Check AC4) andocken können, ohne diese Story
  zu erweitern.

Nicht Teil dieser Story (Nicht-Ziele der Spec `llm-grounding`): kein
Feld-für-Feld-Schema über die hier genannten Verträge hinaus, keine
Score-Berechnungslogik, kein Cross-Check gegen Originalquellen (AC4) und kein
Mapping, welches Finanz-Plugin welche Kategorie erdet.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Score je Analysekategorie: 0–10 oder der Platzhalter "fehlt" (Verträge,
#: Spec `llm-grounding` — der Umgang mit "fehlt", No-Evidence-No-Trade, ist
#: AC6/[[analyse-framework]] und NICHT Teil dieser Story; hier nur als
#: zulässiger Schema-Wert).
_Score = Annotated[float, Field(ge=0, le=10)]


class AnalyseFakt(BaseModel):
    """Eine einzelne geerdete Kennzahl (Verträge, Spec `llm-grounding`).

    `quellen_id` und `timestamp` sind Pflicht (AC1) — fehlt eines von
    beiden, verweigert pydantic die Instanziierung; ein Analyse-Output mit
    einem solchen Fakt wird dadurch strukturell abgelehnt.

    `wert` ist `Decimal`, nicht `float` (architecture.md P7): über
    `kennzahl_typ` laufen absehbar auch Geldwerte (Kurs, Marktkapitalisierung),
    und der Cross-Check-Toleranzvergleich (AC4, Folge-Story) darf keine
    Float-Rundungsdrift erben. Scores bleiben davon unberührt (`AnalyseScores`,
    P7-Ausnahme für Statistik).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kennzahl_typ: str = Field(min_length=1)
    wert: Decimal
    quellen_id: str = Field(min_length=1)
    timestamp: datetime


class AnalyseInput(BaseModel):
    """Strukturierter Analyse-Input an das LLM (Verträge, Spec `llm-grounding`).

    Alle Zahlen sind geerdet (`fakten`) — das LLM erhält keine unstrukturierte
    Freitext-Kennzahl, gegen die ein Analyse-Output später rückgeführt werden
    könnte, ohne dass die Herkunft eindeutig ist (Basis für AC2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel: str = Field(min_length=1)
    anlageklasse: int = Field(ge=1, le=11)
    fakten: tuple[AnalyseFakt, ...] = Field(default=())


class AnalyseScores(BaseModel):
    """Score je der 5 Analysekategorien (Verträge, Spec `llm-grounding`, AC3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fundamental: _Score | Literal["fehlt"]
    technisch: _Score | Literal["fehlt"]
    qualitativ: _Score | Literal["fehlt"]
    makro: _Score | Literal["fehlt"]
    risiko: _Score | Literal["fehlt"]


class AnalyseOutput(BaseModel):
    """Analyse-Output, wird gegen dieses feste JSON-Schema validiert (AC3,
    deckt E1). Schema-Verletzung (fehlendes Pflichtfeld, Score außerhalb
    0–10, unbekanntes Zusatzfeld, Fakt ohne Quellen-ID/Timestamp, ...)
    verweigert pydantic die Instanziierung."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scores: AnalyseScores
    fakten: tuple[AnalyseFakt, ...] = Field(default=())
    begruendung: str = Field(min_length=1)


#: Ablehnungsgründe, die diese Story (AC1-AC3) unterscheidet. AC1
#: (fehlende Quellen-ID/Timestamp) läuft strukturell über dasselbe
#: `AnalyseOutput`-Schema wie AC3 — beide Verstöße ergeben daher
#: `"schema_verletzung"`; nur AC2 (input-fremde Zahl) hat einen eigenen Grund.
GroundingAblehnungsgrund = Literal["schema_verletzung", "input_fremde_zahl"]


class GroundingErgebnis(BaseModel):
    """Strukturiertes Ergebnis des Grounding-Gates (AC1-AC3).

    Bewusst als DTO statt als durchgereichte Exception, damit Folge-Stories
    (Protokollierung AC10, Cross-Check AC4) an `grund`/`detail` andocken
    können, ohne diese Story zu erweitern.
    """

    model_config = ConfigDict(frozen=True)

    status: Literal["geerdet", "abgelehnt"]
    grund: GroundingAblehnungsgrund | None = None
    detail: str | None = None
    output: AnalyseOutput | None = None

    @model_validator(mode="after")
    def _status_invariante(self) -> GroundingErgebnis:
        """geerdet ⇔ output gesetzt und kein grund; abgelehnt ⇔ grund gesetzt
        und kein output — unabhängig von der Aufrufer-Disziplin in
        `pruefe_grounding` (Folge-Stories docken an `grund`/`output` an)."""
        if self.status == "geerdet" and (self.output is None or self.grund is not None):
            raise ValueError("status 'geerdet' verlangt output und verbietet grund")
        if self.status == "abgelehnt" and (self.grund is None or self.output is not None):
            raise ValueError("status 'abgelehnt' verlangt grund und verbietet output")
        return self
