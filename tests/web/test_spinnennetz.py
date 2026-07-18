"""Tests für die Spinnennetz-Geometrie (`app.web.kandidaten.spinnennetz`,
Story S-072, `docs/specs/frontend-cockpit.md` AC15).

Covers (frontend-cockpit): AC15

Substanzielle Geometrie-Tests (Winkel-/Radien-Berechnung als reine
Funktionen) statt nur "SVG existiert" — deckt design.md §8.1 wörtlich:
5 Achsen im Uhrzeigersinn ab −90° im 72°-Abstand, feste Kategorie-
Reihenfolge, radiale Skala 0–10, Kaufstärke-Polygon nur bei vollständigen
Daten (E3/BR-005-Präzisierung, kein fabrizierter Polygon-Punkt für eine
fehlende Kategorie)."""

from __future__ import annotations

import math

import pytest

from app.web.kandidaten.spinnennetz import (
    GITTERRINGE,
    Punkt,
    achsen_winkel_grad,
    berechne_spinnennetz_geometrie,
    score_zu_radius,
    spinnennetz_aria_label,
)

_VOLLSTAENDIGE_SCORES = {
    "fundamental": 8.0,
    "technisch": 7.0,
    "qualitativ": 6.0,
    "makro": 5.0,
    "risiko": 9.0,
}


def test_achsen_winkel_grad_folgt_design_spec_theta_i() -> None:
    """@trace frontend-cockpit#AC15 — θ_i = −90° + i·72° (design.md §8.1),
    5 Achsen ab oben im Uhrzeigersinn."""
    erwartet = [-90.0, -18.0, 54.0, 126.0, 198.0]
    for index, winkel_erwartet in enumerate(erwartet):
        assert achsen_winkel_grad(index) == pytest.approx(winkel_erwartet)


def test_score_zu_radius_linear_skala_0_bis_10() -> None:
    """@trace frontend-cockpit#AC15 — r = R · s/10 (design.md §8.1)."""
    assert score_zu_radius(0.0, 100.0) == pytest.approx(0.0)
    assert score_zu_radius(10.0, 100.0) == pytest.approx(100.0)
    assert score_zu_radius(5.0, 100.0) == pytest.approx(50.0)
    # Nicht-runder Wert (python/R14-Ethos: runde Werte allein beweisen die
    # Linearität nicht robust genug).
    assert score_zu_radius(3.3, 100.0) == pytest.approx(33.0)


def test_score_zu_radius_klemmt_ausserhalb_0_bis_10() -> None:
    """@trace frontend-cockpit#AC15 — Verteidigung gegen Werte leicht
    ausserhalb 0..10 (`KategorieScores` hat keine `ge/le`-Constraint)."""
    assert score_zu_radius(15.0, 100.0) == pytest.approx(100.0)
    assert score_zu_radius(-3.0, 100.0) == pytest.approx(0.0)


def test_gitterringe_konstante_matcht_design_spec() -> None:
    """design.md §8.1: "Gitterringe bei 2/4/6/8/10"."""
    assert GITTERRINGE == (2, 4, 6, 8, 10)


def test_geometrie_achsen_reihenfolge_ist_fest() -> None:
    """@trace frontend-cockpit#AC15 — feste Kategorie-Reihenfolge
    Fundamental/Technisch/Qualitativ/Makro/Risiko (C-007)."""
    geometrie = berechne_spinnennetz_geometrie(_VOLLSTAENDIGE_SCORES)
    kategorien = [achse.kategorie for achse in geometrie.achsen]
    assert kategorien == ["fundamental", "technisch", "qualitativ", "makro", "risiko"]


def test_geometrie_achsen_winkel_und_punkte_numerisch_konsistent() -> None:
    """Ein Achsen-Endpunkt wird manuell (mit `math.cos/sin`) nachgerechnet
    — deckt tatsächliche Koordinatenberechnung, nicht nur Struktur."""
    mittelpunkt = Punkt(0.0, 0.0)
    geometrie = berechne_spinnennetz_geometrie(
        _VOLLSTAENDIGE_SCORES, mittelpunkt=mittelpunkt, aussenradius=100.0
    )
    # Achse 1 = "technisch", θ_1 = -18°.
    technisch = geometrie.achsen[1]
    winkel_rad = math.radians(-18.0)
    erwartet_x = 100.0 * math.cos(winkel_rad)
    erwartet_y = 100.0 * math.sin(winkel_rad)
    assert technisch.ende.x == pytest.approx(erwartet_x)
    assert technisch.ende.y == pytest.approx(erwartet_y)
    # score=7.0 -> radius = 70.0
    assert technisch.score_punkt is not None
    assert technisch.score_punkt.x == pytest.approx(70.0 * math.cos(winkel_rad))
    assert technisch.score_punkt.y == pytest.approx(70.0 * math.sin(winkel_rad))


