"""Modul-Verträge Analyse-Framework — Berechnungskern (C-007, S-009).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet den
Ausschnitt der Verträge aus `docs/specs/analyse-framework.md` ab, den der
Berechnungskern (`app.domain.scoring.score_engine`) für diese Story
benötigt (AC1, AC2, AC3, AC4, AC9, AC11):

- `MethodeEingabe` — eine Methode innerhalb einer Analysekategorie
  (`methoden_id`, `ranking`, `methodenscore`), Eingabe für AC1/AC2/AC9.
- `KategorieEingabe` — eine Analysekategorie mit ihren Methoden (`{
  kategorie, methoden }`, Verträge-Struktur der Spec).
- `Kategoriegewichte` — die 5 Kategoriegewichte einer Anlageklasse
  (Prozentwerte 0–100, Quelle [[anlageklassen-config]]), Eingabe für AC3.
- `KategorieScores` — die 5 Kategorie-Scores als Ausgabe von
  `berechne_kategorie_scores` (Output-Form `kategorie_scores` der
  Verträge); `None` je Kategorie markiert fehlende Evidenz (Hook für die
  No-Evidence-No-Trade-Entscheidung AC8, Folge-Story S-010/S-011).

Nicht Teil dieser Story (Nicht-Ziele/Folge-Stories): `score_schwellen`,
Signal, `sanity_cap_angewendet`, `spinnennetz` und `uebersprungen` aus dem
vollen Output-Vertrag der Spec — diese Felder kommen mit den ACs 5–8/10.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
    Evidenz — die Entscheidung, einen Titel deswegen zu überspringen
    (No-Evidence-No-Trade, AC8), ist Nicht-Ziel dieser Story."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fundamental: float | None = None
    technisch: float | None = None
    qualitativ: float | None = None
    makro: float | None = None
    risiko: float | None = None
