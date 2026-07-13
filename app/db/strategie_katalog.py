"""Strategie-/Zeithorizont-Katalog + Cluster-Gate (Story S-037).

Deckt `docs/specs/strategie-exit-regeln.md`:

- **AC2 (Cluster-Freischaltung, deckt E2):** `pruefe_cluster_freischaltung()`
  lädt eine Strategie (aus dem per Migration
  `ddaf9dcc6216_create_strategy_cluster_strategy_and_.py` geseedeten
  18-Strategien-Katalog) und lehnt sie ab, wenn ihr Cluster aktuell nicht
  freigeschaltet ist (`StrategyCluster.freigeschaltet`, BR-135). Die
  Freischaltung ist ein reines DB-Konfigurationsdatum (kein Codewert) —
  sie kann zur Laufzeit per `UPDATE strategy_cluster SET freigeschaltet = ...`
  geändert werden, ohne dass dieses Modul angepasst werden muss (NFR "zur
  Laufzeit konfigurierbar").

- **AC4 (unabhängige Dimensionen):** `pruefe_kombination()` prüft Strategie
  (Cluster-Freischaltung) und Zeithorizont (Existenz) **unabhängig**
  voneinander — der Zeithorizont beeinflusst nie, ob eine
  Strategie/Cluster-Kombination erlaubt ist, und umgekehrt. Es gibt keine
  Kreuz-Validierung zwischen beiden Dimensionen; jede der 18 Strategien ist
  mit jedem der 9 Zeithorizonte kombinierbar.

Beide Prüfungen sind rein deterministisch (Dict-/DB-Lookups, keine
LLM-Beteiligung) — NFR "kein LLM im Entscheidungs-/Order-Pfad".

Was diese Story NICHT löst (Nicht-Ziele/Scope-Abgrenzung, siehe
Coder-Handoff S-037): das Fixieren des vollständigen Attribut-Bündels beim
Kauf (Strategie + Zeithorizont + Exit-Regeln + These, AC1/AC5-AC11) sowie
ein automatischer Fallback auf eine MVP-Cluster-Strategie bei Ablehnung
(Spec-E2 nennt "Fallback bzw. Fehler" als Alternative — ohne eine
spezifizierte Default-Strategie je Nutzerprofil wäre ein Fallback eine
coder-eigene Erfindung; diese Story implementiert daher ausschliesslich den
Fehler-Zweig).
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import Strategy, StrategyCluster, TimeHorizon


class StrategieNichtGefundenError(LookupError):
    """`strategie_id` referenziert keine bekannte Strategie im Katalog."""


class ZeithorizontNichtGefundenError(LookupError):
    """`zeithorizont_id` referenziert keine der 9 Zeithorizont-Stufen."""


class StrategieClusterNichtFreigeschaltetError(ValueError):
    """Der Cluster der angeforderten Strategie ist aktuell nicht
    freigeschaltet (AC2, BR-135, deckt E2)."""


def pruefe_cluster_freischaltung(session: Session, *, strategie_id: uuid.UUID) -> Strategy:
    """Lädt die Strategie zu `strategie_id` und lehnt sie ab, wenn ihr
    Cluster aktuell nicht freigeschaltet ist (AC2, deckt E2).

    Returns:
        Die geladene `Strategy`-Zeile, wenn ihr Cluster freigeschaltet ist.

    Raises:
        StrategieNichtGefundenError: `strategie_id` existiert nicht im Katalog.
        StrategieClusterNichtFreigeschaltetError: der Cluster der Strategie
            ist aktuell nicht freigeschaltet.
    """
    strategie = session.get(Strategy, strategie_id)
    if strategie is None:
        raise StrategieNichtGefundenError(f"Strategie {strategie_id!r} existiert nicht.")

    cluster = session.get(StrategyCluster, strategie.cluster)
    if cluster is None or not cluster.freigeschaltet:
        raise StrategieClusterNichtFreigeschaltetError(
            f"Strategie {strategie.name!r} gehört zum Cluster {strategie.cluster!r}, "
            "das aktuell nicht freigeschaltet ist."
        )
    return strategie


def pruefe_kombination(
    session: Session, *, strategie_id: uuid.UUID, zeithorizont_id: int
) -> tuple[Strategy, TimeHorizon]:
    """Prüft Strategie (Cluster-Freischaltung) und Zeithorizont (Existenz)
    unabhängig voneinander (AC4) — keine Kombination aus einer der 18
    Strategien mit einem der 9 Zeithorizonte wird durch eine Kreuz-Regel
    blockiert; das Ergebnis der Strategie-Prüfung hängt nicht von
    `zeithorizont_id` ab und umgekehrt.

    Returns:
        Tuple `(Strategy, TimeHorizon)`, wenn beide unabhängig gültig sind.

    Raises:
        StrategieNichtGefundenError / StrategieClusterNichtFreigeschaltetError:
            siehe `pruefe_cluster_freischaltung()`.
        ZeithorizontNichtGefundenError: `zeithorizont_id` liegt ausserhalb
            der 9 Stufen bzw. existiert nicht im Katalog.
    """
    strategie = pruefe_cluster_freischaltung(session, strategie_id=strategie_id)

    zeithorizont = session.get(TimeHorizon, zeithorizont_id)
    if zeithorizont is None:
        raise ZeithorizontNichtGefundenError(
            f"Zeithorizont {zeithorizont_id!r} existiert nicht (erwartet 1-9)."
        )

    return strategie, zeithorizont
