"""Blockade-Grund-Label für die Warteliste-View (design.md §7.6 Text/Badge-
Konvention, D3; `docs/specs/frontend-cockpit.md` AC26/AC27).

Die vier Prüfmatrix-Dimensionen (AC26 wörtlich: "Klumpen-/Korrelations-/
Drawdown-/Kelly-Cap-Limit") als stabiler Anzeige-Text — der Blockade-Grund
erscheint laut AC27 "als Text/Badge", Status/Grund nie nur über Farbe
(D3), das Wort ist führend."""

from __future__ import annotations

#: `blockade_grund`-Code (data-model.md §4 `warteliste_eintrag.blockade_
#: grund`) -> Anzeige-Text.
BLOCKADE_GRUND_LABEL: dict[str, str] = {
    "klumpenrisiko": "Klumpenrisiko",
    "korrelation": "Korrelation",
    "drawdown": "Drawdown-Limit",
    "kelly_cap": "Kelly-Cap-Limit",
}


def blockade_grund_label(blockade_grund: str) -> str:
    """Anzeige-Text für einen Blockade-Grund-Code. Liefert den Rohwert für
    einen unbekannten Code — verteidigt gegen Datenmodell-Drift, ohne die
    View abstürzen zu lassen (kein AC verlangt einen Fehlerpfad hier,
    analog `app.web.kandidaten.anlageklassen.anlageklasse_kuerzel`)."""
    return BLOCKADE_GRUND_LABEL.get(blockade_grund, blockade_grund)
