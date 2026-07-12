"""Tests für die Score-Engine — Berechnungskern (Storys S-009/S-010).

Covers (analyse-framework): AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC9, AC11

`app.domain.scoring.score_engine` deckt den Berechnungskern dieser Storys:
Kategorie-Score (AC1/AC2, inkl. Ausschluss fehlender/ungültiger
Methodenscores AC9), die AC4-Referenz-Verifikation, den Gesamtscore (AC3),
die Signal-Ableitung nach (je Anlageklasse konfigurierbaren) Score-
Schwellen (AC5/AC6), den Risiko-Sanity-Cap (AC7) und Determinismus (AC11).
No-Evidence-No-Trade-Skip (AC8) und Spinnennetz (AC10) sind Nicht-Ziel
dieser Story (S-011) und werden hier nicht getestet.
"""

from __future__ import annotations

import pytest

from app.contracts.analyse_framework import (
    KategorieEingabe,
    Kategoriegewichte,
    KategorieScores,
    MethodeEingabe,
    ScoreSchwellen,
)
from app.domain.scoring.score_engine import (
    berechne_gesamtscore,
    berechne_kategorie_score,
    berechne_kategorie_scores,
    leite_signal_ab,
    wende_risiko_sanity_cap_an,
)


def _methode(methoden_id: str, ranking: int, methodenscore: float | None) -> MethodeEingabe:
    return MethodeEingabe(methoden_id=methoden_id, ranking=ranking, methodenscore=methodenscore)


def test_ac4_referenz_verifikation_fundamental() -> None:
    """@trace analyse-framework#AC1,AC4 — DCF (8, Ranking 9), KGV (7, 7),
    KBV (5, 6): (8×9 + 7×7 + 5×6) / (9+7+6) = 151/22 = 6.86 (2 Dezimalstellen,
    siehe Spec-Präzisierung AC4 — Rechenweg 151/22, nicht 131/22)."""
    methoden = (
        _methode("dcf", 9, 8),
        _methode("kgv", 7, 7),
        _methode("kbv", 6, 5),
    )
    assert berechne_kategorie_score(methoden) == 6.86


def test_ac1_kategorie_score_einfaches_gewichtetes_mittel() -> None:
    """@trace analyse-framework#AC1 — Kategorie-Score ist das Ranking-
    gewichtete Mittel über alle Methoden mit vorhandenem Score."""
    methoden = (_methode("a", 1, 8), _methode("b", 1, 4))
    assert berechne_kategorie_score(methoden) == 6.0


def test_ac2_ranking_bleibt_konstant_methodenscore_aendert_ergebnis() -> None:
    """@trace analyse-framework#AC2 — das Ranking ist der feste,
    klassenspezifische Gewichtungswert; nur der je Analyse neu vergebene
    Methodenscore verändert das Ergebnis bei gleichem Ranking."""
    ranking = 9
    erste_analyse = berechne_kategorie_score((_methode("dcf", ranking, 8),))
    zweite_analyse = berechne_kategorie_score((_methode("dcf", ranking, 5),))

    assert erste_analyse == 8.0
    assert zweite_analyse == 5.0
    assert erste_analyse != zweite_analyse


def test_ac9_fehlender_einzelner_methodenscore_wird_ausgeschlossen_nicht_null() -> None:
    """@trace analyse-framework#AC9 — fehlt innerhalb einer Kategorie nur ein
    einzelner Methodenscore, fließt ausschließlich die vorhandene Methode
    ein (Summierung nur über vorhandene Scores); die fehlende Methode wird
    NICHT als 0 gewertet (deckt A2). Kontrollrechnung: würde `b` als 0
    gezählt, ergäbe sich (8×9 + 0×7)/(9+7) = 4.5 statt 8.0."""
    methoden = (_methode("a", 9, 8), _methode("b", 7, None))
    assert berechne_kategorie_score(methoden) == 8.0


def test_ac9_mehrere_vorhandene_methoden_bei_einer_fehlenden() -> None:
    """@trace analyse-framework#AC9 — bei drei Methoden, von denen eine
    fehlt, fließen die zwei vorhandenen (mit ihrem jeweiligen Ranking) ein:
    (8×9 + 5×6) / (9+6) = 6.8."""
    methoden = (_methode("a", 9, 8), _methode("b", 7, None), _methode("c", 6, 5))
    assert berechne_kategorie_score(methoden) == 6.8


