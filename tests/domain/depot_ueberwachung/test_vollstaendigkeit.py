"""Tests für die AC1-Vollständigkeitsprüfung gehaltener Titel (Story
S-032).

Covers (depot-ueberwachung): AC1

`app.domain.depot_ueberwachung.vollstaendigkeit.ermittle_fehlende_felder`
prüft, ob ein `TitelStrategieExitRegeln`-Eintrag alle vier laut AC1
geforderten Felder (`titel_id, anlageklasse, strategie, exit_regeln`)
trägt."""

from __future__ import annotations

from decimal import Decimal

from app.domain.depot_ueberwachung.vollstaendigkeit import ermittle_fehlende_felder
from app.domain.portfolio.portfolio_aggregate import TitelStrategieExitRegeln
from app.domain.portfolio.ports import ExitRegelnBestand

_LEERE_EXIT_REGELN = ExitRegelnBestand(
    stop_loss_pct=None,
    take_profit_pct=None,
    stop_typ=None,
    atr_multiplikator=None,
    thesis_invalidation=None,
    time_box=None,
)
_GEFUELLTE_EXIT_REGELN = ExitRegelnBestand(
    stop_loss_pct=Decimal("-15"),
    take_profit_pct=Decimal("30"),
    stop_typ="fix_pct",
    atr_multiplikator=None,
    thesis_invalidation="Marktanteil < 10%",
    time_box=None,
)


def _titel(
    *,
    titel_id: str = "titel-1",
    anlageklasse: int = 1,
    strategie: str | None = "Index",
    exit_regeln: ExitRegelnBestand = _GEFUELLTE_EXIT_REGELN,
) -> TitelStrategieExitRegeln:
    return TitelStrategieExitRegeln(
        titel_id=titel_id, anlageklasse=anlageklasse, strategie=strategie, exit_regeln=exit_regeln
    )


def test_vollstaendiger_titel_hat_keine_fehlenden_felder() -> None:
    """@trace depot-ueberwachung#AC1 — alle vier Felder vorhanden → keine
    fehlenden Felder."""
    assert ermittle_fehlende_felder(_titel()) == []


def test_fehlende_strategie_wird_als_fehlend_erkannt() -> None:
    """@trace depot-ueberwachung#AC1 — `strategie=None` wird als fehlend
    protokolliert."""
    assert ermittle_fehlende_felder(_titel(strategie=None)) == ["strategie"]


def test_leerer_strategie_string_zaehlt_ebenfalls_als_fehlend() -> None:
    """@trace depot-ueberwachung#AC1 — ein Leer-/Whitespace-String zählt
    wie `None` als fehlend (analog `app.contracts.depot._ist_leer`)."""
    assert ermittle_fehlende_felder(_titel(strategie="   ")) == ["strategie"]


def test_leere_exit_regeln_werden_als_fehlend_erkannt() -> None:
    """@trace depot-ueberwachung#AC1 — ein `ExitRegelnBestand` mit
    ausschliesslich `None`-Feldern (Cold-Start: keine `exit_rule`-Zeile
    existiert, siehe Moduldocstring) gilt als strukturell fehlend."""
    assert ermittle_fehlende_felder(_titel(exit_regeln=_LEERE_EXIT_REGELN)) == ["exit_regeln"]


def test_anlageklasse_ausserhalb_1_bis_11_zaehlt_als_fehlend() -> None:
    """@trace depot-ueberwachung#AC1 — eine strukturell ungültige
    Anlageklasse (ausserhalb 1..11) zählt als fehlendes Pflichtfeld."""
    assert ermittle_fehlende_felder(_titel(anlageklasse=0)) == ["anlageklasse"]


def test_mehrere_fehlende_felder_werden_alle_gemeldet() -> None:
    """@trace depot-ueberwachung#AC1 — mehrere gleichzeitig fehlende
    Felder werden alle (nicht nur das erste) gemeldet, "nicht
    stillschweigend übersprungen"."""
    fehlend = ermittle_fehlende_felder(
        _titel(titel_id="", strategie=None, exit_regeln=_LEERE_EXIT_REGELN)
    )
    assert fehlend == ["titel_id", "strategie", "exit_regeln"]
