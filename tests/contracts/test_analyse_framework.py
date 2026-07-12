"""Tests für die Analyse-Framework-Verträge (Storys S-009/S-010/S-011, Berechnungskern).

Covers (analyse-framework): AC1, AC2, AC3, AC5, AC6, AC8, AC9, AC10

`app.contracts.analyse_framework` bildet den Ausschnitt der Verträge aus
`docs/specs/analyse-framework.md` ab, den der Berechnungskern
(`app.domain.scoring.score_engine`) benötigt. Diese Tests decken auf
DTO-Ebene die Grenzfälle, die für die Berechnungslogik relevant sind (AC2:
Ranking strukturell auf 1–10 begrenzt; Methodenscore bewusst NICHT
begrenzt, siehe `MethodeEingabe`-Docstring; AC3: Kategoriegewichte-
Wertebereich; AC5/AC6: `ScoreSchwellen`-Defaults entsprechen den
AC5-Werten, nicht gesetzte Felder fallen automatisch auf den Default
zurück; AC9: `KategorieScores`/`methodenscore` akzeptieren fehlende Werte
als `None`; AC8: `Uebersprungen`-Struktur des No-Evidence-Skip-Outputs;
AC10: `SpinnennetzAchsen`/`Spinnennetz`-Wertebereich der Achsendaten). Die
eigentliche Formel-/Signal-/Skip-/Spinnennetz-Berechnung
(AC1/AC4/AC5/AC6/AC7/AC8/AC9/AC10/AC11) liegt in
`tests/domain/scoring/test_score_engine.py`.
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
    ScoreSchwellen,
    Spinnennetz,
    SpinnennetzAchsen,
    Uebersprungen,
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
    No-Evidence-No-Trade-Entscheidung (AC8, `Uebersprungen` weiter
    unten)."""
    scores = KategorieScores()
    for kategorie in KATEGORIE_NAMEN:
        assert getattr(scores, kategorie) is None


def test_score_schwellen_default_entspricht_ac5_werten() -> None:
    """@trace analyse-framework#AC5 — `ScoreSchwellen()` ohne Angaben liefert
    exakt die globalen Default-Schwellen aus AC5 (8.0/6.0/4.0/2.0)."""
    schwellen = ScoreSchwellen()
    assert schwellen.kauf == 8.0
    assert schwellen.beobachten == 6.0
    assert schwellen.halten == 4.0
    assert schwellen.reduzieren == 2.0


def test_score_schwellen_nicht_gesetztes_feld_faellt_auf_default_zurueck() -> None:
    """@trace analyse-framework#AC6 — wird nur ein Feld einer Klassen-
    spezifischen `ScoreSchwellen`-Instanz gesetzt, bleiben die übrigen
    Felder auf dem AC5-Default ("ist keine klassenspezifische Schwelle
    gesetzt, greifen die Default-Werte")."""
    schwellen = ScoreSchwellen(kauf=9.0)
    assert schwellen.kauf == 9.0
    assert schwellen.beobachten == 6.0
    assert schwellen.halten == 4.0
    assert schwellen.reduzieren == 2.0


@pytest.mark.parametrize("feld", ["kauf", "beobachten", "halten", "reduzieren"])
def test_score_schwellen_lehnt_wert_ausserhalb_0_bis_10_ab(feld: str) -> None:
    """@trace analyse-framework#AC5 — Score-Schwellen liegen strukturell im
    Wertebereich des Gesamtscores (0–10), analog zu anderen Score-Feldern
    der Verträge."""
    with pytest.raises(ValidationError):
        ScoreSchwellen(**{feld: 10.01})


def test_score_schwellen_akzeptiert_gueltige_monotone_konfiguration() -> None:
    """@trace analyse-framework#AC6 — eine vollständig gesetzte, monoton
    fallende Klassen-Konfiguration (kauf ≥ beobachten ≥ halten ≥
    reduzieren) wird akzeptiert, auch wenn sie von den AC5-Defaults
    abweicht."""
    schwellen = ScoreSchwellen(kauf=9.0, beobachten=7.0, halten=5.0, reduzieren=3.0)
    assert schwellen.kauf == 9.0
    assert schwellen.beobachten == 7.0
    assert schwellen.halten == 5.0
    assert schwellen.reduzieren == 3.0


def test_score_schwellen_akzeptiert_gleiche_werte_an_der_grenze() -> None:
    """@trace analyse-framework#AC6 — die Monotonie-Invariante ist `≥`
    (nicht strikt `>`); gleiche Nachbarwerte sind zulässig."""
    schwellen = ScoreSchwellen(kauf=8.0, beobachten=8.0, halten=4.0, reduzieren=4.0)
    assert schwellen.kauf == schwellen.beobachten == 8.0
    assert schwellen.halten == schwellen.reduzieren == 4.0