@pytest.mark.parametrize("ungueltiger_score", [0, 0.9, 10.01, 15])
def test_ac2_methodenscore_ausserhalb_1_bis_10_wird_nicht_verrechnet(
    ungueltiger_score: float,
) -> None:
    """@trace analyse-framework#AC2,AC9 — ein Methodenscore außerhalb 1–10
    ist eine ungültige Eingabe (Edge-Cases der Spec) und wird wie ein
    fehlender Score behandelt: nicht verrechnet, nicht als 0 gewertet.
    Kontrollrechnung: nur `b` (5, Ranking 6) fließt ein → 5.0."""
    methoden = (_methode("a", 9, ungueltiger_score), _methode("b", 6, 5))
    assert berechne_kategorie_score(methoden) == 5.0


def test_kategorie_ohne_jeden_vorhandenen_methodenscore_liefert_none() -> None:
    """@trace analyse-framework#AC9 — sind ALLE Methodenscores einer
    Kategorie fehlend (`None`), bleibt Σ(Ranking) der gültigen Teilmenge 0;
    die Kategorie gilt als ohne verwertbare Evidenz (`None`). Das Ranking
    selbst ist über `MethodeEingabe` strukturell auf 1–10 begrenzt (AC2,
    Quelle [[anlageklassen-config]]) — der Edge-Case "Σ(Ranking)=0,
    theoretisch alle Rankings 0" aus der Spec manifestiert sich hier
    dadurch, dass keine Methode einen gültigen Score beisteuert (derselbe
    Code-Pfad, dasselbe Ergebnis `None`). Der Skip-Entscheid für den ganzen
    Titel (No-Evidence-No-Trade, AC8) ist Nicht-Ziel dieser Story."""
    methoden = (_methode("a", 9, None), _methode("b", 7, None))
    assert berechne_kategorie_score(methoden) is None


def test_kategorie_ohne_jede_methode_liefert_none() -> None:
    """@trace analyse-framework#AC9 — eine leere Methodenliste (keine
    Datengrundlage) liefert ebenfalls `None`, denselben Hook wie eine
    Kategorie mit ausschließlich ungültigen/fehlenden Scores."""
    assert berechne_kategorie_score(()) is None


def test_berechne_kategorie_scores_gruppiert_alle_5_kategorien() -> None:
    """@trace analyse-framework#AC1,AC9 — `berechne_kategorie_scores` wendet
    die Formel je der 5 Analysekategorien an; eine nicht gelistete
    Kategorie erscheint als `None` (keine Evidenz)."""
    kategorien = (
        KategorieEingabe(kategorie="fundamental", methoden=(_methode("dcf", 9, 8),)),
        KategorieEingabe(kategorie="technisch", methoden=(_methode("rsi", 5, 6),)),
    )

    ergebnis = berechne_kategorie_scores(kategorien)

    assert ergebnis.fundamental == 8.0
    assert ergebnis.technisch == 6.0
    assert ergebnis.qualitativ is None
    assert ergebnis.makro is None
    assert ergebnis.risiko is None


def test_ac3_gesamtscore_gewichtete_summe_ueber_5_kategorien() -> None:
    """@trace analyse-framework#AC3 — Gesamtscore = Σ(Kategorie-Score ×
    Kategoriegewicht) / 100 (Gewichte als Prozentwerte, Beispiel Aktien
    35/15/20/10/20): (8×35 + 6×15 + 7×20 + 5×10 + 9×20) / 100 = 7.4."""
    kategorie_scores = KategorieScores(fundamental=8, technisch=6, qualitativ=7, makro=5, risiko=9)
    gewichte = Kategoriegewichte(fundamental=35, technisch=15, qualitativ=20, makro=10, risiko=20)

    assert berechne_gesamtscore(kategorie_scores, gewichte) == 7.4


def test_ac3_gesamtscore_liegt_im_bereich_0_bis_10() -> None:
    """@trace analyse-framework#AC3 — bei Kategorie-Scores 0–10 und
    Kategoriegewichten, die sich auf 100 summieren, liegt der Gesamtscore
    ebenfalls im Bereich 0–10 (hier: durchgängig Maximalwerte)."""
    kategorie_scores = KategorieScores(
        fundamental=10, technisch=10, qualitativ=10, makro=10, risiko=10
    )
    gewichte = Kategoriegewichte(fundamental=35, technisch=15, qualitativ=20, makro=10, risiko=20)

    assert berechne_gesamtscore(kategorie_scores, gewichte) == 10.0


def test_ac3_gesamtscore_lehnt_fehlende_kategorie_ab() -> None:
    """@trace analyse-framework#AC3 — fehlt einer der 5 Kategorie-Scores
    (`None`, keine Evidenz), verweigert `berechne_gesamtscore` die
    Berechnung; der Aufrufer muss den Titel vorher überspringen
    (No-Evidence-No-Trade, AC8 — Nicht-Ziel dieser Story, aber die
    Kernfunktion darf keinen falschen Gesamtscore vortäuschen)."""
    kategorie_scores = KategorieScores(
        fundamental=None, technisch=6, qualitativ=7, makro=5, risiko=9
    )
    gewichte = Kategoriegewichte(fundamental=35, technisch=15, qualitativ=20, makro=10, risiko=20)

    with pytest.raises(ValueError, match="fundamental"):
        berechne_gesamtscore(kategorie_scores, gewichte)


