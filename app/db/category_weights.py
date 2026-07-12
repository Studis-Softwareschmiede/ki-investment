"""App-seitige Validierung der Kategoriegewichte (BR-101, data-model.md §1).

Ergänzt den DB-seitigen deferred Constraint-Trigger aus der Migration
`2da446925bbc_create_analysis_category_and_category_.py` um eine schnelle,
dialekt-unabhängige Vorab-Prüfung (data-model.md §10 BR-101: "Enforced by:
App-Validierung + DB-Trigger/Deferred-Check") — für künftige Config-Schreibpfade
(Admin-API, Re-Seed-Tooling), die eine ungültige Gewichtung ablehnen sollen,
bevor überhaupt eine DB-Transaktion versucht wird (AC7).
"""

from __future__ import annotations

from decimal import Decimal

from app.db.models import ANALYSIS_CATEGORY_CODES

# data-model.md §1 `analysis_category`: 5 fixe Kategorie-Codes — einzige
# Quelle ist `app.db.models.ANALYSIS_CATEGORY_CODES` (kein Duplikat).
CATEGORY_CODES = ANALYSIS_CATEGORY_CODES

# BR-101: Σ weight_pct je Klasse = 100 (±0.01).
_TOLERANCE = Decimal("0.01")
_EXPECTED_SUM = Decimal("100")


class InvalidCategoryWeightsError(ValueError):
    """Eine Kategoriegewichtung summiert sich nicht auf exakt 100 % (BR-101, AC7)."""


def validate_category_weights(
    weights: dict[str, Decimal | float | int],
    *,
    tolerance: Decimal = _TOLERANCE,
) -> None:
    """Weist eine Kategoriegewichtung zurück, deren fünf Gewichte nicht exakt
    100 % ergeben (AC7, deckt E1 der Spec).

    `weights` bildet Kategorie-Code -> Gewicht (%) ab. Erwartet werden genau
    die 5 Kategorien aus `CATEGORY_CODES` — fehlende oder zusätzliche
    Kategorien sind ebenfalls eine ungültige Konfiguration.

    Raises:
        InvalidCategoryWeightsError: wenn die Kategorie-Menge nicht exakt
            `CATEGORY_CODES` entspricht, oder wenn die Summe der Gewichte um
            mehr als `tolerance` von 100 abweicht.
    """
    given_codes = set(weights.keys())
    expected_codes = set(CATEGORY_CODES)
    if given_codes != expected_codes:
        missing = expected_codes - given_codes
        unexpected = given_codes - expected_codes
        raise InvalidCategoryWeightsError(
            "Kategoriegewichtung deckt nicht exakt die 5 Analysekategorien ab "
            f"(fehlend: {sorted(missing) or '–'}, unerwartet: {sorted(unexpected) or '–'})."
        )

    total = sum((Decimal(str(value)) for value in weights.values()), start=Decimal("0"))
    if abs(total - _EXPECTED_SUM) > tolerance:
        raise InvalidCategoryWeightsError(
            f"Kategoriegewichte summieren sich auf {total} statt 100 (Toleranz ±{tolerance})."
        )
