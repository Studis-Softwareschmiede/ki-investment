"""Modul-Verträge Analyse-Framework — Berechnungskern (C-007, S-009/S-010/S-011).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet den
vollen Output-Vertrag aus `docs/specs/analyse-framework.md` ab, den der
Berechnungskern (`app.domain.scoring.score_engine`) für alle Storys dieses
Features benötigt (AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11):

- `MethodeEingabe` — eine Methode innerhalb einer Analysekategorie
  (`methoden_id`, `ranking`, `methodenscore`), Eingabe für AC1/AC2/AC9.
- `KategorieEingabe` — eine Analysekategorie mit ihren Methoden (`{
  kategorie, methoden }`, Verträge-Struktur der Spec).
- `Kategoriegewichte` — die 5 Kategoriegewichte einer Anlageklasse
  (Prozentwerte 0–100, Quelle [[anlageklassen-config]]), Eingabe für AC3.
- `KategorieScores` — die 5 Kategorie-Scores als Ausgabe von
  `berechne_kategorie_scores` (Output-Form `kategorie_scores` der
  Verträge); `None` je Kategorie markiert fehlende Evidenz (Hook für die
  No-Evidence-No-Trade-Entscheidung, AC8).
- `Signal` — die 5 möglichen Handlungssignale (Output-Feld `signal` der
  Verträge), Ausgabe von `score_engine.leite_signal_ab` (AC5) ggf. nach
  `score_engine.wende_risiko_sanity_cap_an` (AC7).
- `ScoreSchwellen` — die Score-Schwellen für die Signal-Ableitung
  (Eingabe-Feld `score_schwellen?` der Verträge, AC5/AC6). Default-Werte
  entsprechen den globalen AC5-Schwellen; wird ein Feld beim Instanziieren
  nicht gesetzt, greift automatisch der Default (AC6: "ist keine
  klassenspezifische Schwelle gesetzt, greifen die Default-Werte").
- `Uebersprungen` — Output-Feld `uebersprungen?` der Verträge (AC8):
  `{ grund: "no-evidence", kategorie }`, wenn eine ganze Analysekategorie
  ohne Methodenscore war und der Titel deshalb übersprungen wurde.
- `SpinnennetzAchsen` — die 5 Kategorie-Scores als (nicht-optionale)
  Achsenwerte 0–10, Baustein des `spinnennetz`-Outputs (AC10). Anders als
  `KategorieScores` strukturell ohne `None`, weil eine Spinnennetz-Achse
  nur für eine vollständige Analyse (alle 5 Kategorien vorhanden) gebaut
  wird.
- `Spinnennetz` — Output-Feld `spinnennetz` der Verträge (AC10):
  `{ achsen, historischer_durchschnitt? }`.
- `AnalyseErgebnis` — der volle Output-Vertrag der Spec (`{
  kategorie_scores, gesamtscore?, signal?, sanity_cap_angewendet,
  spinnennetz?, uebersprungen? }`), Ausgabe von
  `score_engine.fuehre_analyse_durch` (S-011, AC8/AC10 verdrahten die
  bereits vorhandenen, reinen S-009/S-010-Bausteine zum Gesamtergebnis).

Der Cap-Schwellwert aus AC7 ("Cap-Schwellwert 3 ist konfigurierbar") wird
bewusst NICHT als eigenes DTO-Feld hier geführt, sondern als Parameter mit
Default an `score_engine.wende_risiko_sanity_cap_an` — die Verträge der
Spec nennen dafür keine eigene Input-Struktur.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Die 5 Analysekategorien (Verträge, `kategorie_scores`-Output). Bewusst
#: eigenständig statt aus `app.db.models.ANALYSIS_CATEGORY_CODES`
#: importiert: `app/domain/**` und `app/contracts/**` dürfen laut
#: architecture.md §4 nicht von `app.db.*` abhängen (Boundary-Regel P1/P3).
KategorieName = Literal["fundamental", "technisch", "qualitativ", "makro", "risiko"]

KATEGORIE_NAMEN: tuple[KategorieName, ...] = (
    "fundamental",
    "technisch",
    "qualitativ",
    "makro",
    "risiko",
)


class MethodeEingabe(BaseModel):
    """Eine Methode innerhalb einer Analysekategorie (Verträge, AC1/AC2/AC9).

    `ranking` ist der klassenspezifische, feste Gewichtungswert der Methode
    (aus [[anlageklassen-config]], 1–10, ändert sich nicht je Analyse, AC2).

    `methodenscore` ist der je Analyse neu vergebene Wert (1–10) oder `None`,
    wenn für diese Methode kein Score vorliegt ("fehlt", A2/AC9). Bewusst
    NICHT auf 1–10 begrenzt (anders als `ranking`): ein Methodenscore
    außerhalb 1–10 ist laut Edge-Cases der Spec eine "ungültige Eingabe, die
    nicht verrechnet wird" — kein struktureller Parse-Fehler des gesamten
    Titels, sondern eine Ausschluss-Entscheidung, die
    `score_engine.berechne_kategorie_score` trifft.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    methoden_id: str = Field(min_length=1)
    ranking: int = Field(ge=1, le=10)
    methodenscore: float | None = None