def test_score_schwellen_teil_override_der_das_reduzieren_fenster_verschluckt_wird_abgelehnt() -> (
    None
):
    """@trace analyse-framework#AC6 — Kern-Regressionstest des Review-
    Befunds: wird nur `reduzieren` klassenspezifisch über den unveränderten
    `halten`-Default (4.0) angehoben, würde ohne Validierung das
    REDUZIEREN-Signal-Fenster still unerreichbar (ein Score wie 4.5 matcht
    bereits bei `halten`, bevor `reduzieren` geprüft wird). Die Validierung
    lehnt diese inkonsistente Teil-Override-Konfiguration ab."""
    with pytest.raises(ValidationError, match="kauf >= beobachten >= halten >= reduzieren"):
        ScoreSchwellen(reduzieren=5.0)


@pytest.mark.parametrize(
    "werte",
    [
        {"kauf": 5.0, "beobachten": 6.0},  # kauf < beobachten
        {"beobachten": 3.0, "halten": 4.0},  # beobachten < halten
        {"halten": 1.0, "reduzieren": 2.0},  # halten < reduzieren
    ],
)
def test_score_schwellen_lehnt_nicht_monotone_direkte_werte_ab(werte: dict[str, float]) -> None:
    """@trace analyse-framework#AC6 — auch bei direkt (nicht nur per
    Teil-Override) widersprüchlich gesetzten Nachbar-Feldern greift die
    Monotonie-Validierung."""
    with pytest.raises(ValidationError):
        ScoreSchwellen(**werte)


# --- AC8: Uebersprungen (No-Evidence-No-Trade-Output) -----------------------


def test_uebersprungen_traegt_grund_und_kategorie() -> None:
    """@trace analyse-framework#AC8 — `Uebersprungen` bildet die
    Verträge-Struktur `{ grund: "no-evidence", kategorie }` ab; `grund`
    hat einen Default, da die Spec aktuell keinen anderen Skip-Grund
    kennt."""
    uebersprungen = Uebersprungen(kategorie="risiko")
    assert uebersprungen.grund == "no-evidence"
    assert uebersprungen.kategorie == "risiko"


def test_uebersprungen_lehnt_unbekannten_grund_ab() -> None:
    """@trace analyse-framework#AC8 — `grund` ist strukturell auf
    "no-evidence" begrenzt (`Literal`); ein anderer Wert wird abgelehnt."""
    with pytest.raises(ValidationError):
        Uebersprungen(grund="sonstiges", kategorie="risiko")  # type: ignore[arg-type]


# --- AC10: SpinnennetzAchsen/Spinnennetz (Spinnennetz-Datenoutput) ----------


def test_spinnennetz_achsen_akzeptiert_alle_5_kategorien_im_bereich_0_bis_10() -> None:
    """@trace analyse-framework#AC10 — `SpinnennetzAchsen` bildet die 5
    Achsenwerte (0–10) ab, eine je Kategorie."""
    achsen = SpinnennetzAchsen(
        fundamental=8.0, technisch=6.0, qualitativ=7.0, makro=5.0, risiko=9.0
    )
    for kategorie in KATEGORIE_NAMEN:
        assert 0 <= getattr(achsen, kategorie) <= 10


@pytest.mark.parametrize("kategorie", list(KATEGORIE_NAMEN))
def test_spinnennetz_achsen_lehnt_wert_ausserhalb_0_bis_10_ab(kategorie: str) -> None:
    """@trace analyse-framework#AC10 — ein Achsenwert außerhalb 0–10 ist
    strukturell ungültig (anders als `KategorieScores` ist `None` hier
    ebenfalls kein gültiger Wert — eine Spinnennetz-Achse wird nur für
    eine vollständige Analyse gebaut)."""
    basiswerte = {name: 5.0 for name in KATEGORIE_NAMEN}
    basiswerte[kategorie] = 10.01
    with pytest.raises(ValidationError):
        SpinnennetzAchsen(**basiswerte)


def test_spinnennetz_ohne_historischen_durchschnitt() -> None:
    """@trace analyse-framework#AC10 — "Historischer Durchschnitt nicht
    vorhanden (neuer Titel) → Spinnennetz nur mit aktueller Datenreihe"
    (Edge-Cases der Spec): `historischer_durchschnitt` ist optional."""
    achsen = SpinnennetzAchsen(
        fundamental=8.0, technisch=6.0, qualitativ=7.0, makro=5.0, risiko=9.0
    )
    spinnennetz = Spinnennetz(achsen=achsen)
    assert spinnennetz.historischer_durchschnitt is None


def test_spinnennetz_mit_historischem_durchschnitt_als_zweite_datenreihe() -> None:
    """@trace analyse-framework#AC10 — der historische Durchschnitt wird
    als zweite, vollwertige `SpinnennetzAchsen`-Datenreihe geführt."""
    achsen = SpinnennetzAchsen(
        fundamental=8.0, technisch=6.0, qualitativ=7.0, makro=5.0, risiko=9.0
    )
    historisch = SpinnennetzAchsen(
        fundamental=7.0, technisch=6.5, qualitativ=6.0, makro=4.5, risiko=8.0
    )
    spinnennetz = Spinnennetz(achsen=achsen, historischer_durchschnitt=historisch)
    assert spinnennetz.historischer_durchschnitt is not None
    assert spinnennetz.historischer_durchschnitt.fundamental == 7.0
