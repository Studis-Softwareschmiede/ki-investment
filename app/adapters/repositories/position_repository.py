"""SQLAlchemy-Implementierung des `PositionRepository`-Ports (architecture.md
§4 `app/adapters/repositories/`, Modul 16 Depotmodul, S-015).

Implementiert `app.domain.portfolio.ports.PositionRepository` strukturell
(Protocol, keine explizite Vererbung nötig) gegen die `position`-Tabelle
(`app.db.models.Position`, `docs/data-model.md` §4).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Position


class SqlAlchemyPositionRepository:
    """Liest den aktuellen Bestand aus der `position`-Tabelle über eine
    injizierte SQLAlchemy-`Session` (Ports & Adapters, P1 — kein eigenes
    Connection-/Engine-Management hier)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def aktuelle_menge(self, titel_id: str) -> Decimal:
        """Summe der `menge` aller offenen (`status == "offen"`) Positionen
        für `titel_id` — `Decimal("0")`, falls keine offene Position
        existiert (oder `titel_id` keine gültige UUID ist — dann kann
        strukturell keine Position dazu existieren). Eine Summe statt einer
        Einzelwert-Abfrage deckt auch den (vom Modell nicht
        ausgeschlossenen) Fall mehrerer offener Positionen desselben Titels
        konsistent ab."""
        try:
            instrument_id = uuid.UUID(titel_id)
        except (ValueError, AttributeError, TypeError):
            return Decimal("0")

        stmt = select(Position.menge).where(
            Position.instrument_id == instrument_id, Position.status == "offen"
        )
        mengen = self._session.scalars(stmt).all()
        return sum(mengen, Decimal("0"))