class KategorieEingabe(BaseModel):
    """Eine Analysekategorie mit ihren Methoden (Verträge: `{ kategorie,
    methoden: [...] }`), Eingabe für `score_engine.berechne_kategorie_scores`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kategorie: KategorieName
    methoden: tuple[MethodeEingabe, ...] = Field(default=())


class Kategoriegewichte(BaseModel):
    """Kategoriegewichte einer Anlageklasse (Verträge, AC3; Quelle
    [[anlageklassen-config]]). Werte sind Prozentwerte 0–100 (analog
    `category_weight.weight_pct`); die fünf Gewichte einer Klasse summieren
    sich auf 100 % — validiert in [[anlageklassen-config]] (AC7), hier nicht
    erneut geprüft (Nicht-Ziel dieser Story: "Keine Definition der
    Methodentabellen/Rankings/Gewichte selbst")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fundamental: float = Field(ge=0, le=100)
    technisch: float = Field(ge=0, le=100)
    qualitativ: float = Field(ge=0, le=100)
    makro: float = Field(ge=0, le=100)
    risiko: float = Field(ge=0, le=100)


class KategorieScores(BaseModel):
    """Kategorie-Scores einer Analyse (Verträge, `kategorie_scores`-Output,
    Ausschnitt AC1/AC9). `None` markiert eine Kategorie ohne verwertbare
    Evidenz — die Entscheidung, einen Titel deswegen zu überspringen, ist
    `score_engine.ermittle_fehlende_kategorie`/`fuehre_analyse_durch` (AC8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fundamental: float | None = None
    technisch: float | None = None
    qualitativ: float | None = None
    makro: float | None = None
    risiko: float | None = None


class Uebersprungen(BaseModel):
    """AC8 (No-Evidence-No-Trade): Output-Feld `uebersprungen?` der
    Verträge, wenn ein Titel übersprungen wurde, weil für eine ganze
    Analysekategorie jeder Methodenscore fehlte. `grund` ist strukturell
    auf den einen in der Spec genannten Wert festgelegt — die Spec kennt
    aktuell keinen anderen Skip-Grund."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    grund: Literal["no-evidence"] = "no-evidence"
    kategorie: KategorieName


class SpinnennetzAchsen(BaseModel):
    """Die 5 Kategorie-Scores als Spinnennetz-Achsenwerte (Verträge, AC10:
    "5×(0–10), eine Achse je Kategorie"). Anders als `KategorieScores`
    strukturell NICHT optional: eine Spinnennetz-Achsenreihe wird nur für
    eine vollständige Analyse gebaut (alle 5 Kategorien haben einen Score,
    sonst greift AC8/`Uebersprungen` statt eines Spinnennetzes)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fundamental: float = Field(ge=0, le=10)
    technisch: float = Field(ge=0, le=10)
    qualitativ: float = Field(ge=0, le=10)
    makro: float = Field(ge=0, le=10)
    risiko: float = Field(ge=0, le=10)


class Spinnennetz(BaseModel):
    """AC10 (Spinnennetz-Datenoutput): Output-Feld `spinnennetz` der
    Verträge, `{ achsen, historischer_durchschnitt? }`. Die aktuelle
    Datenreihe (`achsen`) ist Pflicht; der historische Durchschnitt je
    Achse ist eine optionale zweite Datenreihe ("Historischer Durchschnitt
    nicht vorhanden (neuer Titel) → Spinnennetz nur mit aktueller
    Datenreihe", Edge-Cases der Spec)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    achsen: SpinnennetzAchsen
    historischer_durchschnitt: SpinnennetzAchsen | None = None


#: Die 5 Handlungssignale (Verträge, `signal`-Output, AC5/AC7).
Signal = Literal["KAUF", "BEOBACHTEN", "HALTEN", "REDUZIEREN", "VERKAUF"]


class ScoreSchwellen(BaseModel):
    """Score-Schwellen für die Signal-Ableitung (Verträge, Eingabe-Feld
    `score_schwellen?`, AC5/AC6).

    Jedes Feld ist die **Untergrenze** (inklusiv, AC5) des jeweiligen
    Signals; unterhalb der niedrigsten Schwelle (`reduzieren`) gilt
    VERKAUF (kein eigenes Feld nötig — kein Boden nach unten).

    Die Default-Werte entsprechen den globalen AC5-Schwellen. AC6: die
    Schwellen sind je Anlageklasse konfigurierbar — ein Aufrufer instanziiert
    `ScoreSchwellen` mit nur den klassenspezifisch abweichenden Feldern; für
    nicht gesetzte Felder greift automatisch der AC5-Default (Pydantic-
    Feld-Default), "ist keine klassenspezifische Schwelle gesetzt, greifen
    die Default-Werte" ist damit strukturell erfüllt, ohne eine separate
    Merge-Logik zu benötigen.

    Invariante `kauf ≥ beobachten ≥ halten ≥ reduzieren` (Cross-Field,
    per `model_validator`): `score_engine.leite_signal_ab` prüft die
    Schwellen top-down (erst `kauf`, dann `beobachten`, ...). Bei einem
    Teil-Override, der diese Reihenfolge verletzt (z. B. nur `reduzieren`
    auf einen Wert über dem unveränderten `halten`-Default angehoben),
    würde das REDUZIEREN-Fenster still unerreichbar — ein Score, der
    eigentlich REDUZIEREN treffen sollte, matcht bereits bei `halten`.
    Die Validierung lehnt eine solche Konfiguration structural ab, statt
    sie unbemerkt durchzulassen.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kauf: float = Field(default=8.0, ge=0, le=10)
    beobachten: float = Field(default=6.0, ge=0, le=10)
    halten: float = Field(default=4.0, ge=0, le=10)
    reduzieren: float = Field(default=2.0, ge=0, le=10)

    @model_validator(mode="after")
    def _pruefe_monotonie(self) -> "ScoreSchwellen":
        """Erzwingt `kauf ≥ beobachten ≥ halten ≥ reduzieren` — sonst würde
        ein Teil-Override (AC6) ein Signal-Fenster still unerreichbar
        machen (siehe Klassen-Docstring)."""
        if not (self.kauf >= self.beobachten >= self.halten >= self.reduzieren):
            raise ValueError(
                "ScoreSchwellen ungültig: erwartet kauf >= beobachten >= halten "
                f">= reduzieren, erhalten kauf={self.kauf}, beobachten={self.beobachten}, "
                f"halten={self.halten}, reduzieren={self.reduzieren}."
            )
        return self


class AnalyseErgebnis(BaseModel):
    """Voller Output-Vertrag der Spec (Ausgabe von
    `score_engine.fuehre_analyse_durch`, AC8/AC10):
    `{ kategorie_scores, gesamtscore?, signal?, sanity_cap_angewendet,
    spinnennetz?, uebersprungen? }`.

    Zwei sich gegenseitig ausschließende Ausprägungen:

    - **Übersprungen (AC8):** `uebersprungen` gesetzt, `gesamtscore`,
      `signal` und `spinnennetz` bleiben `None`
      (`sanity_cap_angewendet=False`) — "kein Gesamtscore, kein Signal".
    - **Vollständige Analyse (AC10):** `uebersprungen` bleibt `None`,
      `gesamtscore`/`signal`/`spinnennetz` sind gesetzt.

    `kategorie_scores` ist in beiden Fällen vorhanden (auch bei
    "übersprungen" zeigt es, welche Kategorien tatsächlich Evidenz
    hatten) — das entspricht der Verträge-Struktur der Spec, die
    `kategorie_scores` nicht als optional führt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kategorie_scores: KategorieScores
    gesamtscore: float | None = None
    signal: Signal | None = None
    sanity_cap_angewendet: bool = False
    spinnennetz: Spinnennetz | None = None
    uebersprungen: Uebersprungen | None = None