def test_ac11_determinismus_kategorie_score() -> None:
    """@trace analyse-framework#AC11 — identische Eingaben liefern
    identische Kategorie-Scores bei wiederholtem Aufruf."""
    methoden = (_methode("dcf", 9, 8), _methode("kgv", 7, 7), _methode("kbv", 6, 5))

    assert berechne_kategorie_score(methoden) == berechne_kategorie_score(methoden)


def test_ac11_determinismus_gesamtscore_und_signal_relevante_kette() -> None:
    """@trace analyse-framework#AC11 — identische Kategorie-Scores und
    Kategoriegewichte liefern zweimal exakt denselben Gesamtscore (keine
    Zeit-/Zufallsabhängigkeit im Berechnungskern)."""
    kategorien = (
        KategorieEingabe(kategorie="fundamental", methoden=(_methode("dcf", 9, 8),)),
        KategorieEingabe(kategorie="technisch", methoden=(_methode("rsi", 5, 6),)),
        KategorieEingabe(kategorie="qualitativ", methoden=(_methode("mgmt", 8, 7),)),
        KategorieEingabe(kategorie="makro", methoden=(_methode("zins", 9, 5),)),
        KategorieEingabe(kategorie="risiko", methoden=(_methode("var", 8, 9),)),
    )
    gewichte = Kategoriegewichte(fundamental=35, technisch=15, qualitativ=20, makro=10, risiko=20)

    erster_lauf = berechne_gesamtscore(berechne_kategorie_scores(kategorien), gewichte)
    zweiter_lauf = berechne_gesamtscore(berechne_kategorie_scores(kategorien), gewichte)

    assert erster_lauf == zweiter_lauf


# --- AC5/AC6: Signal-Ableitung aus den Score-Schwellen ---------------------


@pytest.mark.parametrize(
    ("gesamtscore", "erwartetes_signal"),
    [
        (10.0, "KAUF"),
        (8.0, "KAUF"),  # Untergrenze inklusiv
        (7.9, "BEOBACHTEN"),
        (6.0, "BEOBACHTEN"),  # Untergrenze inklusiv
        (5.9, "HALTEN"),
        (4.0, "HALTEN"),  # Untergrenze inklusiv
        (3.9, "REDUZIEREN"),
        (2.0, "REDUZIEREN"),  # Untergrenze inklusiv
        (1.9, "VERKAUF"),
        (0.0, "VERKAUF"),
    ],
)
def test_ac5_signal_ableitung_default_schwellen_inklusive_untergrenzen(
    gesamtscore: float, erwartetes_signal: str
) -> None:
    """@trace analyse-framework#AC5 — Signal-Ableitung nach den globalen
    Default-Schwellen; die Untergrenzen sind inklusiv (genau 8.0 → KAUF,
    genau 6.0 → BEOBACHTEN, genau 4.0 → HALTEN, genau 2.0 → REDUZIEREN)."""
    assert leite_signal_ab(gesamtscore) == erwartetes_signal


def test_ac6_ohne_klassenspezifische_schwelle_greifen_defaults() -> None:
    """@trace analyse-framework#AC6 — wird keine `schwellen`-Instanz
    übergeben (kein `score_schwellen` gesetzt), gelten dieselben
    Default-Werte wie eine explizit mit `ScoreSchwellen()` gebaute
    Default-Instanz."""
    assert leite_signal_ab(8.0) == leite_signal_ab(8.0, ScoreSchwellen())
    assert leite_signal_ab(7.9, None) == leite_signal_ab(7.9, ScoreSchwellen())


def test_ac6_klassenspezifische_schwelle_ueberschreibt_nur_das_gesetzte_feld() -> None:
    """@trace analyse-framework#AC6 — eine Anlageklasse mit kalibrierter,
    höherer KAUF-Schwelle (9.0) lässt die übrigen Schwellen (beobachten/
    halten/reduzieren) unverändert auf dem AC5-Default."""
    schwellen = ScoreSchwellen(kauf=9.0)

    # 8.5 läge unter Default-KAUF (8.0) nicht mehr, unter der
    # klassenspezifischen Schwelle (9.0) schon: Signal fällt auf
    # BEOBACHTEN zurück statt KAUF.
    assert leite_signal_ab(8.5, schwellen) == "BEOBACHTEN"
    assert leite_signal_ab(9.0, schwellen) == "KAUF"
    # Unveränderte (nicht gesetzte) Schwellen verhalten sich weiterhin wie
    # der AC5-Default.
    assert leite_signal_ab(6.0, schwellen) == "BEOBACHTEN"
    assert leite_signal_ab(4.0, schwellen) == "HALTEN"
    assert leite_signal_ab(2.0, schwellen) == "REDUZIEREN"


