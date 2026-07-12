"""Modul-Verträge LLM-Grounding-Gate: Analyse-Input/-Output + Grounding-Ergebnis
plus Cross-Check/Audit-Verträge (S-013).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang läuft
über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet die Verträge
aus `docs/specs/llm-grounding.md` ("Verträge") ab.

Aus S-012 (AC1-AC3):

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
  (`app.adapters.llm.grounding.pruefe_grounding`).

Neu aus S-013 (AC4, AC5, AC10) — Verträge des "Cross-Check-Moduls":

- `Originalquelle` — der tatsächliche Wert einer Kennzahl an ihrer Quelle
  (`quellen_id`), gegen den ein `AnalyseFakt.wert` deterministisch geprüft
  wird (AC4).
- `ToleranzKonfig` — konfigurierbare Toleranzschwelle je Kennzahl-Typ
  (absolut vs. relativ, AC5); Standardwerte liegen in `app.config`
  (ohne Codeänderung überschreibbar).
- `Abweichung` — eine gemessene Abweichung zwischen Output- und Quellwert
  je Kennzahl, Teil des Cross-Check-Ergebnisses.
- `ProtokollEintrag` — ein auditierbarer Protokolleintrag (Grund, Zeitpunkt,
  betroffene Kennzahl/Quelle, AC10); wird sowohl vom Grounding-Gate (S-012-
  Ablehnungspfade) als auch vom Cross-Check-Modul über
  `app.core.audit_log.protokolliere` geschrieben.
- `CrossCheckErgebnis` — strukturiertes Ergebnis des deterministischen
  Zahlen-Cross-Checks (`app.adapters.llm.cross_check.pruefe_cross_check`).

Neu aus S-014 (AC6) — Vertrag der No-Evidence-No-Trade-Prüfung:

- `EvidenzErgebnis` — strukturiertes Ergebnis von
  `app.domain.no_evidence_no_trade.pruefe_evidenzlage`: fehlt einer
  `AnalyseScores`-Kategorie der Score (`"fehlt"`), wird der Titel komplett
  übersprungen statt geschätzt (AC6, geteilte Regel mit
  [[analyse-framework]]); der Übersprung wird protokolliert (AC10, neuer
  `ProtokollGrund`-Wert `keine_evidenz`).

Neu aus S-027 (AC8, AC9, BR-006) — Vertrag der Halluzinations-KPI & des Kills:

- `LlmKettenStatus` — Betriebszustand der LLM-Kette (`aktiv`/`deaktiviert`,
  architecture.md §6 "LLM-Kette (BR-006)").
- `HalluzinationsKpiErgebnis` — strukturiertes Ergebnis von
  `app.core.hallucination_kpi.berechne_kpi`: laufend berechnete Quote
  „Analysen mit Faktenabweichung" aus dem Cross-Check (AC8) plus
  Alarm-/Kill-Zustand (AC9). Neuer `ProtokollGrund`-Wert
  `halluzinations_kpi_alarm` protokolliert den Übergang `aktiv` →
  `deaktiviert` (AC10-Geist).

Nicht Teil dieser Story (Nicht-Ziele der Spec `llm-grounding`): kein
Feld-für-Feld-Schema über die hier genannten Verträge hinaus, keine
Score-Berechnungslogik, kein Mapping, welches Finanz-Plugin welche Kategorie
erdet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

#: Score je Analysekategorie: 0–10 oder der Platzhalter "fehlt" (Verträge,
#: Spec `llm-grounding` — der Umgang mit "fehlt" (No-Evidence-No-Trade) ist
#: AC6/S-014, siehe `app.domain.no_evidence_no_trade.pruefe_evidenzlage`;
#: hier nur als zulässiger Schema-Wert der AC3-Validierung).
_Score = Annotated[float, Field(ge=0, le=10)]


class AnalyseFakt(BaseModel):
    """Eine einzelne geerdete Kennzahl (Verträge, Spec `llm-grounding`).

    `quellen_id` und `timestamp` sind Pflicht (AC1) — fehlt eines von
    beiden, verweigert pydantic die Instanziierung; ein Analyse-Output mit
    einem solchen Fakt wird dadurch strukturell abgelehnt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kennzahl_typ: str = Field(min_length=1)
    wert: float
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


class Originalquelle(BaseModel):
    """Der tatsächliche Wert einer Kennzahl an ihrer Datenquelle (Verträge,
    Spec `llm-grounding`, Cross-Check-Modul, AC4) — die Vergleichsbasis für
    den deterministischen Cross-Check gegen `AnalyseFakt.wert`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quellen_id: str = Field(min_length=1)
    kennzahl_typ: str = Field(min_length=1)
    wert: float


class ToleranzKonfig(BaseModel):
    """Konfigurierbare Toleranzschwelle eines Kennzahl-Typs (AC5) —
    entweder eine absolute Differenz oder eine relative Abweichung
    (Bruchteil des Quellwerts). Provisorische Default-Werte liegen in
    `app.config`, ohne Codeänderung per `toleranz_config`-Übersteuerung
    (Aufrufparameter) oder Env-Variable ersetzbar."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kennzahl_typ: str = Field(min_length=1)
    typ: Literal["absolut", "relativ"]
    schwelle: float = Field(ge=0)


