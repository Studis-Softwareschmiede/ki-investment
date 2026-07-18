"""Tests für das Risikomanagement-Gate (Story S-044).

Covers (risikomanagement): AC2, AC6, AC12

- AC12: kein `DepotStand` (E1) bzw. keine aktive Depotstrategie (analog
  E1, S-043) -> immer `"blockieren"`, nie ein Durchwink-Entscheid.
- AC6: genau einer von drei Entscheiden (`"durchwinken"` / `"deckeln"` /
  `"blockieren"`) je Aufruf; Deckelung ist eine reine Kappung auf das
  erlaubte Maximum ohne Rück-Durchlauf ins Position-Sizing.
- AC2: die Sektor-/Branchen-Prüfung bewertet die Konzentration über ALLE
  offenen Positionen hinweg (wertgewichtet), nicht anhand der nominellen
  Anzahl Titel je Branche.

Die AC5-Invariante ("Gate greift nur beim Kauf") ist strukturell in
`tests/architecture/test_gate_greift_nur_beim_kauf.py` abgedeckt (AST-Scan,
kein Laufzeit-Test hier nötig, da `pruefe_kauf_gate` ausschliesslich eine
`AnnotierteKaufOrder` entgegennimmt).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.contracts.risikomanagement import DepotstrategieKonfiguration, GateEntscheid
from app.contracts.strategie_exit_regeln import AnnotierteKaufOrder, ExitDefaultVorschlag
from app.domain.portfolio.portfolio_aggregate import ermittle_depot_stand
from app.domain.portfolio.ports import ExitRegelnBestand, PositionsBestand
from app.domain.risikomanagement.gate import pruefe_kauf_gate

_JETZT = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)

_LEERE_EXIT_REGELN = ExitRegelnBestand(
    stop_loss_pct=None,
    take_profit_pct=None,
    stop_typ=None,
    atr_multiplikator=None,
    thesis_invalidation=None,
    time_box=None,
)

_VORSCHLAG = ExitDefaultVorschlag(
    kategorie="value_aktien",
    stop_typ="fundamental",
    stop_hinweis="Fundamentaler Stop (These bricht).",
    stop_parameter=None,
    stop_unbestimmt=False,
    take_profit_hinweis="Zielwert erreicht.",
    time_box=None,
    thesis_invalidierung="Marktanteil < 10%.",
)


def _kauf_order(*, titel_id: str = "AAPL", ordergroesse: Decimal) -> AnnotierteKaufOrder:
    return AnnotierteKaufOrder(
        titel_id=titel_id,
        ordergroesse=ordergroesse,
        strategie="Value",
        zeithorizont=7,
        exit_regeln=_VORSCHLAG,
        these="Unterbewertet gegenüber Peer-Group.",
        fixiert_am=_JETZT,
        unveraenderlich=True,
    )


def _depotstrategie(*, max_sektor_pct: Decimal = Decimal("20")) -> DepotstrategieKonfiguration:
    return DepotstrategieKonfiguration(
        portfolio_strategy_id=uuid.uuid4(),
        risk_profile_name="ausgewogen",
        max_einzelposition_pct=Decimal("5"),
        max_sektor_pct=max_sektor_pct,
        cash_quote_ziel_pct=Decimal("5"),
        gesamt_exposure_cap_pct=Decimal("25"),
    )


def _position(
    *,
    position_id: str,
    titel_id: str,
    asset_class_id: int = 1,
    gics_branche: str | None,
    menge: Decimal,
    einstand_preis: Decimal,
) -> PositionsBestand:
    return PositionsBestand(
        position_id=position_id,
        titel_id=titel_id,
        asset_class_id=asset_class_id,
        gics_branche=gics_branche,
        menge=menge,
        einstand_preis=einstand_preis,
        strategie="Value",
        exit_regeln=_LEERE_EXIT_REGELN,
    )


# --- AC12: kein Depot-Stand / keine Depotstrategie -> keine Freigabe -------


def test_ac12_kein_depot_stand_blockiert() -> None:
    """@trace risikomanagement#AC12 — `depot_stand=None` (E1) liefert immer
    `"blockieren"`, unabhängig von Depotstrategie/Ordergrösse."""
    entscheid = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("100")),
        gics_branche="Technology",
        depotstrategie=_depotstrategie(),
        depot_stand=None,
    )

    assert isinstance(entscheid, GateEntscheid)
    assert entscheid.entscheid == "blockieren"
    assert entscheid.freigegebene_groesse == Decimal("0")
    assert entscheid.warteliste is False


def test_ac12_keine_aktive_depotstrategie_blockiert() -> None:
    """@trace risikomanagement#AC12 — `depotstrategie=None` (kein
    Grenzwert verfügbar, analog E1 laut `lade_aktive_depotstrategie`-
    Docstring) liefert `"blockieren"`."""
    depot_stand = ermittle_depot_stand([])

    entscheid = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("100")),
        gics_branche="Technology",
        depotstrategie=None,
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"
    assert entscheid.freigegebene_groesse == Decimal("0")


def test_ac6_erster_kauf_in_leeres_depot_wird_durchgewinkt() -> None:
    """@trace risikomanagement#AC6 — Cold-Start: ein leeres (aber erfolgreich
    geladenes) Depot MIT aktiver Depotstrategie hat noch keine Sektor-
    Konzentration; der allererste Kauf muss durchgewinkt werden (volle
    Grösse), nicht blockiert — sonst wäre der erste Kauf in ein neues Depot
    strukturell unmöglich, sobald ein Sektor-Limit < 100% konfiguriert ist."""
    depot_stand = ermittle_depot_stand([])  # leerer, aber nicht-None DepotStand

    entscheid = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("100")),
        gics_branche="Technology",
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "durchwinken"
    assert entscheid.freigegebene_groesse == Decimal("100")


# --- AC6: Edge-Case Ordergrösse <= 0 ----------------------------------------


def test_ordergroesse_null_oder_negativ_blockiert() -> None:
    """@trace risikomanagement#AC6 — Ordergrösse <= 0 wird nie durchgewinkt
    oder gedeckelt (Edge-Case §Edge-Cases & Fehlerverhalten)."""
    depot_stand = ermittle_depot_stand([])
    depotstrategie = _depotstrategie()

    fuer_null = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("0")),
        gics_branche="Technology",
        depotstrategie=depotstrategie,
        depot_stand=depot_stand,
    )
    fuer_negativ = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("-10")),
        gics_branche="Technology",
        depotstrategie=depotstrategie,
        depot_stand=depot_stand,
    )

    assert fuer_null.entscheid == "blockieren"
    assert fuer_negativ.entscheid == "blockieren"


# --- AC2/AC6: durchwinken --------------------------------------------------


def test_ac6_durchwinken_wenn_resultierende_gewichtung_unter_limit() -> None:
    """@trace risikomanagement#AC2,AC6 — resultierende Sektor-Gewichtung
    bleibt unter dem Limit -> volle geplante Grösse wird durchgewinkt."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="AAPL",
            gics_branche="Technology",
            menge=Decimal("5"),
            einstand_preis=Decimal("100"),
        ),  # 500
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("45"),
            einstand_preis=Decimal("100"),
        ),  # 4500
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 500 (10%)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("100")),
        gics_branche="Technology",
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "durchwinken"
    assert entscheid.freigegebene_groesse == Decimal("100").quantize(Decimal("0.00000001"))