def test_ac11_determinismus_signal_ableitung() -> None:
    """@trace analyse-framework#AC11 — identischer Gesamtscore und
    identische Schwellen liefern zweimal exakt dasselbe Signal."""
    schwellen = ScoreSchwellen(kauf=9.0)
    assert leite_signal_ab(8.5, schwellen) == leite_signal_ab(8.5, schwellen)


# --- AC7: Risiko-Sanity-Cap -------------------------------------------------


@pytest.mark.parametrize("signal_vor_cap", ["KAUF", "BEOBACHTEN"])
def test_ac7_sanity_cap_deckelt_kauf_und_beobachten_auf_halten(signal_vor_cap: str) -> None:
    """@trace analyse-framework#AC7 — ist der Risiko-Score < 3 (Default-
    Schwellwert), wird ein rechnerisches KAUF oder BEOBACHTEN auf HALTEN
    gedeckelt und `sanity_cap_angewendet` ist True (deckt A1)."""
    signal, sanity_cap_angewendet = wende_risiko_sanity_cap_an(signal_vor_cap, risiko_score=2.9)

    assert signal == "HALTEN"
    assert sanity_cap_angewendet is True


@pytest.mark.parametrize("signal_vor_cap", ["REDUZIEREN", "VERKAUF"])
def test_ac7_sanity_cap_laesst_reduzieren_und_verkauf_unveraendert(signal_vor_cap: str) -> None:
    """@trace analyse-framework#AC7 — REDUZIEREN und VERKAUF bleiben trotz
    niedrigem Risiko-Score unverändert (nur KAUF/BEOBACHTEN werden
    gedeckelt)."""
    signal, sanity_cap_angewendet = wende_risiko_sanity_cap_an(signal_vor_cap, risiko_score=1.0)

    assert signal == signal_vor_cap
    assert sanity_cap_angewendet is False


def test_ac7_sanity_cap_greift_nicht_bei_risiko_score_exakt_der_schwelle() -> None:
    """@trace analyse-framework#AC7 — der Cap-Schwellwert ist als "< 3"
    definiert; ein Risiko-Score exakt 3.0 (Default-Schwellwert) löst den
    Cap NICHT aus (Grenzfall-Test lt. Schätz-Notiz)."""
    signal, sanity_cap_angewendet = wende_risiko_sanity_cap_an("KAUF", risiko_score=3.0)

    assert signal == "KAUF"
    assert sanity_cap_angewendet is False


def test_ac7_sanity_cap_greift_knapp_unterhalb_der_schwelle() -> None:
    """@trace analyse-framework#AC7 — ein Risiko-Score knapp unterhalb der
    Schwelle (2.99 < 3.0) löst den Cap aus."""
    signal, sanity_cap_angewendet = wende_risiko_sanity_cap_an("BEOBACHTEN", risiko_score=2.99)

    assert signal == "HALTEN"
    assert sanity_cap_angewendet is True


def test_ac7_cap_schwellwert_ist_konfigurierbar() -> None:
    """@trace analyse-framework#AC7 — "Der Cap-Schwellwert 3 ist
    konfigurierbar": ein abweichender `cap_schwelle`-Wert verschiebt, ab
    welchem Risiko-Score der Cap greift."""
    # Mit einer strengeren, klassenspezifischen Schwelle (5.0) greift der
    # Cap bereits bei einem Risiko-Score, der den Default (3.0) nicht
    # ausgelöst hätte.
    signal, sanity_cap_angewendet = wende_risiko_sanity_cap_an(
        "KAUF", risiko_score=4.0, cap_schwelle=5.0
    )

    assert signal == "HALTEN"
    assert sanity_cap_angewendet is True

    # Mit dem Default-Schwellwert hätte derselbe Risiko-Score (4.0) den
    # Cap NICHT ausgelöst.
    unveraendertes_signal, unveraendertes_flag = wende_risiko_sanity_cap_an(
        "KAUF", risiko_score=4.0
    )
    assert unveraendertes_signal == "KAUF"
    assert unveraendertes_flag is False


def test_ac11_determinismus_sanity_cap() -> None:
    """@trace analyse-framework#AC11 — identisches Signal und identischer
    Risiko-Score liefern zweimal exakt dasselbe (Signal,
    sanity_cap_angewendet)-Ergebnis."""
    erster_lauf = wende_risiko_sanity_cap_an("KAUF", risiko_score=2.5)
    zweiter_lauf = wende_risiko_sanity_cap_an("KAUF", risiko_score=2.5)

    assert erster_lauf == zweiter_lauf