class Abweichung(BaseModel):
    """Eine gemessene Abweichung zwischen Output- und Quellwert einer
    Kennzahl (Verträge, Spec `llm-grounding`, Cross-Check-Modul, AC4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kennzahl_typ: str = Field(min_length=1)
    wert_output: float
    wert_quelle: float
    abweichung: float
    toleranz: float


#: Gründe, aus denen ein Protokolleintrag entsteht (AC10) — deckt sowohl
#: die S-012-Ablehnungspfade des Grounding-Gates (`schema_verletzung`,
#: `input_fremde_zahl`) als auch die S-013-Cross-Check-Ablehnungsgründe
#: (`cross_check_abweichung`, `quelle_nicht_verfuegbar`,
#: `toleranz_nicht_konfiguriert`, Edge-Cases der Spec), den S-014-
#: No-Evidence-No-Trade-Übersprung (`keine_evidenz`, AC6) und den S-027-
#: Halluzinations-KPI-Alarm/Kill (`halluzinations_kpi_alarm`, AC9) unter
#: einem gemeinsamen Vokabular ab.
ProtokollGrund = Literal[
    "schema_verletzung",
    "input_fremde_zahl",
    "cross_check_abweichung",
    "quelle_nicht_verfuegbar",
    "toleranz_nicht_konfiguriert",
    "keine_evidenz",
    "halluzinations_kpi_alarm",
]


class ProtokollEintrag(BaseModel):
    """Ein auditierbarer Protokolleintrag für eine abgelehnte/verworfene
    Analyse (AC10): Grund, Zeitpunkt und betroffene Kennzahl/Quelle.
    Enthält bewusst keine Rohdaten/Secrets — nur die für die Auditierung
    nötigen strukturierten Felder (NFR "keine Secrets im Klartext")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    zeitpunkt: datetime
    grund: ProtokollGrund
    kennzahl_typ: str | None = None
    quellen_id: str | None = None
    detail: str


class CrossCheckErgebnis(BaseModel):
    """Strukturiertes Ergebnis des deterministischen Zahlen-Cross-Checks
    (AC4, `app.adapters.llm.cross_check.pruefe_cross_check`). Bricht die
    Prüfung bei der ersten verwerfenden Abweichung/dem ersten Edge-Case ab
    (konservatives Verwerfen) — `abweichungen` enthält alle bis dahin
    berechneten Vergleiche, `protokoll_eintrag` ist gesetzt, sobald
    `status == "verworfen"` (AC10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["geerdet", "verworfen"]
    abweichungen: tuple[Abweichung, ...] = Field(default=())
    protokoll_eintrag: ProtokollEintrag | None = None


class EvidenzErgebnis(BaseModel):
    """Ergebnis der No-Evidence-No-Trade-Prüfung (AC6, S-014,
    `app.domain.no_evidence_no_trade.pruefe_evidenzlage`) — geteilte Regel
    mit [[analyse-framework]] (dort AC8): fehlt einer der 5
    Analysekategorien die Datengrundlage (Score `"fehlt"`), wird der Titel
    komplett übersprungen (`status == "uebersprungen"`), statt den
    fehlenden Score durch eine LLM-Schätzung zu ersetzen. Nur bei
    `status == "uebersprungen"` ist `protokoll_eintrag` gesetzt (AC10)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["vollstaendig", "uebersprungen"]
    fehlende_kategorien: tuple[str, ...] = Field(default=())
    protokoll_eintrag: ProtokollEintrag | None = None


#: Betriebszustand der LLM-Kette (Verträge, Spec `llm-grounding`, BR-006,
#: architecture.md §6): `aktiv` erlaubt LLM-basierte Analysen in der
#: Entscheidungskette, `deaktiviert` markiert einen ausgelösten
#: Halluzinations-KPI-Alarm (AC9) — bleibt so bis zum manuellen Reset.
LlmKettenStatus = Literal["aktiv", "deaktiviert"]


class HalluzinationsKpiErgebnis(BaseModel):
    """Ergebnis der laufenden Halluzinations-KPI-Berechnung (AC8, S-027,
    `app.core.hallucination_kpi.berechne_kpi`) — Quote „Analysen mit
    Faktenabweichung" über die im Beobachtungsfenster registrierten
    Cross-Check-Ergebnisse (AC4) plus den daraus resultierenden
    Alarm-/Kill-Zustand (AC9): `alarm` ist nur bei einer Quote STRIKT über
    `schwellwert` `True` (Edge-Case „genau am Schwellwert → kein Alarm");
    `llm_status` spiegelt den aktuellen (ggf. bereits zuvor ausgelösten)
    Zustand der LLM-Kette (BR-006)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    geprueft: int = Field(ge=0)
    verworfen: int = Field(ge=0)
    quote: float = Field(ge=0)
    schwellwert: float = Field(ge=0)
    alarm: bool
    llm_status: LlmKettenStatus
