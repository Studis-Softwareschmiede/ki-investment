"""Modul-Vertrag Depotstrategie-Konfiguration (Story S-043, Spec
`docs/specs/risikomanagement.md` AC1/AC3/AC4/AC11).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO. Dieses Modul bildet den Verträge-Abschnitt
"Depotstrategie-Konfiguration: `{ profil, max_einzelposition, max_sektor
(GICS), max_anlageklasse[1..11], cash_quote, kelly_cap_gesamt }`" ab
(`docs/specs/risikomanagement.md` §Verträge).

`DepotstrategieKonfiguration` ist der EINZIGE Vertrag, über den ein
künftiges Risikomanagement-Gate (AC5-AC10, ausserhalb dieser Story) Limits
lesen darf (AC11: "Das Gate bezieht seine Limits ausschliesslich aus der
Depotstrategie und definiert keine eigenen Grenzwerte") — erzeugt von
`app.db.depotstrategie.lade_aktive_depotstrategie()`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DepotstrategieKonfiguration(BaseModel):
    """AC1/AC11-Vertrag: die vollständige, aktuell aktive Depotstrategie-
    Konfiguration.

    `max_anlageklasse_pct` bildet `asset_class_id -> max_klasse_pct` ab
    (Vertragsfeld `max_anlageklasse[1..11]`) — enthält nur die Klassen, für
    die tatsächlich ein `PortfolioClassLimit` konfiguriert ist (AC4 seedet
    nur Krypto konkret, siehe `app.db.models.PortfolioClassLimit`-Docstring);
    eine fehlende Klasse bedeutet "kein Klassen-Limit konfiguriert", nicht
    "Limit 0".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    portfolio_strategy_id: uuid.UUID
    risk_profile_name: str = Field(min_length=1)
    max_einzelposition_pct: Decimal
    max_sektor_pct: Decimal
    cash_quote_ziel_pct: Decimal
    gesamt_exposure_cap_pct: Decimal
    max_anlageklasse_pct: dict[int, Decimal] = Field(default_factory=dict)
