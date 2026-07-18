"""SQLAlchemy-Implementierung des `GateErgebnisRepository`-Ports
(architecture.md §4 `app/adapters/repositories/`, Story S-068, Spec
`docs/specs/frontend-cockpit.md` AC8).

Implementiert `app.domain.lernschleife.ports.GateErgebnisRepository`
strukturell (Protocol, keine explizite Vererbung nötig, analog
`app.adapters.repositories.position_repository
.SqlAlchemyPositionRepository`) gegen die `gate_result`-Tabelle
(`app.db.models.GateResult`, S-062). Read-only: kein Schreibpfad — die
Schreibseite bleibt unverändert `app.db.gate_result
.registriere_gate_ergebnis`."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GateResult
from app.domain.lernschleife.ports import LetztesGateErgebnis


class SqlAlchemyGateErgebnisRepository:
    """Liest die zuletzt persistierte `gate_result`-Zeile über ALLE Trials
    hinweg (`created_at` absteigend, erste Zeile)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def letztes_ergebnis(self) -> LetztesGateErgebnis | None:
        zeile = (
            self._session.execute(
                select(GateResult).order_by(GateResult.created_at.desc()).limit(1)
            )
            .scalars()
            .first()
        )
        if zeile is None:
            return None
        return LetztesGateErgebnis(ampel=zeile.ampel, ermittelt_am=zeile.created_at)  # type: ignore[arg-type]