def test_geometrie_vollstaendige_scores_baut_kaufstaerke_polygon() -> None:
    """@trace frontend-cockpit#AC15 — Kaufstärke-Fläche als Polygon der 5
    Punkte (design.md §8.1), wenn alle 5 Kategorien einen Score haben."""
    geometrie = berechne_spinnennetz_geometrie(_VOLLSTAENDIGE_SCORES)
    assert geometrie.kaufstaerke_polygon is not None
    assert len(geometrie.kaufstaerke_polygon) == 5
    for achse, punkt in zip(geometrie.achsen, geometrie.kaufstaerke_polygon, strict=True):
        assert achse.score_punkt == punkt


def test_geometrie_fehlende_kategorie_baut_keinen_kaufstaerke_polygon() -> None:
    """@trace frontend-cockpit#AC15 — deckt E3/BR-005: fehlt eine
    Kategorie, wird KEIN fabrizierter Polygon-Punkt gezeichnet (Spec-
    Präzisierung `docs/specs/frontend-cockpit.md` Edge-Cases). Die Achse
    selbst (Linie/Gitter) bleibt trotzdem vorhanden."""
    scores = dict(_VOLLSTAENDIGE_SCORES)
    scores["risiko"] = None
    geometrie = berechne_spinnennetz_geometrie(scores)

    assert geometrie.kaufstaerke_polygon is None
    risiko_achse = geometrie.achsen[4]
    assert risiko_achse.kategorie == "risiko"
    assert risiko_achse.score is None
    assert risiko_achse.score_punkt is None
    # Andere Achsen bleiben vollständig berechnet.
    fundamental_achse = geometrie.achsen[0]
    assert fundamental_achse.score == pytest.approx(8.0)
    assert fundamental_achse.score_punkt is not None


def test_gitterringe_radien_folgen_score_skala() -> None:
    """@trace frontend-cockpit#AC15 — jeder Gitterring liegt bei
    `score_zu_radius(ringscore, R)` je Achse."""
    geometrie = berechne_spinnennetz_geometrie(_VOLLSTAENDIGE_SCORES, aussenradius=100.0)
    ring_scores = [ring for ring, _punkte in geometrie.gitterringe]
    assert ring_scores == [2, 4, 6, 8, 10]

    ring_10 = dict(geometrie.gitterringe)[10]
    ring_2 = dict(geometrie.gitterringe)[2]
    assert len(ring_10) == 5
    # Ring 10 liegt exakt auf dem Aussenradius, Ring 2 bei 1/5 davon.
    for punkt_10, punkt_2, achse in zip(ring_10, ring_2, geometrie.achsen, strict=True):
        abstand_10 = math.hypot(
            punkt_10.x - geometrie.mittelpunkt.x, punkt_10.y - geometrie.mittelpunkt.y
        )
        abstand_2 = math.hypot(
            punkt_2.x - geometrie.mittelpunkt.x, punkt_2.y - geometrie.mittelpunkt.y
        )
        assert abstand_10 == pytest.approx(100.0)
        assert abstand_2 == pytest.approx(20.0)
        assert achse.kategorie is not None  # nur zur Zip-Längenprüfung


def test_geometrie_respektiert_uebergebenen_mittelpunkt() -> None:
    """Nicht-Ursprungs-Mittelpunkt (Template nutzt `STANDARD_MITTELPUNKT_*`,
    130/130) — Achsen-Endpunkte verschieben sich um den Mittelpunkt-Offset."""
    zentrum = Punkt(130.0, 130.0)
    geometrie = berechne_spinnennetz_geometrie(
        _VOLLSTAENDIGE_SCORES, mittelpunkt=zentrum, aussenradius=100.0
    )
    fundamental = geometrie.achsen[0]  # θ_0 = -90° -> (0, -R) relativ zum Zentrum
    assert fundamental.ende.x == pytest.approx(130.0)
    assert fundamental.ende.y == pytest.approx(30.0)


def test_spinnennetz_aria_label_nennt_alle_5_kategorien_mit_titel() -> None:
    """@trace frontend-cockpit#AC15 — design.md §8.1 A11y-Pflicht:
    aria-label "Analyse <Titel>: Fundamental x, Technisch y, …"."""
    label = spinnennetz_aria_label("AAPL", _VOLLSTAENDIGE_SCORES)
    assert label == (
        "Analyse AAPL: Fundamental 8.0, Technisch 7.0, Qualitativ 6.0, Makro 5.0, Risiko 9.0"
    )


def test_spinnennetz_aria_label_weist_fehlende_kategorie_als_fehlend_aus() -> None:
    """@trace frontend-cockpit#AC15 — deckt E3/BR-005: fehlende Kategorie
    im aria-label als "fehlend" ausgewiesen, nie als 0/geschätzter Wert."""
    scores = dict(_VOLLSTAENDIGE_SCORES)
    scores["risiko"] = None
    label = spinnennetz_aria_label("AAPL", scores)
    assert "Risiko fehlend" in label
    assert "Risiko 0" not in label
