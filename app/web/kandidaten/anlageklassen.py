"""Anlageklassen-Kürzel für den Klassen-Chip (design.md §2.4, C-006;
`docs/specs/frontend-cockpit.md` AC15).

Die 11 Anlageklassen sind bereits fest im Datenmodell geseedet
(`app/db/migrations/versions/b2bd709be080_create_asset_class_table_and_seed_11_.py`,
`AssetClass.id` 1..11, dieselbe Reihenfolge wie design.md §2.4). Dieses
Mapping bildet ausschliesslich das feste Kürzel für die Chip-Anzeige ab —
keine neue Datenquelle, keine DB-Abfrage (reine Anzeige-Konstante, AC2
UI-Boundary gilt ohnehin nicht für ein reines `dict`-Literal ohne Import)."""

from __future__ import annotations

#: `asset_class_id` -> Kürzel (design.md §2.4-Tabelle, gleiche Reihenfolge/
#: IDs wie `ASSET_CLASS_SEED` in der Migration).
ANLAGEKLASSEN_KUERZEL: dict[int, str] = {
    1: "AKT",
    2: "ETF",
    3: "CSH",
    4: "OBL",
    5: "FND",
    6: "IMM",
    7: "CRY",
    8: "ROH",
    9: "INF",
    10: "FX",
    11: "DER",
}


def anlageklasse_kuerzel(asset_class_id: int) -> str:
    """Kürzel einer Anlageklasse für den Klassen-Chip (design.md §2.4).
    Liefert `"?"` für eine unbekannte ID — verteidigt gegen Datenmodell-
    Drift, ohne die View abstürzen zu lassen (kein AC verlangt einen
    Fehlerpfad hier)."""
    return ANLAGEKLASSEN_KUERZEL.get(asset_class_id, "?")
