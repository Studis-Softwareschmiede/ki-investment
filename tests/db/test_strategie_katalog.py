"""Tests fuer den Cluster-Gate + Unabhaengigkeits-Check (Story S-037).

Covers (strategie-exit-regeln): AC2, AC4

- AC2 (deckt E2): `pruefe_cluster_freischaltung()` lehnt eine Strategie aus
  einem nicht freigeschalteten Cluster ab und laesst eine Strategie aus dem
  freigeschalteten MVP-Cluster (Passiv/Regelbasiert) durch. Zusaetzlich wird
  die NFR "zur Laufzeit konfigurierbar" verifiziert: ein reines
  DB-`UPDATE` auf `StrategyCluster.freigeschaltet` aendert das Gate-Ergebnis
  ohne Code-Aenderung.
- AC4: `pruefe_kombination()` zeigt, dass Strategie- und
  Zeithorizont-Pruefung unabhaengig voneinander sind — fuer eine
  freigeschaltete Strategie ist JEDER der 9 Zeithorizonte kombinierbar,
  keine Kombination wird durch eine Kreuz-Regel blockiert.

`app.db.strategie_katalog` ist deterministisch (reine DB-Lookups) — kein
LLM im Pruefpfad (NFR).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import Strategy, StrategyCluster, TimeHorizon
from app.db.strategie_katalog import (
    StrategieClusterNichtFreigeschaltetError,
    StrategieNichtGefundenError,
    ZeithorizontNichtGefundenError,
    pruefe_cluster_freischaltung,
    pruefe_kombination,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add_all(
            [
                StrategyCluster(
                    code="passiv_regelbasiert", name="Passiv/Regelbasiert", freigeschaltet=True
                ),
                StrategyCluster(
                    code="aktiv_fundamental", name="Aktiv-Fundamental", freigeschaltet=False
                ),
            ]
        )
        db_session.add_all(
            TimeHorizon(
                id=i,
                name=f"Stufe {i}",
                transaktionskosten_relevanz="MITTEL",
                break_even_anforderung="1-3 % pro Position",
            )
            for i in range(1, 10)
        )
        db_session.commit()
        yield db_session


def _add_strategy(session: Session, *, name: str, cluster: str, stufe: str) -> uuid.UUID:
    strategie = Strategy(name=name, cluster=cluster, stufe=stufe)
    session.add(strategie)
    session.commit()
    session.refresh(strategie)
    return strategie.id


def test_freigeschaltete_mvp_strategie_wird_akzeptiert(session: Session) -> None:
    """@trace strategie-exit-regeln#AC2 — Strategie aus dem freigeschalteten
    MVP-Cluster (Passiv/Regelbasiert) wird nicht abgelehnt."""
    strategie_id = _add_strategy(session, name="Index", cluster="passiv_regelbasiert", stufe="MVP")

    strategie = pruefe_cluster_freischaltung(session, strategie_id=strategie_id)

    assert strategie.name == "Index"


def test_strategie_ausserhalb_freigeschaltetem_cluster_wird_abgelehnt(session: Session) -> None:
    """@trace strategie-exit-regeln#AC2 — deckt E2: Anforderung einer
    Strategie ausserhalb des freigeschalteten Clusters wird abgelehnt."""
    strategie_id = _add_strategy(session, name="Value", cluster="aktiv_fundamental", stufe="Stufe2")

    with pytest.raises(StrategieClusterNichtFreigeschaltetError):
        pruefe_cluster_freischaltung(session, strategie_id=strategie_id)


def test_unbekannte_strategie_id_wird_abgelehnt(session: Session) -> None:
    """@trace strategie-exit-regeln#AC2 — eine nicht existierende
    `strategie_id` wird als Katalog-Fehler behandelt, nicht stillschweigend
    durchgelassen."""
    with pytest.raises(StrategieNichtGefundenError):
        pruefe_cluster_freischaltung(session, strategie_id=uuid.uuid4())


def test_cluster_freischaltung_ist_zur_laufzeit_per_update_konfigurierbar(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC2 — NFR "zur Laufzeit konfigurierbar":
    ein reines DB-UPDATE auf `StrategyCluster.freigeschaltet` aendert das
    Gate-Ergebnis ohne Code-/Migrations-Aenderung."""
    strategie_id = _add_strategy(session, name="Value", cluster="aktiv_fundamental", stufe="Stufe2")

    with pytest.raises(StrategieClusterNichtFreigeschaltetError):
        pruefe_cluster_freischaltung(session, strategie_id=strategie_id)

    cluster = session.get(StrategyCluster, "aktiv_fundamental")
    cluster.freigeschaltet = True
    session.commit()

    strategie = pruefe_cluster_freischaltung(session, strategie_id=strategie_id)
    assert strategie.name == "Value"


def test_freigeschaltete_strategie_ist_mit_jedem_der_9_zeithorizonte_kombinierbar(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC4 — Strategie und Zeithorizont sind
    unabhaengige Dimensionen: dieselbe (freigeschaltete) Strategie ist mit
    JEDEM der 9 Zeithorizonte kombinierbar, keine Kombination wird
    systemseitig blockiert."""
    strategie_id = _add_strategy(session, name="DCA", cluster="passiv_regelbasiert", stufe="MVP")

    ergebnisse = [
        pruefe_kombination(session, strategie_id=strategie_id, zeithorizont_id=horizont_id)
        for horizont_id in range(1, 10)
    ]

    assert len(ergebnisse) == 9
    assert all(strategie.name == "DCA" for strategie, _ in ergebnisse)
    assert {horizont.id for _, horizont in ergebnisse} == set(range(1, 10))


def test_cluster_ablehnung_ist_unabhaengig_vom_gewaehlten_zeithorizont(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC4 — die Cluster-Ablehnung einer
    Strategie (AC2) tritt fuer JEDEN Zeithorizont identisch ein; der
    Zeithorizont aendert das Cluster-Gate-Ergebnis nicht."""
    strategie_id = _add_strategy(session, name="Value", cluster="aktiv_fundamental", stufe="Stufe2")

    for horizont_id in range(1, 10):
        with pytest.raises(StrategieClusterNichtFreigeschaltetError):
            pruefe_kombination(session, strategie_id=strategie_id, zeithorizont_id=horizont_id)


def test_unbekannter_zeithorizont_wird_unabhaengig_von_der_strategie_abgelehnt(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC4 — die Zeithorizont-Existenzpruefung
    ist unabhaengig von der Strategie-Cluster-Pruefung (getrennte
    Fehlerklassen, keine Kreuz-Kopplung)."""
    strategie_id = _add_strategy(session, name="Index", cluster="passiv_regelbasiert", stufe="MVP")

    with pytest.raises(ZeithorizontNichtGefundenError):
        pruefe_kombination(session, strategie_id=strategie_id, zeithorizont_id=99)
