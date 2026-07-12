"""Tests für die reinen Portfolio-Aggregat-/Depot-Stand-Bausteine (Story
S-036, AC8/AC9).

Covers (depot): AC8, AC9

`app.domain.portfolio.portfolio_aggregate` liefert reine Formel-/
Aggregations-Bausteine, die eine bereits mode-isoliert gelesene
`PositionsBestand`-Liste entgegennehmen (kein DB-Zugriff, P1) — das
eigentliche depotweite Lesen ist Repository-Sache (siehe
`tests/adapters/repositories/test_position_repository.py::
test_alle_offenen_positionen_*` für die Verdrahtung).
"""

from __future__ import annotations

from decimal import Decimal

from app.domain.portfolio.portfolio_aggregate import (
    CASH_ASSET_CLASS_ID,
    UNBEKANNTE_BRANCHE,
    berechne_portfolio_aggregat,
    ermittle_depot_stand,
    ermittle_titel_strategie_exit_regeln,
)
from app.domain.portfolio.ports import ExitRegelnBestand, PositionsBestand

_LEERE_EXIT_REGELN = ExitRegelnBestand(
    stop_loss_pct=None,
    take_profit_pct=None,
    stop_typ=None,
    atr_multiplikator=None,
    thesis_invalidation=None,
    time_box=None,
)


def _position(
    *,
    position_id: str = "lot-1",
    titel_id: str = "titel-1",
    asset_class_id: int = 1,
    gics_branche: str | None = "Technology",
    menge: Decimal = Decimal("10"),
    einstand_preis: Decimal = Decimal("100"),
    strategie: str | None = "Index",
    exit_regeln: ExitRegelnBestand = _LEERE_EXIT_REGELN,
) -> PositionsBestand:
    return PositionsBestand(
        position_id=position_id,
        titel_id=titel_id,
        asset_class_id=asset_class_id,
        gics_branche=gics_branche,
        menge=menge,
        einstand_preis=einstand_preis,
        strategie=strategie,
        exit_regeln=exit_regeln,
    )


# --- AC8: berechne_portfolio_aggregat --------------------------------------


def test_leeres_depot_ergibt_leere_gewichtung_und_cash_quote_null() -> None:
    """@trace depot#AC8 — ohne offene Position keine Division durch 0,
    sondern leere Aggregate."""
    aggregat = berechne_portfolio_aggregat([])
    assert aggregat.branchen_gewichtung == {}
    assert aggregat.klassen_gewichtung == {}
    assert aggregat.cash_quote == Decimal("0")


def test_einzelne_position_ergibt_100_prozent_gewichtung() -> None:
    """@trace depot#AC8 — eine einzelne offene Position trägt 100 % ihrer
    Branche und Anlageklasse."""
    positionen = [_position(gics_branche="Technology", asset_class_id=1)]
    aggregat = berechne_portfolio_aggregat(positionen)
    assert aggregat.branchen_gewichtung == {"Technology": Decimal("100.000")}
    assert aggregat.klassen_gewichtung == {1: Decimal("100.000")}


def test_zwei_positionen_gleicher_groesse_ergeben_je_50_prozent() -> None:
    """@trace depot#AC8 — Gewichtung ist wert-proportional (Kostenbasis =
    menge × Ø-Einstandspreis), nicht nach Anzahl Positionen."""
    positionen = [
        _position(
            titel_id="titel-a",
            gics_branche="Technology",
            asset_class_id=1,
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
        ),
        _position(
            titel_id="titel-b",
            gics_branche="Healthcare",
            asset_class_id=1,
            menge=Decimal("20"),
            einstand_preis=Decimal("50"),
        ),
    ]
    aggregat = berechne_portfolio_aggregat(positionen)
    assert aggregat.branchen_gewichtung == {
        "Technology": Decimal("50.000"),
        "Healthcare": Decimal("50.000"),
    }
    # Beide Positionen sind Anlageklasse 1 (Aktien) -> volle Klassen-Gewichtung dort.
    assert aggregat.klassen_gewichtung == {1: Decimal("100.000")}


def test_mehrere_lots_desselben_titels_werden_pro_branche_summiert() -> None:
    """@trace depot#AC8 — bei FIFO existieren mehrere Lot-Zeilen desselben
    Titels; ihr Wert wird je Branche/Klasse aufsummiert, nicht als
    separate Branchen-Einträge geführt."""
    positionen = [
        _position(position_id="lot-1", titel_id="titel-a", menge=Decimal("5")),
        _position(position_id="lot-2", titel_id="titel-a", menge=Decimal("5")),
    ]
    aggregat = berechne_portfolio_aggregat(positionen)
    assert aggregat.branchen_gewichtung == {"Technology": Decimal("100.000")}


def test_fehlende_gics_branche_faellt_auf_sentinel_zurueck() -> None:
    """@trace depot#AC8 — `Instrument.gics_sector` ist NULLable; eine
    Position ohne bekannte Branche fällt nicht stillschweigend aus der
    Gewichtung, sondern landet unter dem Sentinel-Schlüssel."""
    positionen = [_position(gics_branche=None)]
    aggregat = berechne_portfolio_aggregat(positionen)
    assert aggregat.branchen_gewichtung == {UNBEKANNTE_BRANCHE: Decimal("100.000")}


