"""Tests für den Monitoring-Zyklus `app.orchestration.depot_ueberwachung`
(Story S-032).

Covers (depot-ueberwachung): AC1, AC2, AC3, AC8, AC9

`fuehre_monitoring_zyklus_aus` verdrahtet Depot-Read (AC1, über
`app.domain.portfolio.portfolio_aggregate.ermittle_titel_strategie_exit_regeln`),
die geteilte Datenquellen-Abfrage (AC2, GENAU EINE gebündelte Anfrage,
`app.orchestration.datasource_query.hole_signal_buendel`), die je
Anlageklasse überwachten Grössen (AC3), die Toggle-Ausnahme für gehaltene
Titel (AC8, deckt A1) und die Frische-Fenster-Prüfung (AC9, deckt E1) zu
einem Zyklus-Ergebnis.

SQLite (in-memory) reicht aus (analog `tests/orchestration
/test_datasource_query.py`, `tests/adapters/repositories
/test_position_repository.py`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.orchestration.depot_ueberwachung as depot_ueberwachung_orchestrierung
from app.core import monitoring_audit_log
from app.db.base import Base
from app.db.models import (
    AssetClass,
    DataSource,
    DataSourceAssetClass,
    ExitRule,
    Instrument,
    MarketDataGold,
    Position,
    Strategy,
    TimeHorizon,
)
from app.orchestration.datasource_query import hole_signal_buendel
from app.orchestration.depot_ueberwachung import fuehre_monitoring_zyklus_aus

_JETZT = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolieren():
    monitoring_audit_log.reset_fuer_tests()
    yield
    monitoring_audit_log.reset_fuer_tests()


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True))
        db_session.add(AssetClass(id=7, name="Krypto", prio_stufe="MVP", aktiv=True))
        db_session.add(
            TimeHorizon(
                id=8,
                name="Buy-and-Hold",
                transaktionskosten_relevanz="MINIMAL",
                break_even_anforderung="Jahresrendite nach Kosten",
            )
        )
        strategy = Strategy(
            id=uuid.uuid4(), name="Index", cluster="passiv_regelbasiert", stufe="MVP"
        )
        db_session.add(strategy)
        db_session.commit()
        yield db_session


def _instrument(session: Session, *, symbol: str, asset_class_id: int = 1) -> Instrument:
    instrument = Instrument(
        id=uuid.uuid4(), symbol=symbol, name=symbol, asset_class_id=asset_class_id, currency="CHF"
    )
    session.add(instrument)
    session.commit()
    return instrument


def _strategy_id(session: Session) -> uuid.UUID:
    return session.scalars(select(Strategy.id)).first()


def _position(session: Session, *, instrument: Instrument, mit_exit_rule: bool = True) -> Position:
    position = Position(
        id=uuid.uuid4(),
        instrument_id=instrument.id,
        asset_class_id=instrument.asset_class_id,
        strategy_id=_strategy_id(session),
        time_horizon_id=8,
        these="These.",
        menge=Decimal("10"),
        einstand_preis=Decimal("100"),
        mode="simuliert",
        status="offen",
    )
    session.add(position)
    session.flush()
    if mit_exit_rule:
        session.add(
            ExitRule(position_id=position.id, stop_typ="fix_pct", stop_loss_pct=Decimal("-15"))
        )
    session.commit()
    return position


def _quelle(session: Session, *, name: str) -> DataSource:
    quelle = DataSource(
        id=uuid.uuid4(),
        name=name,
        kategorie="equity_fundamentals",
        qualitaet="hoch",
        frequenz_sekunden=60,
        aktiv=True,
    )
    session.add(quelle)
    session.commit()
    return quelle


def _mappe_anlageklasse(session: Session, *, quelle: DataSource, anlageklasse: int) -> None:
    session.add(DataSourceAssetClass(data_source_id=quelle.id, asset_class_id=anlageklasse))
    session.commit()


def _gold_zeile(
    session: Session, *, quelle: DataSource, symbol: str, observed_at: datetime
) -> None:
    session.add(
        MarketDataGold(
            silver_id=uuid.uuid4(),
            silver_observed_at=observed_at,
            data_source_id=quelle.id,
            source_event_id=f"{quelle.name}:{symbol}:{observed_at.isoformat()}",
            symbol=symbol,
            angereicherter_wert=Decimal("400"),
            qualitaetsindikator="hoch",
            observed_at=observed_at,
        )
    )
    session.commit()


def test_vollstaendiger_und_bewertbarer_titel_erscheint_mit_signalen_und_groessen(
    session: Session,
) -> None:
    """@trace depot-ueberwachung#AC1,AC2,AC3 — ein vollständiger,
    aktueller Titel erscheint mit Signal-Bündel (AC2, über die geteilte
    Abfrage) und den je Klasse überwachten Grössen (AC3); kein
    Protokolleintrag."""
    instrument = _instrument(session, symbol="AAPL")
    _position(session, instrument=instrument)
    quelle = _quelle(session, name="IBKR")
    _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)
    _gold_zeile(
        session, quelle=quelle, symbol=str(instrument.id), observed_at=_JETZT - timedelta(hours=1)
    )

    ergebnis = fuehre_monitoring_zyklus_aus(session, mode="simuliert", jetzt=_JETZT)

    assert ergebnis.protokoll == ()
    [titel] = ergebnis.ueberwachte_titel
    assert titel.titel_id == str(instrument.id)
    assert titel.anlageklasse == 1
    assert titel.strategie == "Index"
    assert titel.ueberwachte_groessen == (
        "news_katalysatoren",
        "relativer_kurssturz",
        "sentiment_kippen",
        "momentum_verlust",
    )
    assert titel.signal_buendel.signale != []
    assert monitoring_audit_log.alle_eintraege() == ()


def test_titel_ohne_exit_rule_wird_als_unvollstaendig_protokolliert(session: Session) -> None:
    """@trace depot-ueberwachung#AC1 — fehlt das (beim Kauf fixierte)
    Exit-Regel-Bündel (hier: keine `exit_rule`-Zeile), wird der Titel als
    unvollständig protokolliert und NICHT weiter überwacht (nicht
    stillschweigend übersprungen)."""
    instrument = _instrument(session, symbol="AAPL")
    _position(session, instrument=instrument, mit_exit_rule=False)

    ergebnis = fuehre_monitoring_zyklus_aus(session, mode="simuliert", jetzt=_JETZT)

    assert ergebnis.ueberwachte_titel == ()
    [eintrag] = ergebnis.protokoll
    assert eintrag.titel_id == str(instrument.id)
    assert eintrag.grund == "unvollstaendig"
    assert "exit_regeln" in eintrag.detail
    assert monitoring_audit_log.alle_eintraege() == ergebnis.protokoll


def test_deaktivierte_anlageklasse_schaltet_ueberwachung_nicht_ab(session: Session) -> None:
    """@trace depot-ueberwachung#AC8 — deckt A1: eine per Toggle
    deaktivierte Anlageklasse (`AssetClass.aktiv=False`) lässt einen
    bereits gehaltenen, vollständigen und bewertbaren Titel trotzdem in
    `ueberwachte_titel` erscheinen."""
    instrument = _instrument(session, symbol="AAPL")
    _position(session, instrument=instrument)
    quelle = _quelle(session, name="IBKR")
    _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)
    _gold_zeile(
        session, quelle=quelle, symbol=str(instrument.id), observed_at=_JETZT - timedelta(hours=1)
    )

    asset_class = session.get(AssetClass, 1)
    asset_class.aktiv = False
    session.commit()

    ergebnis = fuehre_monitoring_zyklus_aus(session, mode="simuliert", jetzt=_JETZT)

    [titel] = ergebnis.ueberwachte_titel
    assert titel.titel_id == str(instrument.id)
    assert ergebnis.protokoll == ()


def test_titel_ohne_signal_buendel_wird_als_nicht_bewertbar_protokolliert(
    session: Session,
) -> None:
    """@trace depot-ueberwachung#AC9 — deckt E1: keine Registry-Quelle für
    die Anlageklasse (kein Signal-Bündel) → der Titel wird als nicht
    bewertbar protokolliert, kein Ereignis fabriziert (kein Eintrag in
    `ueberwachte_titel`)."""
    instrument = _instrument(session, symbol="AAPL")
    _position(session, instrument=instrument)

    ergebnis = fuehre_monitoring_zyklus_aus(session, mode="simuliert", jetzt=_JETZT)

    assert ergebnis.ueberwachte_titel == ()
    [eintrag] = ergebnis.protokoll
    assert eintrag.titel_id == str(instrument.id)
    assert eintrag.grund == "nicht_bewertbar"


def test_titel_mit_veraltetem_signal_wird_als_nicht_bewertbar_protokolliert(
    session: Session,
) -> None:
    """@trace depot-ueberwachung#AC9 — deckt E1: ein Signal-Bündel, dessen
    jüngstes Signal älter als das konfigurierte Frische-Fenster (Default
    24h) ist, macht den Titel nicht bewertbar."""
    instrument = _instrument(session, symbol="AAPL")
    _position(session, instrument=instrument)
    quelle = _quelle(session, name="IBKR")
    _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)
    _gold_zeile(
        session, quelle=quelle, symbol=str(instrument.id), observed_at=_JETZT - timedelta(hours=48)
    )

    ergebnis = fuehre_monitoring_zyklus_aus(session, mode="simuliert", jetzt=_JETZT)

    assert ergebnis.ueberwachte_titel == ()
    [eintrag] = ergebnis.protokoll
    assert eintrag.grund == "nicht_bewertbar"


def test_mehrere_titel_stellen_genau_eine_gebuendelte_abfrage(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@trace depot-ueberwachung#AC2 — mehrere gehaltene Titel lösen
    GENAU EINEN Aufruf der geteilten Datenquellen-Abfrage aus (gebündelt,
    ein `TitelAnfrage`-Eintrag je Titel), keine eigene Anbindung, kein
    Aufruf je Titel."""
    instrument_a = _instrument(session, symbol="AAPL")
    instrument_b = _instrument(session, symbol="MSFT")
    _position(session, instrument=instrument_a)
    _position(session, instrument=instrument_b)
    quelle = _quelle(session, name="IBKR")
    _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)
    _gold_zeile(
        session,
        quelle=quelle,
        symbol=str(instrument_a.id),
        observed_at=_JETZT - timedelta(hours=1),
    )
    _gold_zeile(
        session,
        quelle=quelle,
        symbol=str(instrument_b.id),
        observed_at=_JETZT - timedelta(hours=1),
    )

    aufrufe: list[int] = []

    def _zaehlender_wrapper(session_arg, anfrage):
        aufrufe.append(len(anfrage.titel_anfragen))
        return hole_signal_buendel(session_arg, anfrage)

    monkeypatch.setattr(
        depot_ueberwachung_orchestrierung, "hole_signal_buendel", _zaehlender_wrapper
    )

    ergebnis = fuehre_monitoring_zyklus_aus(session, mode="simuliert", jetzt=_JETZT)

    assert aufrufe == [2]
    assert {titel.titel_id for titel in ergebnis.ueberwachte_titel} == {
        str(instrument_a.id),
        str(instrument_b.id),
    }