def test_edge_order_genau_am_limit_gilt_als_eingehalten() -> None:
    """@trace risikomanagement#AC2,AC6 — Order, die die resultierende
    Gewichtung exakt auf das Limit bringt, gilt als eingehalten
    (durchwinken, nicht deckeln; Spec-Edge-Case "Order genau am Limit")."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="AAPL",
            gics_branche="Technology",
            menge=Decimal("5"),
            einstand_preis=Decimal("100"),
        ),  # 500
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("45"),
            einstand_preis=Decimal("100"),
        ),  # 4500
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 500 (10%)
    # x = (0.20*5000 - 500) / (1-0.20) = 625 -> resultierend genau 20 %.
    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("625")),
        gics_branche="Technology",
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "durchwinken"
    assert entscheid.freigegebene_groesse == Decimal("625").quantize(Decimal("0.00000001"))


# --- AC2/AC6: deckeln --------------------------------------------------


def test_ac6_deckeln_kappt_auf_erlaubtes_maximum_ohne_rueck_durchlauf() -> None:
    """@trace risikomanagement#AC2,AC6 — volle Ordergrösse würde das
    Sektor-Limit überschreiten -> Deckelung auf das exakt erlaubte Maximum
    (kein Rück-Durchlauf ins Position-Sizing, reine Kappung des bereits
    fixierten Werts)."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="AAPL",
            gics_branche="Technology",
            menge=Decimal("5"),
            einstand_preis=Decimal("100"),
        ),  # 500
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("45"),
            einstand_preis=Decimal("100"),
        ),  # 4500
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 500 (10%)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("2000")),
        gics_branche="Technology",
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "deckeln"
    # Erwartetes Maximum: (0.20*5000 - 500) / 0.80 = 625.
    assert entscheid.freigegebene_groesse == Decimal("625").quantize(Decimal("0.00000001"))
    assert entscheid.freigegebene_groesse < Decimal("2000")

    # Resultierende Gewichtung nach Deckelung trifft das Limit exakt (20%).
    resultierender_gesamtwert = Decimal("5000") + entscheid.freigegebene_groesse
    resultierender_sektorwert = Decimal("500") + entscheid.freigegebene_groesse
    assert resultierender_sektorwert / resultierender_gesamtwert == Decimal("0.2")


