"""Tests für das dringlichkeitsbasierte Exit-Sizing (Story S-042) +
Feintuning (Story S-055).

Covers (sizing): AC8, AC9, AC10, AC11, AC12

`app.domain.sizing.exit_sizing.bestimme_exit_order` deckt AC8 (Hard-Exit
-> sofort/`stop_market`, Soft-Exit -> gestaffelt/`limit`, primär nach der
Dringlichkeit des `SellSignal`) sowie den Grenzfall einer ungültigen
`position_menge`. AC10 (TWAP-Schwelle) und AC11 (3-4-Tranchen-Zerlegung +
Abstands-Trigger) werden am selben Aufruf geprüft, AC9
(Limit-Anteil-Betriebskennzahl) über die separate Aggregations-Funktion
`berechne_limit_anteil_kpi`. AC12 (kein Risikomanagement-Gate dazwischen)
wird strukturell geprüft: die Funktion nimmt keine Depotstrategie-/
Limit-Daten entgegen (Signatur-Introspektion) — der Import-Guard-Beleg
(kein `app.contracts.risikomanagement`-/`app.db.depotstrategie`-Import)
liegt in `tests/architecture/test_exit_sizing_umgeht_risikomanagement.py`.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.contracts.analyse_pipelines import Dringlichkeit, SellSignal
from app.contracts.sizing import ExitSizingKonfiguration, Verkaufsauftrag
from app.domain.sizing.exit_sizing import berechne_limit_anteil_kpi, bestimme_exit_order


def _sell_signal(dringlichkeit: Dringlichkeit) -> SellSignal:
    return SellSignal(
        titel_id="AAA",
        dringlichkeit=dringlichkeit,
        ausloeser="news_katalysator",
        rohwerte={},
        zeitstempel=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_ac8_hard_exit_verkauft_sofort_die_gesamte_position_per_stop_market() -> None:
    """@trace sizing#AC8 — Hard-Exit: sofort die gesamte Position, Order-
    Typ Stop-Market (Edge-Cases: kritischer Not-Ausstieg -> Stop-Market,
    nicht Stop-Limit)."""
    auftrag = bestimme_exit_order(_sell_signal("hard"), position_menge=Decimal("100"))

    assert auftrag.titel_id == "AAA"
    assert auftrag.menge == Decimal("100")
    assert auftrag.tranchen == (Decimal("100"),)
    assert auftrag.order_typ == "stop_market"
    assert auftrag.ausfuehrungsprofil == "sofort"
    assert auftrag.preis is None
    assert auftrag.tranchen_trigger is None


def test_ac8_hard_exit_ignoriert_twap_schwelle_trotz_grosser_position() -> None:
    """@trace sizing#AC8,AC10 — Hard-Exit bleibt immer `stop_market`/
    Einzel-Tranche, selbst wenn `tageshandelsvolumen` die AC10-TWAP-
    Schwelle deutlich überschreiten würde (Dringlichkeit "sofort" ist
    mit TWAP unvereinbar, siehe Moduldocstring)."""
    auftrag = bestimme_exit_order(
        _sell_signal("hard"),
        position_menge=Decimal("100"),
        tageshandelsvolumen=Decimal("100"),
    )

    assert auftrag.order_typ == "stop_market"
    assert auftrag.tranchen == (Decimal("100"),)


def test_ac8_soft_exit_ist_gestaffelt_per_limit_default() -> None:
    """@trace sizing#AC8 — Soft-Exit: gestaffelt, Order-Typ Limit als
    Default."""
    auftrag = bestimme_exit_order(_sell_signal("soft"), position_menge=Decimal("100"))

    assert auftrag.titel_id == "AAA"
    assert auftrag.menge == Decimal("100")
    assert auftrag.order_typ == "limit"
    assert auftrag.ausfuehrungsprofil == "gestaffelt"
    assert auftrag.preis is None


@pytest.mark.parametrize("position_menge", [Decimal("0"), Decimal("-1")])
def test_ac8_ungueltige_position_menge_wirft(position_menge: Decimal) -> None:
    """@trace sizing#AC8 — `position_menge <= 0` ist keine gültige, noch
    offene Position zum Verkauf."""
    with pytest.raises(ValueError):
        bestimme_exit_order(_sell_signal("hard"), position_menge=position_menge)


def test_ac9_limit_anteil_kpi_faellt_unter_ziel_bei_zu_vielen_stop_market_orders() -> None:
    """@trace sizing#AC9 — Limit-Anteil-Betriebskennzahl: bei 18 von 20
    Ausführungen (90 %) unterhalb des Default-Ziels (95 %) meldet die KPI
    `ziel_erreicht=False`."""
    auftraege = [bestimme_exit_order(_sell_signal("soft"), position_menge=Decimal("10"))] * 18
    auftraege += [bestimme_exit_order(_sell_signal("hard"), position_menge=Decimal("10"))] * 2

    kpi = berechne_limit_anteil_kpi(auftraege)

    assert kpi.anzahl_gesamt == 20
    assert kpi.anzahl_limit == 18
    assert kpi.limit_anteil == Decimal("0.9")
    assert kpi.ziel == Decimal("0.95")
    assert kpi.ziel_erreicht is False


def test_ac9_limit_anteil_kpi_erreicht_ziel_bei_ausreichendem_limit_anteil() -> None:
    """@trace sizing#AC9 — 19 von 20 Ausführungen (95 %) erreichen exakt
    das Default-Ziel — `ziel_erreicht=True` bei exakter Übereinstimmung."""
    auftraege = [bestimme_exit_order(_sell_signal("soft"), position_menge=Decimal("10"))] * 19
    auftraege += [bestimme_exit_order(_sell_signal("hard"), position_menge=Decimal("10"))]

    kpi = berechne_limit_anteil_kpi(auftraege)

    assert kpi.limit_anteil == Decimal("0.95")
    assert kpi.ziel_erreicht is True


def test_ac9_limit_anteil_kpi_ohne_auftraege_ist_vakuos_wahr() -> None:
    """@trace sizing#AC9 — keine Ausführungen: `limit_anteil=1`,
    `ziel_erreicht=True` (kein Datenpunkt verletzt das Ziel)."""
    kpi = berechne_limit_anteil_kpi([])

    assert kpi.anzahl_gesamt == 0
    assert kpi.limit_anteil == Decimal(1)
    assert kpi.ziel_erreicht is True


def test_ac9_limit_anteil_kpi_zaehlt_twap_nicht_als_limit() -> None:
    """@trace sizing#AC9 — `order_typ == "twap"` zählt nicht als
    Limit-Order (eigenständiger Order-Typ, siehe Vertrag)."""
    twap_auftrag = bestimme_exit_order(
        _sell_signal("soft"),
        position_menge=Decimal("100"),
        tageshandelsvolumen=Decimal("100"),
    )
    assert twap_auftrag.order_typ == "twap"

    kpi = berechne_limit_anteil_kpi([twap_auftrag])

    assert kpi.anzahl_gesamt == 1
    assert kpi.anzahl_limit == 0
    assert kpi.limit_anteil == Decimal("0")


@pytest.mark.parametrize(
    ("position_menge", "tageshandelsvolumen", "erwarteter_order_typ"),
    [
        (Decimal("9"), Decimal("100"), "limit"),
        (Decimal("10"), Decimal("100"), "twap"),
        (Decimal("11"), Decimal("100"), "twap"),
    ],
)
def test_ac10_twap_schwelle_grenzfaelle(
    position_menge: Decimal, tageshandelsvolumen: Decimal, erwarteter_order_typ: str
) -> None:
    """@trace sizing#AC10 — Default-Schwelle 10 % des Handelsvolumens:
    unterhalb bleibt `"limit"`, exakt an bzw. über der Schwelle wird
    `"twap"` (Grenzfall: erreicht die Schwelle löst bereits aus)."""
    auftrag = bestimme_exit_order(
        _sell_signal("soft"),
        position_menge=position_menge,
        tageshandelsvolumen=tageshandelsvolumen,
    )
    assert auftrag.order_typ == erwarteter_order_typ


def test_ac10_ohne_tageshandelsvolumen_bleibt_limit_default() -> None:
    """@trace sizing#AC10 — fehlt `tageshandelsvolumen` (kein
    Datenpunkt), bleibt das S-042-Verhalten `"limit"` unverändert."""
    auftrag = bestimme_exit_order(_sell_signal("soft"), position_menge=Decimal("1000000"))
    assert auftrag.order_typ == "limit"


def test_ac10_ungueltiges_tageshandelsvolumen_wirft() -> None:
    """@trace sizing#AC10 — `tageshandelsvolumen <= 0` ist kein gültiger
    Volumen-Datenpunkt."""
    with pytest.raises(ValueError):
        bestimme_exit_order(
            _sell_signal("soft"), position_menge=Decimal("10"), tageshandelsvolumen=Decimal("0")
        )


def test_ac11_default_zerlegt_in_drei_tranchen_ohne_rundungsverlust() -> None:
    """@trace sizing#AC11 — Default-Tranchenzahl 3, Summe der Tranchen ==
    volle Menge (kein Rundungsverlust bei nicht glatt teilbaren Beträgen)."""
    auftrag = bestimme_exit_order(_sell_signal("soft"), position_menge=Decimal("100"))

    assert len(auftrag.tranchen) == 3
    assert sum(auftrag.tranchen) == Decimal("100")
    assert auftrag.tranchen[0] == auftrag.tranchen[1]


def test_ac11_konfigurierbare_tranchenzahl_vier_ohne_rundungsverlust() -> None:
    """@trace sizing#AC11 — konfigurierte Tranchenzahl 4 (Spec-Obergrenze),
    weiterhin ohne Rundungsverlust."""
    auftrag = bestimme_exit_order(
        _sell_signal("soft"),
        position_menge=Decimal("10"),
        konfiguration=ExitSizingKonfiguration(anzahl_tranchen=4),
    )

    assert len(auftrag.tranchen) == 4
    assert sum(auftrag.tranchen) == Decimal("10")


def test_ac11_zeitbasierter_abstands_trigger_ist_default() -> None:
    """@trace sizing#AC11 — Default-Abstands-Auslöser ist zeitbasiert mit
    dem konfigurierten `tranchen_zeitabstand`, `weitere_bewegung_pct`
    bleibt `None`."""
    auftrag = bestimme_exit_order(_sell_signal("soft"), position_menge=Decimal("100"))

    assert auftrag.tranchen_trigger is not None
    assert auftrag.tranchen_trigger.art == "zeitbasiert"
    assert auftrag.tranchen_trigger.zeitabstand == timedelta(days=1)
    assert auftrag.tranchen_trigger.weitere_bewegung_pct is None


def test_ac11_ereignisbasierter_abstands_trigger_konfigurierbar() -> None:
    """@trace sizing#AC11 — konfiguriert auf ereignisbasiert liefert der
    Trigger `weitere_bewegung_pct` statt `zeitabstand`."""
    konfiguration = ExitSizingKonfiguration(
        tranchen_abstand_art="ereignisbasiert",
        tranchen_weitere_bewegung_pct=Decimal("0.08"),
    )
    auftrag = bestimme_exit_order(
        _sell_signal("soft"), position_menge=Decimal("100"), konfiguration=konfiguration
    )

    assert auftrag.tranchen_trigger is not None
    assert auftrag.tranchen_trigger.art == "ereignisbasiert"
    assert auftrag.tranchen_trigger.weitere_bewegung_pct == Decimal("0.08")
    assert auftrag.tranchen_trigger.zeitabstand is None


def test_ac12_bestimme_exit_order_nimmt_keine_risikomanagement_daten_entgegen() -> None:
    """@trace sizing#AC12 — strukturell abgesichert: die Signatur von
    `bestimme_exit_order` enthält ausschliesslich `sell_signal`,
    `position_menge` sowie die AC9/AC10/AC11-Feintuning-Parameter
    `tageshandelsvolumen`/`konfiguration` — keine Depotstrategie-/
    Limit-/Risiko-Gate-Parameter, über die ein Risikomanagement-Ergebnis
    hereinkommen könnte."""
    parameter = set(inspect.signature(bestimme_exit_order).parameters)
    assert parameter == {
        "sell_signal",
        "position_menge",
        "tageshandelsvolumen",
        "konfiguration",
    }


def test_ac12_verkaufsauftrag_dto_hat_keine_risikomanagement_felder() -> None:
    """@trace sizing#AC12 — auch das erweiterte `Verkaufsauftrag`-DTO
    (AC11-Feld `tranchen_trigger`) trägt keine Depotstrategie-/
    Risiko-Gate-Felder."""
    assert set(Verkaufsauftrag.model_fields) == {
        "titel_id",
        "menge",
        "tranchen",
        "order_typ",
        "preis",
        "ausfuehrungsprofil",
        "tranchen_trigger",
    }
