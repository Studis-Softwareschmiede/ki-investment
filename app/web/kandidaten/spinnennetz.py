"""Spinnennetz-/Radar-Geometrie (design.md §8.1, `docs/specs/
frontend-cockpit.md` AC15) — reine, deterministische Projektion der 5
Kategorie-Scores auf ein Polygon.

Bewusst getrennt von der Jinja2-Rendering-Schicht (`app/web/templates/
partials/kandidaten/_spinnennetz_svg.html`): dieses Modul berechnet
ausschliesslich Koordinaten (Winkel/Radien/Punkte) als reine, unit-testbare
Funktionen ohne Markup-/String-Bau — das SVG selbst entsteht über Jinja2's
Auto-Escape im Template (html/R02: kein Markup-String-Bau in Python).

Geometrie exakt nach design.md §8.1:
- 5 Achsen im Uhrzeigersinn ab oben (−90°), Winkelabstand 72°:
  θ_i = −90° + i·72°. Feste Kategorie-Reihenfolge Fundamental, Technisch,
  Qualitativ, Makro, Risiko — importiert aus `app.contracts
  .analyse_framework.KATEGORIE_NAMEN` (dieselbe Quelle wie die Domäne,
  keine zweite Reihenfolge-Definition).
- Radiale Skala 0–10: r = R · s/10 (R = Aussenradius).
- Gitterringe bei 2/4/6/8/10.
- **Kaufstärke-Fläche nur, wenn ALLE 5 Kategorien einen Score haben**
  (Spec-Präzisierung zu E3/BR-005, siehe `docs/specs/frontend-cockpit.md`
  Edge-Cases: eine fehlende Kategorie wird NIE durch einen fabrizierten
  Polygon-Punkt ersetzt — konsistent mit `app.contracts.analyse_framework
  .SpinnennetzAchsen`, die strukturell nur für eine vollständige Analyse
  gebaut wird, und mit dem No-Evidence-No-Trade-Verhalten, das
  `gesamtscore`/`signal` in diesem Fall ohnehin auf `None` setzt — siehe
  `app.domain.scoring.ports.KandidatDetail`)."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from app.contracts.analyse_framework import KATEGORIE_NAMEN, KategorieName

#: design.md §8.1: "Gitterringe bei 2/4/6/8/10".
GITTERRINGE: tuple[int, ...] = (2, 4, 6, 8, 10)

#: design.md §8.1: "5 Achsen ... Winkelabstand 72°" (360° / 5 Kategorien).
_WINKELSCHRITT_GRAD = 360.0 / len(KATEGORIE_NAMEN)
#: design.md §8.1: "im Uhrzeigersinn ab oben (−90°)".
_START_WINKEL_GRAD = -90.0
_MAX_SCORE = 10.0

#: Layout-Vorgabe für das server-gerenderte SVG (Template + `ui.py` teilen
#: sich diese Konstanten, damit Geometrie und `viewBox` konsistent bleiben).
STANDARD_MITTELPUNKT_X = 130.0
STANDARD_MITTELPUNKT_Y = 130.0
STANDARD_AUSSENRADIUS = 100.0
STANDARD_LABEL_ABSTAND = 20.0
STANDARD_VIEWBOX = "0 0 260 260"


@dataclass(frozen=True)
class Punkt:
    x: float
    y: float


@dataclass(frozen=True)
class Achse:
    """Eine der 5 Spinnennetz-Achsen (design.md §8.1). `score`/`score_punkt`
    sind `None`, wenn die Kategorie keine Datengrundlage hat (→ BR-005) —
    die Achse selbst (Linie/Label/Gitter) wird trotzdem immer gezeichnet."""

    kategorie: KategorieName
    winkel_grad: float
    ende: Punkt
    label: Punkt
    score: float | None
    score_punkt: Punkt | None


@dataclass(frozen=True)
class SpinnennetzGeometrie:
    mittelpunkt: Punkt
    aussenradius: float
    achsen: tuple[Achse, ...]
    #: `(ringscore, 5 Punkte)` je Gitterring (design.md §8.1: 2/4/6/8/10).
    gitterringe: tuple[tuple[int, tuple[Punkt, ...]], ...]
    #: `None`, wenn mindestens eine Kategorie ohne Score ist (BR-005/E3) —
    #: dann wird KEIN fabrizierter Polygon-Punkt gezeichnet.
    kaufstaerke_polygon: tuple[Punkt, ...] | None


def achsen_winkel_grad(index: int) -> float:
    """θ_i = −90° + i·72° (design.md §8.1) — Achse `index` (0..4)."""
    return _START_WINKEL_GRAD + index * _WINKELSCHRITT_GRAD


def score_zu_radius(score: float, aussenradius: float, max_score: float = _MAX_SCORE) -> float:
    """r = R · s/10 (design.md §8.1). `score` wird defensiv gegen
    `[0, max_score]` geklemmt — `KategorieScores` hat (anders als
    `SpinnennetzAchsen`) keine `ge=0,le=10`-Constraint; die Geometrie
    verteidigt sich hier selbst gegen einen leicht ausserhalb liegenden
    Wert, statt eine eigene Validierungsebene vom Aufrufer zu verlangen."""
    geklemmt = max(0.0, min(score, max_score))
    return aussenradius * geklemmt / max_score


def _punkt_auf_kreis(mittelpunkt: Punkt, radius: float, winkel_grad: float) -> Punkt:
    winkel_rad = math.radians(winkel_grad)
    return Punkt(
        x=mittelpunkt.x + radius * math.cos(winkel_rad),
        y=mittelpunkt.y + radius * math.sin(winkel_rad),
    )


def berechne_spinnennetz_geometrie(
    kategorie_scores: Mapping[str, float | None],
    *,
    mittelpunkt: Punkt | None = None,
    aussenradius: float = STANDARD_AUSSENRADIUS,
    label_abstand: float = STANDARD_LABEL_ABSTAND,
) -> SpinnennetzGeometrie:
    """Baut die volle Geometrie (Achsen, Gitterringe, Kaufstärke-Polygon)
    aus den 5 Kategorie-Scores. `kategorie_scores` folgt der Struktur von
    `app.contracts.analyse_framework.KategorieScores` (Kategorie-Name →
    Score oder `None` bei fehlender Evidenz, → BR-005)."""
    zentrum = mittelpunkt or Punkt(STANDARD_MITTELPUNKT_X, STANDARD_MITTELPUNKT_Y)

    achsen: list[Achse] = []
    for index, kategorie in enumerate(KATEGORIE_NAMEN):
        winkel = achsen_winkel_grad(index)
        ende = _punkt_auf_kreis(zentrum, aussenradius, winkel)
        label = _punkt_auf_kreis(zentrum, aussenradius + label_abstand, winkel)
        score = kategorie_scores.get(kategorie)
        score_punkt = None
        if score is not None:
            radius = score_zu_radius(score, aussenradius)
            score_punkt = _punkt_auf_kreis(zentrum, radius, winkel)
        achsen.append(
            Achse(
                kategorie=kategorie,
                winkel_grad=winkel,
                ende=ende,
                label=label,
                score=score,
                score_punkt=score_punkt,
            )
        )

    gitterringe = tuple(
        (
            ring,
            tuple(
                _punkt_auf_kreis(
                    zentrum, score_zu_radius(ring, aussenradius), achsen_winkel_grad(i)
                )
                for i in range(len(KATEGORIE_NAMEN))
            ),
        )
        for ring in GITTERRINGE
    )

    vollstaendig = all(achse.score_punkt is not None for achse in achsen)
    kaufstaerke_polygon: tuple[Punkt, ...] | None = None
    if vollstaendig:
        kaufstaerke_polygon = tuple(
            achse.score_punkt for achse in achsen if achse.score_punkt is not None
        )

    return SpinnennetzGeometrie(
        mittelpunkt=zentrum,
        aussenradius=aussenradius,
        achsen=tuple(achsen),
        gitterringe=gitterringe,
        kaufstaerke_polygon=kaufstaerke_polygon,
    )


def spinnennetz_aria_label(titel: str, kategorie_scores: Mapping[str, float | None]) -> str:
    """design.md §8.1 A11y-Pflicht: '`aria-label` "Analyse <Titel>:
    Fundamental x, Technisch y, …"'. Fehlende Kategorien (→ BR-005) werden
    als "fehlend" ausgewiesen, nie als 0/geschätzter Wert (E3)."""
    teile = []
    for kategorie in KATEGORIE_NAMEN:
        score = kategorie_scores.get(kategorie)
        wert = f"{score:.1f}" if score is not None else "fehlend"
        teile.append(f"{kategorie.capitalize()} {wert}")
    return f"Analyse {titel}: " + ", ".join(teile)
