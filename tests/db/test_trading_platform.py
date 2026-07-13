"""Tests fuer die Plattform-Auswahl + erwartete-Kosten-Berechnung (Story
S-017), `app.db.trading_platform`.

Covers (ausfuehrung-paper): AC10, AC11

- AC10 (Plattform-Auswahl je Anlageklasse anhand von Stammdaten,
  Plattform-Zuordnung ist Konfiguration): `waehle_plattform_fuer_
  anlageklasse()` — Einzelkandidat ohne `bevorzugt`, Mehrfachkandidaten mit
  genau einem `bevorzugt=True`, sowie die beiden Fehlerfaelle (keine
  konfigurierte Plattform; mehrere Kandidaten ohne eindeutiges
  `bevorzugt`-Flag: 0 oder >1).
- AC11 (erwartete Kosten Courtage + Spread + geschätzte Slippage an
  Sizing-Module, Pre-Trade-Kalkulation): `berechne_erwartete_kosten()` —
  Happy-Path-Summe, Prozent-Konvention (0.05 = 0.05 %, nicht Anteil 0-1),
  fehlende `courtage_pct`/`typ_spread_pct` werden als 0 behandelt, der
  konfigurierbare Slippage-Default (`Settings.
  erwartete_slippage_pct_default`) sowie sein optionaler Override, und der
  Edge-Case "Mindestgebühr-Effekt" (Verträge/Edge-Cases: "Order kleiner als
  die Mindest-Ordergrösse/Mindestgebühr-Schwelle → das Modul meldet dies
  zurück (Mindestgebühr-Effekt)") ueber `mindestgebuehr_greift` +
  `courtage_effektiv_chf`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import Base
from app.db.models import AssetClass, PlatformAssetClass, TradingPlatform
from app.db.trading_platform import (
    PlattformAuswahlError,
    berechne_erwartete_kosten,
    waehle_plattform_fuer_anlageklasse,
)

AKTIEN_ID = 1


def _session_mit_aktien() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        AssetClass(id=AKTIEN_ID, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True)
    )
    session.commit()
    return session


def _plattform(session: Session, *, name: str, mindestgebuehr_chf: str = "0") -> uuid.UUID:
    platform_id = uuid.uuid4()
    session.add(
        TradingPlatform(id=platform_id, name=name, mindestgebuehr_chf=Decimal(mindestgebuehr_chf))
    )
    session.commit()
    return platform_id


def test_waehlt_einzige_konfigurierte_plattform_ohne_bevorzugt_flag() -> None:
    """@trace ausfuehrung-paper#AC10 — genau ein konfigurierter Kandidat
    wird gewaehlt, auch ohne `bevorzugt=True` (keine Konkurrenz moeglich)."""
    session = _session_mit_aktien()
    platform_id = _plattform(session, name="Interactive Brokers")
    session.add(
        PlatformAssetClass(
            platform_id=platform_id,
            asset_class_id=AKTIEN_ID,
            courtage_pct=Decimal("0.05"),
            typ_spread_pct=Decimal("0.02"),
        )
    )
    session.commit()

    stammdaten = waehle_plattform_fuer_anlageklasse(session, asset_class_id=AKTIEN_ID)
    assert stammdaten.plattform_id == platform_id
    assert stammdaten.plattform_name == "Interactive Brokers"


def test_waehlt_bevorzugte_plattform_unter_mehreren_kandidaten() -> None:
    """@trace ausfuehrung-paper#AC10 — bei mehreren konfigurierten
    Plattformen entscheidet ausschliesslich das `bevorzugt`-Flag (die
    Verträge-Konfiguration "Plattform-Zuordnung je Anlageklasse")."""
    session = _session_mit_aktien()
    ibkr_id = _plattform(session, name="Interactive Brokers")
    kraken_id = _plattform(session, name="Kraken")
    session.add(
        PlatformAssetClass(
            platform_id=ibkr_id, asset_class_id=AKTIEN_ID, courtage_pct=Decimal("0.05")
        )
    )
    session.add(
        PlatformAssetClass(
            platform_id=kraken_id,
            asset_class_id=AKTIEN_ID,
            courtage_pct=Decimal("0.10"),
            bevorzugt=True,
        )
    )
    session.commit()

    stammdaten = waehle_plattform_fuer_anlageklasse(session, asset_class_id=AKTIEN_ID)
    assert stammdaten.plattform_id == kraken_id
    assert stammdaten.plattform_name == "Kraken"


def test_keine_konfigurierte_plattform_wirft_auswahl_error() -> None:
    """@trace ausfuehrung-paper#AC10 — eine Anlageklasse ohne jede
    `PlatformAssetClass`-Zeile ist eine unvollstaendige Konfiguration, kein
    stillschweigendes Fehlen."""
    session = _session_mit_aktien()
    with pytest.raises(PlattformAuswahlError):
        waehle_plattform_fuer_anlageklasse(session, asset_class_id=AKTIEN_ID)


def test_mehrere_kandidaten_ohne_bevorzugte_plattform_wirft_auswahl_error() -> None:
    """@trace ausfuehrung-paper#AC10 — mehrere Kandidaten, aber KEINER als
    `bevorzugt=True` markiert, ist eine mehrdeutige Konfiguration."""
    session = _session_mit_aktien()
    ibkr_id = _plattform(session, name="Interactive Brokers")
    kraken_id = _plattform(session, name="Kraken")
    session.add(PlatformAssetClass(platform_id=ibkr_id, asset_class_id=AKTIEN_ID))
    session.add(PlatformAssetClass(platform_id=kraken_id, asset_class_id=AKTIEN_ID))
    session.commit()

    with pytest.raises(PlattformAuswahlError):
        waehle_plattform_fuer_anlageklasse(session, asset_class_id=AKTIEN_ID)


def test_mehrere_kandidaten_mit_zwei_bevorzugten_wirft_auswahl_error() -> None:
    """@trace ausfuehrung-paper#AC10 — mehrere Kandidaten mit MEHR als
    einer `bevorzugt=True`-Zeile ist ebenfalls mehrdeutig (widerspruechliche
    Konfiguration)."""
    session = _session_mit_aktien()
    ibkr_id = _plattform(session, name="Interactive Brokers")
    kraken_id = _plattform(session, name="Kraken")
    session.add(PlatformAssetClass(platform_id=ibkr_id, asset_class_id=AKTIEN_ID, bevorzugt=True))
    session.add(PlatformAssetClass(platform_id=kraken_id, asset_class_id=AKTIEN_ID, bevorzugt=True))
    session.commit()

    with pytest.raises(PlattformAuswahlError):
        waehle_plattform_fuer_anlageklasse(session, asset_class_id=AKTIEN_ID)


def test_erwartete_kosten_happy_path_summiert_courtage_spread_slippage() -> None:
    """@trace ausfuehrung-paper#AC11 — erwartete Kosten = Courtage + Spread
    + geschätzte Slippage; Prozent-Konvention (0.05 = 0.05 %, durch 100
    geteilt vor der Multiplikation mit dem Order-Wert)."""
    session = _session_mit_aktien()
    platform_id = _plattform(session, name="Interactive Brokers", mindestgebuehr_chf="1")
    session.add(
        PlatformAssetClass(
            platform_id=platform_id,
            asset_class_id=AKTIEN_ID,
            courtage_pct=Decimal("0.10"),
            typ_spread_pct=Decimal("0.02"),
        )
    )
    session.commit()

    kosten = berechne_erwartete_kosten(
        session,
        asset_class_id=AKTIEN_ID,
        order_wert_chf=Decimal("10000"),
        geschaetzte_slippage_pct=Decimal("0.05"),
    )

    assert kosten.courtage_chf == Decimal("10.00")
    assert kosten.spread_kosten_chf == Decimal("2.00")
    assert kosten.geschaetzte_slippage_chf == Decimal("5.00")
    assert kosten.mindestgebuehr_greift is False
    assert kosten.courtage_effektiv_chf == Decimal("10.00")
    assert kosten.gesamtkosten_chf == Decimal("17.00")
    assert kosten.plattform_id == platform_id


def test_erwartete_kosten_nutzt_konfigurierten_slippage_default_ohne_override() -> None:
    """@trace ausfuehrung-paper#AC11 — ohne expliziten Override greift
    `Settings.erwartete_slippage_pct_default` (provisorischer,
    konfigurierbarer Default)."""
    session = _session_mit_aktien()
    platform_id = _plattform(session, name="Interactive Brokers")
    session.add(
        PlatformAssetClass(
            platform_id=platform_id,
            asset_class_id=AKTIEN_ID,
            courtage_pct=Decimal("0.05"),
            typ_spread_pct=Decimal("0.02"),
        )
    )
    session.commit()

    kosten = berechne_erwartete_kosten(
        session, asset_class_id=AKTIEN_ID, order_wert_chf=Decimal("10000")
    )

    default_pct = Decimal(str(get_settings().erwartete_slippage_pct_default))
    erwartet = (Decimal("10000") * default_pct / Decimal("100")).quantize(Decimal("0.01"))
    assert kosten.geschaetzte_slippage_chf.quantize(Decimal("0.01")) == erwartet


def test_erwartete_kosten_behandelt_fehlende_courtage_und_spread_als_null() -> None:
    """@trace ausfuehrung-paper#AC11 — eine Referenzzeile ohne
    `courtage_pct`/`typ_spread_pct` (noch nicht vollstaendig konfiguriert)
    wird mit 0 gerechnet statt den Aufruf abzulehnen."""
    session = _session_mit_aktien()
    platform_id = _plattform(session, name="Interactive Brokers")
    session.add(PlatformAssetClass(platform_id=platform_id, asset_class_id=AKTIEN_ID))
    session.commit()

    kosten = berechne_erwartete_kosten(
        session,
        asset_class_id=AKTIEN_ID,
        order_wert_chf=Decimal("10000"),
        geschaetzte_slippage_pct=Decimal("0"),
    )

    assert kosten.courtage_chf == Decimal("0")
    assert kosten.spread_kosten_chf == Decimal("0")


def test_mindestgebuehr_effekt_greift_bei_kleiner_order() -> None:
    """@trace ausfuehrung-paper#AC11 — Edge-Case "Mindestgebühr-Effekt":
    uebersteigt die Mindestgebühr die reine Prozent-Courtage, meldet das
    Modul dies zurueck (`mindestgebuehr_greift=True`,
    `courtage_effektiv_chf` = Mindestgebühr statt Prozent-Courtage) statt
    einen unwirtschaftlichen Trade unbemerkt durchzureichen."""
    session = _session_mit_aktien()
    platform_id = _plattform(session, name="Interactive Brokers", mindestgebuehr_chf="5")
    session.add(
        PlatformAssetClass(
            platform_id=platform_id,
            asset_class_id=AKTIEN_ID,
            courtage_pct=Decimal("0.05"),
            typ_spread_pct=Decimal("0.02"),
        )
    )
    session.commit()

    kosten = berechne_erwartete_kosten(
        session,
        asset_class_id=AKTIEN_ID,
        order_wert_chf=Decimal("100"),
        geschaetzte_slippage_pct=Decimal("0"),
    )

    assert kosten.courtage_chf == Decimal("0.05")
    assert kosten.mindestgebuehr_chf == Decimal("5")
    assert kosten.mindestgebuehr_greift is True
    assert kosten.courtage_effektiv_chf == Decimal("5")
    assert kosten.gesamtkosten_chf == Decimal("5") + Decimal("0.02")


def test_erwartete_kosten_ohne_konfigurierte_plattform_wirft_auswahl_error() -> None:
    """@trace ausfuehrung-paper#AC11 — ohne AC10-Plattform-Auswahl kann
    keine Kostenkalkulation stattfinden; der Fehler wird durchgereicht,
    nicht verschluckt."""
    session = _session_mit_aktien()
    with pytest.raises(PlattformAuswahlError):
        berechne_erwartete_kosten(session, asset_class_id=AKTIEN_ID, order_wert_chf=Decimal("1000"))
