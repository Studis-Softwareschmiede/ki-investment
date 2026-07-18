"""Tests für das Anlageklassen-Kürzel-Mapping (`app.web.kandidaten
.anlageklassen`, `docs/specs/frontend-cockpit.md` AC15, Story S-072).

Covers (frontend-cockpit): AC15

S-072 Iteration 2 (Review-Suggestion, mitgezogen): deckt den `"?"`-
Fallback für eine unbekannte `asset_class_id` (Datenmodell-Drift-Schutz,
`anlageklasse_kuerzel`-Docstring)."""

from __future__ import annotations

import pytest

from app.web.kandidaten.anlageklassen import ANLAGEKLASSEN_KUERZEL, anlageklasse_kuerzel


@pytest.mark.parametrize("asset_class_id", sorted(ANLAGEKLASSEN_KUERZEL))
def test_anlageklasse_kuerzel_liefert_bekanntes_kuerzel(asset_class_id: int) -> None:
    assert anlageklasse_kuerzel(asset_class_id) == ANLAGEKLASSEN_KUERZEL[asset_class_id]


def test_anlageklasse_kuerzel_liefert_fragezeichen_fuer_unbekannte_id() -> None:
    """Verteidigt gegen Datenmodell-Drift (unbekannte `asset_class_id`),
    ohne die View abstürzen zu lassen."""
    assert anlageklasse_kuerzel(999) == "?"
