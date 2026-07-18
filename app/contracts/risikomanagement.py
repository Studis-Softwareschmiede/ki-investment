"""Modul-Verträge Depotstrategie-Konfiguration + Gate-Entscheid (Storys
S-043 AC1/AC3/AC4/AC11, S-044 AC2/AC5/AC6/AC12, S-045 AC8/AC9/AC10 und
S-056 AC7, Spec `docs/specs/risikomanagement.md`).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO. Dieses Modul bildet zwei Verträge-Abschnitte
ab:

- "Depotstrategie-Konfiguration: `{ profil, max_einzelposition, max_sektor
  (GICS), max_anlageklasse[1..11], cash_quote, kelly_cap_gesamt }`"
  (`DepotstrategieKonfiguration`, S-043).
- "Output: Gate-Entscheid an das Kauf-&-Verkaufsmodul: `{ entscheid:
  durchwinken | deckeln | blockieren, freigegebene_groesse, begruendung,
  warteliste?: bool }`" (`GateEntscheid`, S-044).

`DepotstrategieKonfiguration` ist der EINZIGE Vertrag, über den das
Risikomanagement-Gate (`app.domain.risikomanagement.gate`) Limits lesen
darf (AC11: "Das Gate bezieht seine Limits ausschliesslich aus der
Depotstrategie und definiert keine eigenen Grenzwerte") — erzeugt von
`app.db.depotstrategie.lade_aktive_depotstrategie()`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

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


#: AC6: die drei möglichen Gate-Entscheide (Main Success Scenario Schritt
#: 5, deckt A1/A2/A3) — "genau einen von drei Entscheiden".
GateEntscheidTyp = Literal["durchwinken", "deckeln", "blockieren"]


class GateEntscheid(BaseModel):
    """AC6/AC7/AC12-Vertrag (S-044, S-056): der Drei-Wege-Entscheid des
    Risikomanagement-Gates je geplantem Kauf (§Verträge "Output").

    `freigegebene_groesse` ist bei `entscheid="durchwinken"` die volle
    geplante Ordergrösse, bei `"deckeln"` das erlaubte Maximum (AC6: "kein
    Rück-Durchlauf ins Position-Sizing" — die Deckelung ist eine einfache
    Kappung, keine Neuberechnung) und bei `"blockieren"` `Decimal("0")`.

    `warteliste` bildet den optionalen AC7-Vertragsteil
    (`{ ..., warteliste?: bool }`) ab: `app.domain.risikomanagement.gate
    .pruefe_kauf_gate` setzt es auf `True`, wenn der Aufrufer per
    `warteliste_bei_blockade=True` den optionalen A2-Wunsch äussert UND der
    Kauf wegen ausgeschöpften Limits blockiert wird (AC7, S-056) — sonst
    (inkl. AC12/E1-Blockaden und dem Ordergrösse-`<=0`-Edge-Case) bleibt es
    `False`. Die eigentliche Warteliste-Mechanik (Persistenz, Re-Prüfung)
    ist laut Spec "Offene Punkte" weiterhin offen (Folge-Story)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entscheid: GateEntscheidTyp
    freigegebene_groesse: Decimal
    begruendung: str = Field(min_length=1)
    warteliste: bool = False
