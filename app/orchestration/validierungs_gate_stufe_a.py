"""Validierungs-Gate Stufe A — Verdrahtung Trial-Registry + Berechnungskern
(Story S-060, Spec `docs/specs/lernschleife.md` AC4-AC7).

architecture.md §4 P1 (Dependency-Richtung nach innen): der reine
Domain-Kern `app.domain.lernschleife.stage_a` darf nicht von `app.db.*`
abhängen. Diese Orchestration-Schicht schliesst die Lücke: sie liest
`n_trials` aus der Trial-Registry (S-059, `app.db.trial_registry`) und
übergibt sie zusammen mit der bereits aufbereiteten Trade-Historie an
`bewerte_stufe_a` (AC7: "korrigiert um die aus der Trial-Registry bekannte
Anzahl aller getesteten Regelvarianten").
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.contracts.lernschleife import StufeAKonfiguration, StufeAReport, TradeErgebnis
from app.db.trial_registry import anzahl_trials
from app.domain.lernschleife.stage_a import bewerte_stufe_a


def pruefe_stufe_a(
    session: Session,
    *,
    hypothesis_id: uuid.UUID,
    trades: Sequence[TradeErgebnis],
    konfiguration: StufeAKonfiguration | None = None,
) -> StufeAReport:
    """Liest die Trial-Anzahl der Hypothese aus der Trial-Registry (AC3,
    S-059) und bewertet Stufe A (AC4-AC7) über den reinen Berechnungskern.
    Die Variante selbst MUSS bereits registriert sein (`anzahl_trials`
    liefert sonst 0, was `berechne_deflated_sharpe_ratio` als
    "n_trials >= 1"-Verstoss ablehnt)."""
    n_trials = anzahl_trials(session, hypothesis_id=hypothesis_id)
    return bewerte_stufe_a(
        trades,
        hypothesis_id=hypothesis_id,
        n_trials=n_trials,
        konfiguration=konfiguration,
    )


__all__ = ["pruefe_stufe_a"]
