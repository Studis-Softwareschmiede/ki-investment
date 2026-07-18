"""Tests für das Risikomanagement-Gate (Storys S-044, S-045, S-056).

Covers (risikomanagement): AC2, AC6, AC7, AC8, AC9, AC10, AC12

- AC7: ein wegen ausgeschöpften Limits (A2) blockierter Kauf wird nur dann
  als `warteliste=True` markiert, wenn der Aufrufer das explizit per
  `warteliste_bei_blockade=True` anfordert ("kann optional"); Default
  bleibt `False`. Die AC12/E1-Blockaden (kein Depot-Stand/keine
  Depotstrategie) und der Ordergrösse-`<=0`-Edge-Case setzen `warteliste`
  NIE, selbst wenn der Aufrufer `warteliste_bei_blockade=True` übergibt
  (Präzisierung S-056, siehe Spec).
- AC12: kein `DepotStand` (E1) bzw. keine aktive Depotstrategie (analog
  E1, S-043) -> immer `"blockieren"`, nie ein Durchwink-Entscheid.
- AC6: genau einer von drei Entscheiden (`"durchwinken"` / `"deckeln"` /
  `"blockieren"`) je Aufruf; Deckelung ist eine reine Kappung auf das
  erlaubte Maximum ohne Rück-Durchlauf ins Position-Sizing.
- AC2: die Sektor-/Branchen-Prüfung bewertet die Konzentration über ALLE
  offenen Positionen hinweg (wertgewichtet), nicht anhand der nominellen
  Anzahl Titel je Branche.
- AC8: Klumpenrisiko vollständig — zusätzlich zu AC2 (Sektor) auch
  Anlageklasse (nur falls konfiguriert, sonst kein Limit) und
  Einzelposition (alle bestehenden Lots desselben Titels).
- AC9: Korrelations-Cluster-Konzentration wird unabhängig vom Sektorlimit
  geprüft; fehlende Cluster-Zuordnung fällt konservativ in einen
  gemeinsamen "unbekannt"-Bucket statt die Prüfung zu überspringen
  (Edge-Case).
- AC10: portfolio-weiter Kelly-Cap (`gesamt_exposure_cap_pct`) begrenzt den
  wertgewichteten Anteil aller Nicht-Cash-Positionen am Gesamtdepot.
- Cold-Start (S-044-Lesson, jetzt für ALLE fünf Prüf-Dimensionen erneut
  verifiziert): ein leeres Depot MIT scharf konfigurierten Limits
  blockiert den allerersten Kauf NICHT.

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
from app.domain.portfolio.portfolio_aggregate import (
    CASH_ASSET_CLASS_ID,
    DepotStand,
    ermittle_depot_stand,
)
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


def _depotstrategie(
    *,
    max_sektor_pct: Decimal = Decimal("20"),
    # AC8-AC10 (S-045): non-bindende Defaults, damit bestehende, rein
    # sektor-fokussierte Tests (S-044) unverändert ihre ursprüngliche
    # Erwartung behalten — die neuen Prüfungen greifen nur, wo ein Test sie
    # explizit über diese Parameter aktiviert.
    max_einzelposition_pct: Decimal = Decimal("100"),
    max_anlageklasse_pct: dict[int, Decimal] | None = None,
    gesamt_exposure_cap_pct: Decimal = Decimal("100"),
) -> DepotstrategieKonfiguration:
    return DepotstrategieKonfiguration(
        portfolio_strategy_id=uuid.uuid4(),
        risk_profile_name="ausgewogen",
        max_einzelposition_pct=max_einzelposition_pct,
        max_sektor_pct=max_sektor_pct,
        cash_quote_ziel_pct=Decimal("5"),
        gesamt_exposure_cap_pct=gesamt_exposure_cap_pct,
        max_anlageklasse_pct=max_anlageklasse_pct or {},
    )


def _position(
    *,
    position_id: str,
    titel_id: str,
    asset_class_id: int = 1,
    gics_branche: str | None,
    menge: Decimal,
    einstand_preis: Decimal,
    korrelations_cluster: str | None = None,
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
        korrelations_cluster=korrelations_cluster,
    )


# --- AC12: kein Depot-Stand / keine Depotstrategie -> keine Freigabe -------


def test_ac12_kein_depot_stand_blockiert() -> None:
    """@trace risikomanagement#AC12 — `depot_stand=None` (E1) liefert immer
    `"blockieren"`, unabhängig von Depotstrategie/Ordergrösse."""
    entscheid = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("100")),
        gics_branche="Technology",
        asset_class_id=1,
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
        asset_class_id=1,
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
        asset_class_id=1,
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
        asset_class_id=1,
        depotstrategie=depotstrategie,
        depot_stand=depot_stand,
    )
    fuer_negativ = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("-10")),
        gics_branche="Technology",
        asset_class_id=1,
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
            korrelations_cluster="tech_cluster",
        ),  # 500
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("45"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="health_cluster",
        ),  # 4500
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 500 (10%)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("100")),
        gics_branche="Technology",
        asset_class_id=1,
        korrelations_cluster="tech_cluster",
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
            korrelations_cluster="tech_cluster",
        ),  # 500
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("45"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="health_cluster",
        ),  # 4500
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 500 (10%)
    # x = (0.20*5000 - 500) / (1-0.20) = 625 -> resultierend genau 20 %.
    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("625")),
        gics_branche="Technology",
        asset_class_id=1,
        korrelations_cluster="tech_cluster",
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
            korrelations_cluster="tech_cluster",
        ),  # 500
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            gics_branche="Health Care",
            menge=Decimal("45"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="health_cluster",
        ),  # 4500
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Tech 500 (10%)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("2000")),
        gics_branche="Technology",
        asset_class_id=1,
        korrelations_cluster="tech_cluster",
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
        asset_class_id=1,
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
        asset_class_id=1,
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
        asset_class_id=1,
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"


# --- AC7: Warteliste beim Blockieren (S-056) --------------------------------


def _blockierendes_depot() -> tuple[DepotstrategieKonfiguration, DepotStand]:
    """Depot-Stand + Depotstrategie, bei denen das Sektor-Limit bereits
    ausgeschöpft ist (identischer Aufbau wie
    `test_ac6_blockieren_wenn_sektor_limit_bereits_ausgeschoepft`)."""
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
    return _depotstrategie(max_sektor_pct=Decimal("20")), depot_stand


def test_ac7_warteliste_wird_bei_a2_blockade_gesetzt_wenn_angefordert() -> None:
    """@trace risikomanagement#AC7 — der Aufrufer fordert
    `warteliste_bei_blockade=True` an; das Limit ist ausgeschöpft (A2) ->
    `GateEntscheid.warteliste` wird `True`."""
    depotstrategie, depot_stand = _blockierendes_depot()

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("50")),
        gics_branche="Technology",
        asset_class_id=1,
        depotstrategie=depotstrategie,
        depot_stand=depot_stand,
        warteliste_bei_blockade=True,
    )

    assert entscheid.entscheid == "blockieren"
    assert entscheid.warteliste is True


def test_ac7_warteliste_bleibt_false_ohne_ausdruecklichen_wunsch() -> None:
    """@trace risikomanagement#AC7 — "kann optional gesetzt werden": ohne
    `warteliste_bei_blockade=True` bleibt `warteliste` auch bei einer
    A2-Blockade `False` (Default-Verhalten unverändert zu S-044/S-045)."""
    depotstrategie, depot_stand = _blockierendes_depot()

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("50")),
        gics_branche="Technology",
        asset_class_id=1,
        depotstrategie=depotstrategie,
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"
    assert entscheid.warteliste is False


def test_ac7_warteliste_nicht_bei_ac12_blockade_trotz_wunsch() -> None:
    """@trace risikomanagement#AC7,AC12 — `warteliste_bei_blockade=True`
    wirkt NICHT auf die AC12/E1-Blockaden (kein Depot-Stand/keine
    Depotstrategie): keine Konzentrationsprüfung fand statt, es gibt
    fachlich keinen wartefähigen Kandidaten (Präzisierung S-056)."""
    kein_depot_stand = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("100")),
        gics_branche="Technology",
        asset_class_id=1,
        depotstrategie=_depotstrategie(),
        depot_stand=None,
        warteliste_bei_blockade=True,
    )
    keine_depotstrategie = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("100")),
        gics_branche="Technology",
        asset_class_id=1,
        depotstrategie=None,
        depot_stand=ermittle_depot_stand([]),
        warteliste_bei_blockade=True,
    )

    assert kein_depot_stand.entscheid == "blockieren"
    assert kein_depot_stand.warteliste is False
    assert keine_depotstrategie.entscheid == "blockieren"
    assert keine_depotstrategie.warteliste is False


def test_ac7_warteliste_nicht_bei_ordergroesse_edge_case_trotz_wunsch() -> None:
    """@trace risikomanagement#AC7 — `warteliste_bei_blockade=True` wirkt
    NICHT auf den Ordergrösse-`<=0`-Edge-Case (keine gültige Order, die
    warten könnte, Präzisierung S-056)."""
    depot_stand = ermittle_depot_stand([])

    entscheid = pruefe_kauf_gate(
        _kauf_order(ordergroesse=Decimal("0")),
        gics_branche="Technology",
        asset_class_id=1,
        depotstrategie=_depotstrategie(),
        depot_stand=depot_stand,
        warteliste_bei_blockade=True,
    )

    assert entscheid.entscheid == "blockieren"
    assert entscheid.warteliste is False


# --- AC8: Klumpenrisiko — Anlageklasse (S-045) ------------------------------


def test_ac8_klassen_limit_blockiert_trotz_verteilter_sektoren() -> None:
    """@trace risikomanagement#AC8 — Konzentration innerhalb EINER
    Anlageklasse wird erkannt, auch wenn die Positionen über mehrere
    Sektoren verteilt sind (Sektorlimit allein hätte keine Konzentration
    erkannt)."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="AAPL",
            asset_class_id=1,
            gics_branche="Technology",
            menge=Decimal("9"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="clusterA",
        ),  # 900, Klasse 1
        _position(
            position_id="lot-2",
            titel_id="XOM",
            asset_class_id=1,
            gics_branche="Energy",
            menge=Decimal("9"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="clusterB",
        ),  # 900, Klasse 1
        _position(
            position_id="lot-3",
            titel_id="JNJ",
            asset_class_id=2,
            gics_branche="Health Care",
            menge=Decimal("32"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="clusterC",
        ),  # 3200, Klasse 2
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, Klasse 1: 1800 (36%)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="XLU", ordergroesse=Decimal("50")),
        gics_branche="Utilities",  # neuer Sektor, kein Sektor-Konflikt
        asset_class_id=1,
        korrelations_cluster="clusterD",  # neuer Cluster, kein Cluster-Konflikt
        depotstrategie=_depotstrategie(
            max_sektor_pct=Decimal("20"),
            max_anlageklasse_pct={1: Decimal("35")},  # Klasse 1 bereits bei 36 % > 35 %
        ),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"


def test_ac8_fehlende_klassen_limit_konfiguration_bedeutet_kein_limit() -> None:
    """@trace risikomanagement#AC8 — eine Anlageklasse OHNE konfigurierten
    `max_anlageklasse_pct`-Eintrag hat kein Limit (nicht "Limit 0"), auch
    bei extremer bestehender Konzentration."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="BTC",
            asset_class_id=5,
            gics_branche="Krypto-Sonstige",
            menge=Decimal("49"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="krypto_cluster_a",
        ),  # 4900 von 5000 (98 %), Klasse 5 — KEIN Eintrag in max_anlageklasse_pct
    ]
    depot_stand = ermittle_depot_stand(positionen)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="ETH", ordergroesse=Decimal("100")),
        gics_branche="Krypto-Sonstige-2",  # neuer Sektor
        asset_class_id=5,
        korrelations_cluster="krypto_cluster_b",  # neuer, unbelasteter Cluster
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),  # max_anlageklasse_pct={}
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "durchwinken"
    assert entscheid.freigegebene_groesse == Decimal("100").quantize(Decimal("0.00000001"))


# --- AC8: Klumpenrisiko — Einzelposition (S-045) ----------------------------


def test_ac8_einzelpositions_limit_deckelt_nachkauf() -> None:
    """@trace risikomanagement#AC8 — ein Nachkauf desselben Titels wird auf
    das Einzelpositions-Limit gedeckelt, auch wenn Sektor-/Klassen-Limits
    grosszügig genug wären (isolierter Treiber)."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="AAPL",
            asset_class_id=1,
            gics_branche="Technology",
            menge=Decimal("9"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="tech_cluster",
        ),  # 900 (18 %)
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            asset_class_id=2,
            gics_branche="Health Care",
            menge=Decimal("41"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="health_cluster",
        ),  # 4100 (82 %)
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="AAPL", ordergroesse=Decimal("500")),
        gics_branche="Technology",
        asset_class_id=1,
        korrelations_cluster="tech_cluster",
        depotstrategie=_depotstrategie(
            max_sektor_pct=Decimal("50"),  # grosszügig, kein Sektor-Konflikt
            max_einzelposition_pct=Decimal("20"),
        ),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "deckeln"
    # x = (0.20*5000 - 900) / (1-0.20) = 125.
    assert entscheid.freigegebene_groesse == Decimal("125").quantize(Decimal("0.00000001"))


