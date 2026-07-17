"""Modul-Vertrag Position-Sizing-Kern (Story S-039, Spec
`docs/specs/sizing.md` AC1/AC2/AC3/AC4/AC7).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet den
**Kelly-Kern**-Ausschnitt des Verträge-Abschnitts "Konfiguration:
Kelly-Fraktion je Anlageklasse, Trade-Cap %, Trade-Minimum für
Kelly-Schärfung, ..." sowie einen Teil des "Position-Sizing Output"
(`eingesetzte_kelly_fraktion`, `risiko_pct`, `verworfen?`) ab.

`ordergroesse` (absolute Geldsumme) und `titel_id`-Pass-Through in den
vollen Output-Vertrag fehlen hier bewusst: sie setzen eine Kapitalbasis
und die Pre-Trade-Kostenkalkulation voraus (AC5/AC6 der Spec) — beides
ist NICHT Teil dieser Story ("Position-Sizing-Kern: Kelly-Formel,
Fraktionen, hartes Cap, Scharfschaltung", ohne Kosten-/Mindestgrössen-
Prüfung). Dieses Modul liefert ausschliesslich den **Risiko-Anteil des
Kapitals** (`risiko_pct`, 0–1) als Prozentsatz; eine Folgestory
kombiniert das mit Kapitalbasis + Kosten zur absoluten `ordergroesse`.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class KellyFraktionsKonfiguration(BaseModel):
    """AC2/AC3/AC4: die konfigurierbaren Sizing-Parameter (Verträge:
    "Kelly-Fraktion je Anlageklasse, Trade-Cap %, Trade-Minimum für
    Kelly-Schärfung") — alle Werte sind Defaults, provisorisch,
    konfigurierbar (Spec-Formulierung).

    `fraktion_volatil` ist zugleich die Obergrenze der für volatile
    Anlageklassen eingesetzten Fraktion (AC2: "Quarter-Kelly wirkt
    zugleich als Obergrenze der eingesetzten Fraktion") — ein Aufrufer
    kann diesen Wert nach unten konfigurieren, aber
    `bestimme_konfigurierte_fraktion` deckelt ihn zusätzlich hart auf
    `QUARTER_KELLY_OBERGRENZE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: AC2: Standard-Fraktion (Half-Kelly) für nicht-volatile Anlageklassen.
    fraktion_standard: Decimal = Field(default=Decimal("0.5"), gt=0)
    #: AC2: Fraktion für volatile Anlageklassen (z.B. Krypto, Quarter-Kelly).
    fraktion_volatil: Decimal = Field(default=Decimal("0.25"), gt=0)
    #: AC3: hartes Cap auf das Risiko je Trade (Spec-Bereich 1–2 %, als
    #: Anteil 0–1, nicht Prozentpunkte 0–100).
    trade_cap_pct: Decimal = Field(default=Decimal("0.02"), gt=0)
    #: AC4: Mindestzahl abgeschlossener Simulations-Trades, ab der Kelly
    #: "scharf" geschaltet wird (Spec-Bereich 50–100).
    kelly_min_trades: int = Field(default=100, ge=0)
    #: A2/AC4: konservative Fixed-Fractional-Ersatzgrösse, solange Kelly
    #: nicht scharf ist.
    fixed_fractional_pct: Decimal = Field(default=Decimal("0.01"), gt=0)


class PositionSizingErgebnis(BaseModel):
    """AC1/AC2/AC3/AC4-Ausschnitt des "Position-Sizing Output"-Vertrags:
    `{ titel_id, eingesetzte_kelly_fraktion, risiko_pct, verworfen? }`
    (ohne `ordergroesse`, siehe Moduldocstring).

    `eingesetzte_kelly_fraktion` ist die rohe Kelly-Fraktion `f*` (AC1),
    multipliziert mit der nach AC2 bestimmten Fraktion (Half-/Quarter-
    Kelly) — **vor** dem AC3-Cap; `None`, solange Kelly nicht scharf
    geschaltet ist (AC4, Fixed-Fractional-Rückfall greift, kein
    Kelly-Wert "eingesetzt").

    `risiko_pct` ist der **finale** eingesetzte Anteil des Kapitals (0–1)
    nach Anwendung des AC3-Hartcaps (gilt für beide Zweige — Kelly UND
    Fixed-Fractional, siehe `position_sizing`-Moduldocstring) — die Basis,
    aus der eine Folgestory zusammen mit einer Kapitalbasis + Kosten
    (AC5/AC6) die absolute `ordergroesse` bildet.

    `verworfen` trägt `"kelly-negativ"`, wenn `f*` ≤ 0 ist (AC1, deckt
    E1: "negatives Kelly → kein Trade") — in diesem Fall ist `risiko_pct`
    `0`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    eingesetzte_kelly_fraktion: Decimal | None = None
    risiko_pct: Decimal = Field(ge=0)
    kelly_scharf: bool
    verworfen: str | None = None


__all__ = ["KellyFraktionsKonfiguration", "PositionSizingErgebnis"]
