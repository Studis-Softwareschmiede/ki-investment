"""Modul-Verträge Handelsplattform-Stammdaten & erwartete Kosten (Story
S-017, Spec `docs/specs/ausfuehrung-paper.md` AC10/AC11).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO. Dieses Modul bildet den Verträge-Abschnitt
"Handelsplattform-Stammdaten (Referenzdaten): je Plattform/Anlageklasse
`{ gebuehrenmodell, mindestgebuehr, typischer_spread }` → erwartete Kosten
an Position-/Exit-Sizing" ab, soweit diese Story (AC10, AC11) ihn betrifft:

- `PlattformStammdaten` — die AC10-Referenzdaten EINER Plattform/Anlageklasse-
  Kombination (`{ gebuehrenmodell, mindestgebuehr, typischer_spread }`),
  ergaenzt um die Plattform-Identität für den Konsumenten.
- `ErwarteteKosten` — der AC11-Vertrag "erwartete Kosten (Courtage + Spread +
  geschätzte Slippage) an die Sizing-Module (Pre-Trade-Kalkulation)", inkl.
  des Edge-Case-Flags `mindestgebuehr_greift` ("Order kleiner als die
  Mindest-Ordergrösse/Mindestgebühr-Schwelle → das Modul meldet dies zurück
  (Mindestgebühr-Effekt), statt einen unwirtschaftlichen Trade auszuführen" —
  die eigentliche Entscheidung "Trade trotzdem ausführen oder verwerfen"
  liegt beim (künftigen) Sizing-Modul-Konsumenten, Nicht-Ziel dieser Story).

Die Position-/Exit-Sizing-Module selbst existieren in dieser Codebasis noch
nicht (Cold-Start, spätere Story) — `app.db.trading_platform` ist der
erzeugende Endpunkt dieser Verträge, kein Konsument ist Teil dieser Story.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PlattformStammdaten(BaseModel):
    """AC10-Referenzdaten EINER Plattform/Anlageklasse-Kombination:
    `{ gebuehrenmodell, mindestgebuehr, typischer_spread }`, ergaenzt um die
    Plattform-/Anlageklassen-Identität."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plattform_id: uuid.UUID
    plattform_name: str = Field(min_length=1)
    asset_class_id: int = Field(ge=1, le=11)
    gebuehrenmodell: str | None = None
    mindestgebuehr_chf: Decimal
    typischer_spread_pct: Decimal | None = None


class ErwarteteKosten(BaseModel):
    """AC11-Vertrag: erwartete Kosten (Courtage + Spread + geschätzte
    Slippage) an die Sizing-Module (Pre-Trade-Kalkulation).

    `courtage_chf` ist die reine Prozent-Berechnung (`order_wert_chf *
    courtage_pct`), `courtage_effektiv_chf` bereits mit der
    Mindestgebühr-Untergrenze verrechnet (`max(courtage_chf,
    mindestgebuehr_chf)`) — `mindestgebuehr_greift=True` markiert den
    Edge-Case, in dem die Mindestgebühr die eigentliche Prozent-Courtage
    übersteigt (Verträge/Edge-Cases: "Mindestgebühr-Effekt").
    `gesamtkosten_chf` ist die Summe aus `courtage_effektiv_chf`,
    `spread_kosten_chf` und `geschaetzte_slippage_chf`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plattform_id: uuid.UUID
    plattform_name: str = Field(min_length=1)
    asset_class_id: int = Field(ge=1, le=11)
    order_wert_chf: Decimal = Field(gt=0)
    courtage_chf: Decimal
    mindestgebuehr_chf: Decimal
    courtage_effektiv_chf: Decimal
    mindestgebuehr_greift: bool
    spread_kosten_chf: Decimal
    geschaetzte_slippage_chf: Decimal
    gesamtkosten_chf: Decimal