def test_cash_quote_ist_gewichtung_der_anlageklasse_3() -> None:
    """@trace depot#AC8 — Cash-Quote ist die Gewichtung der Anlageklasse 3
    (Cash/Geldmarkt) innerhalb `klassen_gewichtung`, kein separates
    Cash-Ledger."""
    assert CASH_ASSET_CLASS_ID == 3
    positionen = [
        _position(
            titel_id="titel-aktie",
            asset_class_id=1,
            gics_branche="Technology",
            menge=Decimal("80"),
            einstand_preis=Decimal("1"),
        ),
        _position(
            titel_id="titel-cash",
            asset_class_id=3,
            gics_branche=None,
            menge=Decimal("20"),
            einstand_preis=Decimal("1"),
        ),
    ]
    aggregat = berechne_portfolio_aggregat(positionen)
    assert aggregat.klassen_gewichtung[3] == Decimal("20.000")
    assert aggregat.cash_quote == Decimal("20.000")


def test_cash_quote_null_ohne_position_in_anlageklasse_3() -> None:
    """@trace depot#AC8 — kein gehaltener Cash-Titel ergibt Cash-Quote 0,
    keinen fehlenden Schlüsselzugriff."""
    positionen = [_position(asset_class_id=1)]
    aggregat = berechne_portfolio_aggregat(positionen)
    assert aggregat.cash_quote == Decimal("0")


# --- AC9: ermittle_depot_stand ----------------------------------------------


def test_ermittle_depot_stand_buendelt_positionen_und_aggregat() -> None:
    """@trace depot#AC9 — Depot-Stand für das Risikomanagement enthält die
    offenen Positionen UND das daraus berechnete Aggregat (Verträge-Vertrag
    "Output an Risikomanagement")."""
    positionen = [_position(titel_id="titel-a"), _position(titel_id="titel-b")]
    depot_stand = ermittle_depot_stand(positionen)
    assert depot_stand.positionen == tuple(positionen)
    assert depot_stand.aggregat == berechne_portfolio_aggregat(positionen)


def test_ermittle_depot_stand_ohne_positionen_liefert_leeres_aggregat() -> None:
    """@trace depot#AC9 — ein leeres Depot liefert einen Depot-Stand mit
    leerer Positionsliste und leerem Aggregat statt eines Fehlers."""
    depot_stand = ermittle_depot_stand([])
    assert depot_stand.positionen == ()
    assert depot_stand.aggregat.cash_quote == Decimal("0")


# --- AC9: ermittle_titel_strategie_exit_regeln ------------------------------


def test_ermittle_titel_strategie_exit_regeln_liefert_je_titel_einen_eintrag() -> None:
    """@trace depot#AC9 — Output an die Depot-Überwachung: je gehaltenem
    Titel genau ein `{ titel_id, strategie, exit_regeln }`-Eintrag."""
    exit_regeln = ExitRegelnBestand(
        stop_loss_pct=Decimal("-15"),
        take_profit_pct=Decimal("30"),
        stop_typ="fix_pct",
        atr_multiplikator=None,
        thesis_invalidation="Marktanteil < 10%",
        time_box=None,
    )
    positionen = [
        _position(titel_id="titel-a", strategie="Index", exit_regeln=exit_regeln),
    ]
    ergebnis = ermittle_titel_strategie_exit_regeln(positionen)
    assert len(ergebnis) == 1
    assert ergebnis[0].titel_id == "titel-a"
    assert ergebnis[0].strategie == "Index"
    assert ergebnis[0].exit_regeln == exit_regeln


def test_ermittle_titel_strategie_exit_regeln_dedupliziert_mehrere_lots_desselben_titels() -> None:
    """@trace depot#AC9 — mehrere offene Lots desselben Titels (FIFO)
    ergeben genau EINEN Eintrag (der Depot-Überwachung-Vertrag AC2 fordert
    genau eine Abfrage je Titel) — der Wert des ÄLTESTEN (zuerst
    übergebenen) Lots gewinnt."""
    aelterer_exit_regeln = ExitRegelnBestand(
        stop_loss_pct=Decimal("-10"),
        take_profit_pct=None,
        stop_typ="fix_pct",
        atr_multiplikator=None,
        thesis_invalidation=None,
        time_box=None,
    )
    positionen = [
        _position(
            position_id="lot-alt",
            titel_id="titel-a",
            strategie="Momentum",
            exit_regeln=aelterer_exit_regeln,
        ),
        _position(
            position_id="lot-neu",
            titel_id="titel-a",
            strategie="Momentum-V2",
            exit_regeln=_LEERE_EXIT_REGELN,
        ),
    ]
    ergebnis = ermittle_titel_strategie_exit_regeln(positionen)
    assert len(ergebnis) == 1
    assert ergebnis[0].strategie == "Momentum"
    assert ergebnis[0].exit_regeln == aelterer_exit_regeln


def test_ermittle_titel_strategie_exit_regeln_leer_ohne_positionen() -> None:
    """@trace depot#AC9 — kein offener Titel ergibt eine leere Liste,
    keinen Fehler."""
    assert ermittle_titel_strategie_exit_regeln([]) == []
