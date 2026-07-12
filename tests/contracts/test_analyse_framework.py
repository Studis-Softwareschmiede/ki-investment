"""Tests für die Analyse-Framework-Verträge (Story S-009, Berechnungskern).

Covers (analyse-framework): AC1, AC2, AC3, AC9

`app.contracts.analyse_framework` bildet den Ausschnitt der Verträge aus
`docs/specs/analyse-framework.md` ab, den der Berechnungskern
(`app.domain.scoring.score_engine`) für diese Story benötigt. Diese Tests
decken auf DTO-Ebene die Grenzfälle, die für die Berechnungslogik relevant
sind (AC2: Ranking strukturell auf 1–10 begrenzt; Methodenscore bewusst
NICHT begrenzt, siehe `MethodeEingabe`-Docstring; AC3:
Kategoriegewichte-Wertebereich; AC9: `KategorieScores`/`methodenscore`
akzeptieren fehlende Werte als `None`). Die eigentliche Formel-Berechnung
(AC1/AC4/AC9/AC11) liegt in `tests/domain/scoring/test_score_engine.py`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.analyse_framework import (
    KATEGORIE_NAMEN,
    KategorieEingabe,
    Kategoriegewichte,
    KategorieScores,
    MethodeEingabe,
)


def test_methode_eingabe_akzeptiert_fehlenden_methodenscore() -> None:
    """@trace analyse-framework#AC9 — `methodenscore=None` ("fehlt", A2)
    lässt sich instanziieren; der Ausschluss aus der Berechnung ist Sache
    von `score_engine.berechne_kategorie_score`, keine Parse-Ablehnung."""
    methode = MethodeEingabe(methoden_id="dcf", ranking=9, methodenscore=None)
    assert methode.methodenscore is None


@pytest.mark.parametrize("methodenscore", [0, 0.5, 10.01, 15, -3])
def test_methode_eingabe_akzeptiert_methodenscore_ausserhalb_1_bis_10(
    methodenscore: float,
) -> None:
    """@trace analyse-framework#AC2 — ein Methodenscore außerhalb 1–10 ist
    laut Edge-Cases eine "ungültige Eingabe, die nicht verrechnet wird" —
    kein struktureller Parse-Fehler des gesamten Titels. Der Ausschluss aus
    der Berechnung passiert in `score_engine.berechne_kategorie_score`."""
    methode = MethodeEingabe(methoden_id="dcf", ranking=9, methodenscore=methodenscore)
    assert methode.methodenscore == methodenscore


@pytest.mark.parametrize("ranking", [0, -1, 11, 100])
def test_methode_eingabe_lehnt_ranking_ausserhalb_1_bis_10_ab(ranking: int) -> None:
    """@trace analyse-framework#AC2 — das Ranking ist der klassenspezifische,
    feste Gewichtungswert aus [[anlageklassen-config]] und dort bereits auf
    1–10 validiert; die DTO-Grenze spiegelt diese Invariante."""
    with pytest.raises(ValidationError):
        MethodeEingabe(methoden_id="dcf", ranking=ranking, methodenscore=8)


def test_kategorie_eingabe_traegt_kategorie_und_methoden() -> None:
    """@trace analyse-framework#AC1 — `KategorieEingabe` bildet die
    Verträge-Struktur `{ kategorie, methoden: [...] }` ab."""
    eingabe = KategorieEingabe(
        kategorie="fundamental",
        methoden=(MethodeEingabe(methoden_id="dcf", ranking=9, methodenscore=8),),
    )
    assert eingabe.kategorie == "fundamental"
    assert len(eingabe.methoden) == 1


def test_kategoriegewichte_akzeptiert_werte_0_bis_100_ohne_summenpruefung() -> None:
    """@trace analyse-framework#AC3 — Kategoriegewichte sind Prozentwerte
    0–100; die Summenprüfung auf exakt 100 % ist Sache von
    [[anlageklassen-config]] (AC7 dort) und wird hier bewusst NICHT erneut
    durchgeführt (Nicht-Ziel dieser Story)."""
    gewichte = Kategoriegewichte(fundamental=35, technisch=15, qualitativ=20, makro=10, risiko=20)
    assert gewichte.fundamental == 35
    # Summe absichtlich != 100 — wird von diesem DTO nicht zurückgewiesen.
    ungeprueft = Kategoriegewichte(fundamental=50, technisch=50, qualitativ=50, makro=50, risiko=50)
    assert ungeprueft.qualitativ == 50


def test_kategorie_scores_default_ist_ueberall_none() -> None:
    """@trace analyse-framework#AC9 — `KategorieScores` ohne Angaben markiert
    alle 5 Kategorien als ohne Evidenz (`None`), der Hook für die
    No-Evidence-No-Trade-Entscheidung (AC8, Folge-Story)."""
    scores = KategorieScores()
    for kategorie in KATEGORIE_NAMEN:
        assert getattr(scores, kategorie) is None
