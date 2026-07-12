"""Tests fuer die App-seitige Kategoriegewicht-Validierung (Story S-004).

Covers (anlageklassen-config): AC6, AC7

`app.db.category_weights.validate_category_weights` ist die schnelle,
dialekt-unabhaengige App-Validierungsschicht aus BR-101
("Enforced by: App-Validierung + DB-Trigger/Deferred-Check", data-model.md
§10) — deckt AC7 / E1 ("Eine Kategoriegewichtung, deren fünf Gewichte für
eine Klasse nicht exakt 100 % ergeben, wird als ungültig zurückgewiesen und
nicht wirksam") ohne DB-Verbindung ab. Der DB-seitige deferred
Constraint-Trigger (zweite Durchsetzungsschicht) ist in
`tests/db/test_category_weight_migration.py` dokumentiert und wurde manuell
gegen die lokale Compose-Postgres-Instanz verifiziert (Coder-Self-Test).
AC6 wird zusätzlich durch `test_category_codes_constant_has_exactly_5_entries`
gedeckt (die App-seitige Kategorie-Konstante muss exakt die 5
Analysekategorien aus AC6 abbilden).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.category_weights import (
    CATEGORY_CODES,
    InvalidCategoryWeightsError,
    validate_category_weights,
)

VALID_WEIGHTS = {
    "fundamental": 35,
    "technisch": 15,
    "qualitativ": 20,
    "makro": 10,
    "risiko_quant": 20,
}


def test_accepts_weights_summing_to_exactly_100() -> None:
    """@trace anlageklassen-config#AC7 — eine gültige Gewichtung (Σ = 100)
    wird nicht zurückgewiesen."""
    validate_category_weights(VALID_WEIGHTS)  # keine Exception


@pytest.mark.parametrize("total_offset", [1, -1, 5, -100])
def test_rejects_weights_not_summing_to_100(total_offset: int) -> None:
    """@trace anlageklassen-config#AC7 — eine Kategoriegewichtung, deren fünf
    Gewichte nicht exakt 100 % ergeben, wird als ungültig zurückgewiesen
    (deckt E1)."""
    invalid = dict(VALID_WEIGHTS)
    invalid["makro"] = invalid["makro"] + total_offset
    with pytest.raises(InvalidCategoryWeightsError):
        validate_category_weights(invalid)


def test_rejects_missing_category() -> None:
    """@trace anlageklassen-config#AC7 — eine unvollständige Gewichtung
    (fehlende Kategorie) ist ebenfalls ungültig, auch wenn die verbleibenden
    Gewichte zufällig 100 ergeben."""
    incomplete = {"fundamental": 40, "technisch": 20, "qualitativ": 20, "makro": 20}
    with pytest.raises(InvalidCategoryWeightsError):
        validate_category_weights(incomplete)


def test_rejects_unexpected_category() -> None:
    """@trace anlageklassen-config#AC7 — eine unbekannte Kategorie macht die
    Gewichtung ungültig, selbst wenn die Summe über alle Einträge 100
    ergibt."""
    invalid = dict(VALID_WEIGHTS)
    invalid.pop("risiko_quant")
    invalid["unbekannt"] = 20
    with pytest.raises(InvalidCategoryWeightsError):
        validate_category_weights(invalid)


def test_accepts_within_default_tolerance() -> None:
    """@trace anlageklassen-config#AC7 — BR-101 erlaubt eine Rundungs-Toleranz
    von ±0.01 um 100."""
    almost = dict(VALID_WEIGHTS)
    almost["makro"] = Decimal("10.005")
    validate_category_weights(almost)


def test_rejects_just_outside_default_tolerance() -> None:
    """@trace anlageklassen-config#AC7 — eine Abweichung knapp über der
    ±0.01-Toleranz wird zurückgewiesen."""
    almost = dict(VALID_WEIGHTS)
    almost["makro"] = Decimal("10.02")
    with pytest.raises(InvalidCategoryWeightsError):
        validate_category_weights(almost)


def test_category_codes_constant_has_exactly_5_entries() -> None:
    """@trace anlageklassen-config#AC6 — die App-seitige Kategorie-Konstante
    deckt exakt die 5 Analysekategorien aus AC6 ab."""
    assert set(CATEGORY_CODES) == {
        "fundamental",
        "technisch",
        "qualitativ",
        "makro",
        "risiko_quant",
    }
