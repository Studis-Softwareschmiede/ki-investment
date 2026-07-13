"""Handelsplattform-Stammdaten: Plattform-Auswahl je Anlageklasse + erwartete
Kosten an Sizing (Story S-017).

Deckt `docs/specs/ausfuehrung-paper.md` AC10/AC11:

- **AC10 (Plattform-Auswahl je Anlageklasse anhand von Stammdaten):**
  `waehle_plattform_fuer_anlageklasse()` liest ausschliesslich
  `PlatformAssetClass` (data-model.md §1, `bevorzugt`-Flag = die
  Verträge-Konfiguration "Plattform-Zuordnung je Anlageklasse ist
  Konfiguration"). Auswahl-Regel: gibt es fuer eine Anlageklasse genau EINE
  konfigurierte Plattform, wird sie ohne weitere Bedingung gewaehlt (keine
  Konkurrenz moeglich); gibt es mehrere, muss GENAU EINE davon
  `bevorzugt=True` tragen — sonst ist die Konfiguration unvollstaendig
  (keine bevorzugte Plattform) oder widerspruechlich (mehrere bevorzugte)
  und `waehle_plattform_fuer_anlageklasse()` weist dies mit
  `PlattformAuswahlError` zurueck, statt eine der Kandidaten-Plattformen
  stillschweigend zu raten.

- **AC11 (erwartete Kosten Courtage + Spread + geschätzte Slippage an
  Sizing-Module, Pre-Trade-Kalkulation):** `berechne_erwartete_kosten()`
  waehlt zunaechst die zustaendige Plattform (AC10) und berechnet daraus
  `ErwarteteKosten` (`app.contracts.ausfuehrung_paper`). **Prozent-
  Konvention** (data-model.md-Praezisierung, siehe dort): `courtage_pct`/
  `typ_spread_pct`/`erwartete_slippage_pct_default` sind Prozent-Zahlen
  (z.B. `0.05` = 0.05 %, analog `category_weight.weight_pct`) — NICHT
  Anteile 0-1; jede der drei Groessen wird daher durch 100 geteilt, bevor
  sie mit `order_wert_chf` multipliziert wird.
  `courtage_chf = order_wert_chf * courtage_pct / 100` (fehlt
  `courtage_pct` in den Referenzdaten, wird mit 0 gerechnet — die
  Referenzzeile ist dann noch nicht vollstaendig konfiguriert, kein Grund
  den Aufruf abzulehnen), `spread_kosten_chf` analog aus `typ_spread_pct`,
  `geschaetzte_slippage_chf` aus dem konfigurierbaren, provisorischen
  `Settings.erwartete_slippage_pct_default` (AC9s eigentliches
  Fill-Slippage-Modell ist eine eigene Folge-Story, S-049 — diese
  Pre-Trade-Schätzung ist bewusst ein einfacher, konfigurierbarer
  Platzhalter dafuer, kein Fill-Modell).

  **Edge-Case "Mindestgebühr-Effekt"** (Verträge/Edge-Cases: "Order kleiner
  als die Mindest-Ordergrösse/Mindestgebühr-Schwelle → das Modul meldet
  dies zurück (Mindestgebühr-Effekt), statt einen unwirtschaftlichen Trade
  auszuführen"): `courtage_effektiv_chf = max(courtage_chf,
  mindestgebuehr_chf)`, `mindestgebuehr_greift=True` genau dann, wenn die
  Mindestgebühr die reine Prozent-Courtage übersteigt. Die Entscheidung, ob
  ein Trade bei `mindestgebuehr_greift=True` trotzdem ausgeführt oder als
  unwirtschaftlich verworfen wird, liegt beim (künftigen) Sizing-Modul-
  Konsumenten — Nicht-Ziel dieser Story (die Sizing-Module existieren noch
  nicht, Cold-Start).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts.ausfuehrung_paper import ErwarteteKosten, PlattformStammdaten
from app.db.models import PlatformAssetClass, TradingPlatform


class PlattformAuswahlError(ValueError):
    """Die Plattform-Zuordnung (`PlatformAssetClass`) fuer eine Anlageklasse
    ist unvollstaendig (keine konfigurierte Plattform, oder mehrere ohne
    genau eine `bevorzugt=True`-Kennzeichnung, AC10)."""


def _waehle_zuordnung(
    session: Session, *, asset_class_id: int
) -> tuple[PlatformAssetClass, TradingPlatform]:
    """Interne Auswahl-Logik (AC10), von `waehle_plattform_fuer_anlageklasse()`
    UND `berechne_erwartete_kosten()` genutzt (eine einzige Query/Regel
    statt Duplikat).

    Regel: genau ein konfigurierter Kandidat -> dieser wird gewaehlt
    (unabhaengig vom `bevorzugt`-Flag, keine Konkurrenz moeglich). Mehrere
    Kandidaten -> genau einer davon muss `bevorzugt=True` sein, sonst
    `PlattformAuswahlError` (weder 0 noch >1 bevorzugte Plattformen sind
    eine eindeutige Konfiguration).
    """
    zeilen = session.execute(
        select(PlatformAssetClass, TradingPlatform)
        .join(TradingPlatform, PlatformAssetClass.platform_id == TradingPlatform.id)
        .where(PlatformAssetClass.asset_class_id == asset_class_id)
    ).all()

    if not zeilen:
        raise PlattformAuswahlError(
            f"Keine Handelsplattform fuer Anlageklasse {asset_class_id} konfiguriert."
        )

    if len(zeilen) == 1:
        return zeilen[0]

    bevorzugte = [(z, p) for z, p in zeilen if z.bevorzugt]
    if len(bevorzugte) != 1:
        raise PlattformAuswahlError(
            f"Anlageklasse {asset_class_id} hat {len(zeilen)} konfigurierte Plattformen, "
            f"aber {len(bevorzugte)} davon sind als 'bevorzugt' markiert (erwartet genau 1)."
        )
    return bevorzugte[0]


def waehle_plattform_fuer_anlageklasse(
    session: Session, *, asset_class_id: int
) -> PlattformStammdaten:
    """AC10: waehlt die zustaendige Handelsplattform fuer `asset_class_id`
    anhand der `PlatformAssetClass`-Referenzdaten (Auswahl-Regel siehe
    `_waehle_zuordnung`)."""
    zuordnung, plattform = _waehle_zuordnung(session, asset_class_id=asset_class_id)

    return PlattformStammdaten(
        plattform_id=plattform.id,
        plattform_name=plattform.name,
        asset_class_id=asset_class_id,
        gebuehrenmodell=plattform.gebuehrenmodell,
        mindestgebuehr_chf=plattform.mindestgebuehr_chf,
        typischer_spread_pct=zuordnung.typ_spread_pct,
    )


def berechne_erwartete_kosten(
    session: Session,
    *,
    asset_class_id: int,
    order_wert_chf: Decimal,
    geschaetzte_slippage_pct: Decimal | None = None,
) -> ErwarteteKosten:
    """AC11: liefert die erwarteten Kosten (Courtage + Spread + geschätzte
    Slippage) fuer eine Order der Groesse `order_wert_chf` in
    `asset_class_id` — Pre-Trade-Kalkulation an die (künftigen)
    Sizing-Module.

    `geschaetzte_slippage_pct` ueberschreibt optional den konfigurierten
    Default (`Settings.erwartete_slippage_pct_default`, AC9-Platzhalter) —
    als Prozent-Zahl (z.B. `Decimal("0.05")` = 0.05 %, siehe Modul-Docstring
    "Prozent-Konvention"), nicht als Anteil 0-1.

    Raises:
        PlattformAuswahlError: wenn AC10 (Plattform-Auswahl) fuer
            `asset_class_id` keine eindeutige Plattform ermitteln kann.
    """
    # Plattform-Auswahl (AC10) — eine einzige Query via `_waehle_zuordnung`.
    zuordnung, plattform = _waehle_zuordnung(session, asset_class_id=asset_class_id)
    stammdaten = PlattformStammdaten(
        plattform_id=plattform.id,
        plattform_name=plattform.name,
        asset_class_id=asset_class_id,
        gebuehrenmodell=plattform.gebuehrenmodell,
        mindestgebuehr_chf=plattform.mindestgebuehr_chf,
        typischer_spread_pct=zuordnung.typ_spread_pct,
    )
    courtage_pct = zuordnung.courtage_pct

    slippage_pct = (
        Decimal(str(geschaetzte_slippage_pct))
        if geschaetzte_slippage_pct is not None
        else Decimal(str(get_settings().erwartete_slippage_pct_default))
    )
    spread_pct = stammdaten.typischer_spread_pct or Decimal("0")
    courtage_pct = courtage_pct or Decimal("0")

    # Prozent-Konvention: courtage_pct/spread_pct/slippage_pct sind
    # Prozent-Zahlen (0.05 = 0.05 %, siehe Modul-Docstring) -> durch 100
    # teilen, um den Multiplikator zu erhalten.
    _hundert = Decimal("100")
    courtage_chf = order_wert_chf * courtage_pct / _hundert
    spread_kosten_chf = order_wert_chf * spread_pct / _hundert
    geschaetzte_slippage_chf = order_wert_chf * slippage_pct / _hundert

    courtage_effektiv_chf = max(courtage_chf, stammdaten.mindestgebuehr_chf)
    mindestgebuehr_greift = stammdaten.mindestgebuehr_chf > courtage_chf

    gesamtkosten_chf = courtage_effektiv_chf + spread_kosten_chf + geschaetzte_slippage_chf

    return ErwarteteKosten(
        plattform_id=stammdaten.plattform_id,
        plattform_name=stammdaten.plattform_name,
        asset_class_id=asset_class_id,
        order_wert_chf=order_wert_chf,
        courtage_chf=courtage_chf,
        mindestgebuehr_chf=stammdaten.mindestgebuehr_chf,
        courtage_effektiv_chf=courtage_effektiv_chf,
        mindestgebuehr_greift=mindestgebuehr_greift,
        spread_kosten_chf=spread_kosten_chf,
        geschaetzte_slippage_chf=geschaetzte_slippage_chf,
        gesamtkosten_chf=gesamtkosten_chf,
    )


__all__ = [
    "PlattformAuswahlError",
    "waehle_plattform_fuer_anlageklasse",
    "berechne_erwartete_kosten",
]