# --- AC2/AC6: blockieren (Limit bereits ausgeschöpft) -----------------------


def test_ac6_blockieren_wenn_sektor_limit_bereits_ausgeschoepft() -> None:
    """@trace risikomanagement#AC2,AC6 — die bestehende Sektor-Gewichtung
    erreicht (oder übersteigt) bereits das Limit -> jede weitere Order in
    dieser Branche wird blockiert (Spec A2: "Limit bereits ausgeschöpft")."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="AAPL",
            gics_branche="Technology",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
        ),  # 1000
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("40"),
            einstand_preis=Decimal("100"),
        ),  # 4000
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 1000 (20% == Limit)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("50")),
        gics_branche="Technology",
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"
    assert entscheid.freigegebene_groesse == Decimal("0")


def test_ac2_versteckte_konzentration_ueber_viele_kleine_positionen_erkannt() -> None:
    """@trace risikomanagement#AC2 — mehrere kleine Positionen derselben
    Branche summieren sich zur Konzentrationsprüfung, nicht nur eine
    einzelne grosse Position; die Prüfung erkennt die Konzentration auch
    dann, wenn kein einzelner Titel für sich genommen auffällig wäre
    ("nicht anhand der nominellen Anzahl Titel")."""
    positionen = [
        _position(
            position_id=f"lot-tech-{i}",
            titel_id=f"TECH{i}",
            gics_branche="Technology",
            menge=Decimal("2"),
            einstand_preis=Decimal("100"),
        )
        for i in range(5)
    ]  # 5 kleine Tech-Titel je 200 = 1000 gesamt
    positionen.append(
        _position(
            position_id="lot-health",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("40"),
            einstand_preis=Decimal("100"),
        )
    )  # 4000
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 1000 (20% == Limit)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="TECH6", ordergroesse=Decimal("10")),
        gics_branche="Technology",
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"


def test_ac2_unbekannte_branche_faellt_in_gemeinsamen_bucket() -> None:
    """@trace risikomanagement#AC2 — Positionen ohne gepflegte GICS-Branche
    (`gics_branche=None`) und ein Kauf-Kandidat ohne bekannte Branche
    fallen in denselben `unbekannt`-Bucket (Sentinel analog
    `portfolio_aggregate.UNBEKANNTE_BRANCHE`) statt aus der Prüfung zu
    fallen."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="XYZ",
            gics_branche=None,
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
        ),  # 1000, unbekannt
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("40"),
            einstand_preis=Decimal("100"),
        ),  # 4000
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, unbekannt 1000 (20% == Limit)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="ABC", ordergroesse=Decimal("50")),
        gics_branche=None,
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"