# --- AC9: Korrelations-Cluster-Prüfung (S-045) ------------------------------


def test_ac9_cluster_konzentration_blockiert_trotz_freiem_sektorlimit() -> None:
    """@trace risikomanagement#AC9 — ein weiterer Titel eines bereits stark
    vertretenen Korrelations-Clusters wird blockiert, obwohl das nominelle
    Sektorlimit noch nicht erreicht ist (jeweils neuer Sektor je Position)."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="AAPL",
            asset_class_id=1,
            gics_branche="Technology",
            menge=Decimal("9"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="growth_tech",
        ),  # 900 (18 %)
        _position(
            position_id="lot-2",
            titel_id="AMZN",
            asset_class_id=1,
            gics_branche="Consumer Discretionary",
            menge=Decimal("9"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="growth_tech",
        ),  # 900 (18 %)
        _position(
            position_id="lot-3",
            titel_id="JNJ",
            asset_class_id=2,
            gics_branche="Health Care",
            menge=Decimal("32"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="defensive",
        ),  # 3200 (64 %)
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000, growth_tech: 1800 (36 %)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="META", ordergroesse=Decimal("50")),
        gics_branche="Communication Services",  # neuer, unbelasteter Sektor
        asset_class_id=1,
        korrelations_cluster="growth_tech",
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"


def test_ac9_fehlende_cluster_daten_werden_konservativ_behandelt_nicht_uebersprungen() -> None:
    """@trace risikomanagement#AC9 — Edge-Case "Korrelations-Daten nicht
    verfügbar": ein Kauf-Kandidat OHNE bekannten Cluster fällt in den
    gemeinsamen `unbekannt`-Bucket und wird dort blockiert, wenn dieser
    Bucket bereits am Limit ist — die Prüfung wird NICHT übersprungen,
    obwohl der (neue) Sektor des Kandidaten völlig unbelastet ist."""
    positionen = [
        _position(
            position_id="lot-1",
            titel_id="XYZ",
            asset_class_id=1,
            gics_branche="Technology",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
            korrelations_cluster=None,  # unbekannter Cluster
        ),  # 1000 (20 % == Limit), unbekannt
        _position(
            position_id="lot-2",
            titel_id="JNJ",
            asset_class_id=2,
            gics_branche="Health Care",
            menge=Decimal("40"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="defensive",
        ),  # 4000 (80 %)
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 5000

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="ABC", ordergroesse=Decimal("10")),
        gics_branche="Utilities",  # neuer, unbelasteter Sektor
        asset_class_id=1,
        korrelations_cluster=None,  # ebenfalls unbekannt -> selber Bucket
        depotstrategie=_depotstrategie(max_sektor_pct=Decimal("20")),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "blockieren"


# --- AC10: portfolio-weiter Kelly-Cap (S-045) -------------------------------


def test_ac10_kelly_cap_deckelt_nicht_cash_exposure() -> None:
    """@trace risikomanagement#AC10 — der portfolio-weite Kelly-Cap
    begrenzt den wertgewichteten Anteil aller Nicht-Cash-Positionen am
    Gesamtdepot (isolierter Treiber, Sektor/Klasse/Einzelposition/Cluster
    grosszügig konfiguriert)."""
    positionen = [
        _position(
            position_id="lot-cash",
            titel_id="CASH-CHF",
            asset_class_id=CASH_ASSET_CLASS_ID,
            gics_branche=None,
            menge=Decimal("1"),
            einstand_preis=Decimal("900"),
            korrelations_cluster="cash",
        ),  # 900 Cash
        _position(
            position_id="lot-tech",
            titel_id="AAPL",
            asset_class_id=1,
            gics_branche="Technology",
            menge=Decimal("1"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="growth_tech",
        ),  # 100 Nicht-Cash
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 1000, Nicht-Cash 100 (10 %)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="MSFT", ordergroesse=Decimal("500")),
        gics_branche="Utilities",  # neuer Sektor
        asset_class_id=1,
        korrelations_cluster="value",  # neuer Cluster
        depotstrategie=_depotstrategie(
            max_sektor_pct=Decimal("100"),  # non-bindend
            gesamt_exposure_cap_pct=Decimal("25"),  # AC10-Bandbreite 20-30 %
        ),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "deckeln"
    # x = (0.25*1000 - 100) / (1-0.25) = 200.
    assert entscheid.freigegebene_groesse == Decimal("200").quantize(Decimal("0.00000001"))


def test_ac10_kauf_der_cash_klasse_selbst_umgeht_die_kelly_cap_pruefung() -> None:
    """@trace risikomanagement#AC10 — kauft der Kandidat selbst die
    Cash-Klasse (`CASH_ASSET_CLASS_ID`), erhöht das den Nicht-Cash-Anteil
    nicht -> die Kelly-Cap-Prüfung entfällt, selbst bei einem depotweit
    bereits weit über dem Cap liegenden Nicht-Cash-Exposure."""
    positionen = [
        _position(
            position_id="lot-tech",
            titel_id="AAPL",
            asset_class_id=1,
            gics_branche="Technology",
            menge=Decimal("9"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="growth_tech",
        ),  # 900 Nicht-Cash (90 %)
        _position(
            position_id="lot-cash",
            titel_id="CASH-CHF",
            asset_class_id=CASH_ASSET_CLASS_ID,
            gics_branche=None,
            menge=Decimal("1"),
            einstand_preis=Decimal("100"),
            korrelations_cluster="cash",
        ),  # 100 Cash (10 %)
    ]
    depot_stand = ermittle_depot_stand(positionen)  # Gesamtwert 1000, Nicht-Cash 900 (90 % > 25 %)

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="CASH-CHF-2", ordergroesse=Decimal("500")),
        gics_branche=None,
        asset_class_id=CASH_ASSET_CLASS_ID,
        korrelations_cluster="cash",
        depotstrategie=_depotstrategie(
            max_sektor_pct=Decimal("100"),
            gesamt_exposure_cap_pct=Decimal("25"),
        ),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "durchwinken"
    assert entscheid.freigegebene_groesse == Decimal("500").quantize(Decimal("0.00000001"))


# --- Cold-Start (S-044-Lesson) — erneut verifiziert für ALLE AC8-AC10-Checks ----


def test_cold_start_mit_scharfer_konfiguration_blockiert_ersten_kauf_nicht() -> None:
    """@trace risikomanagement#AC8,AC9,AC10 — coder-Lesson (S-044): JEDE
    neue `x/(x+bestehend)`-Formel braucht einen expliziten Cold-Start-Test
    mit realer, scharf konfigurierter Depotstrategie — sonst blockiert die
    Formel den allerersten Kauf rechnerisch (100 % Konzentration in JEDER
    Dimension). Alle fünf Prüfungen (Sektor/Klasse/Einzelposition/Cluster/
    Kelly-Cap) sind hier absichtlich sehr eng konfiguriert (2 %)."""
    depot_stand = ermittle_depot_stand([])  # leerer, aber nicht-None DepotStand

    entscheid = pruefe_kauf_gate(
        _kauf_order(titel_id="AAPL", ordergroesse=Decimal("1000")),
        gics_branche="Technology",
        asset_class_id=1,
        korrelations_cluster="growth_tech",
        depotstrategie=_depotstrategie(
            max_sektor_pct=Decimal("2"),
            max_einzelposition_pct=Decimal("2"),
            max_anlageklasse_pct={1: Decimal("2")},
            gesamt_exposure_cap_pct=Decimal("2"),
        ),
        depot_stand=depot_stand,
    )

    assert entscheid.entscheid == "durchwinken"
    assert entscheid.freigegebene_groesse == Decimal("1000").quantize(Decimal("0.00000001"))
