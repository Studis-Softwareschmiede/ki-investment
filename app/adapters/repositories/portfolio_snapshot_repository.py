"""SQLAlchemy-Implementierung des `PortfolioSnapshotRepository`-Ports
(architecture.md §4 `app/adapters/repositories/`, Story S-081,
`docs/specs/frontend-cockpit.md` AC32).

Liest/schreibt `portfolio_snapshot` (data-model.md §5). `verlauf()` ist
rein lesend (konsumiert von `app.api.queries.depot_verlauf`, Boundary
AC2); `schreibe_snapshot()` ist der einzige Schreibpfad — aufgerufen vom
periodischen Scheduler-Job (`app.scheduler.portfolio_snapshot_job`), NICHT
von der Query-/UI-Schicht (kein Write-on-Read, AC32 wörtlich)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import PortfolioSnapshot
from app.domain.portfolio_verlauf.ports import Modus, PortfolioSnapshotEintrag


class SqlAlchemyPortfolioSnapshotRepository:
    """Implementiert `app.domain.portfolio_verlauf.ports
    .PortfolioSnapshotRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def verlauf(
        self,
        *,
        mode: Modus,
        von: datetime | None = None,
        bis: datetime | None = None,
    ) -> list[PortfolioSnapshotEintrag]:
        """AC32: mode-isoliert (→ BR-130), aufsteigend nach `snapshot_at`,
        optional auf `[von, bis]` gefiltert (beidseitig inklusiv)."""
        stmt = select(PortfolioSnapshot).where(PortfolioSnapshot.mode == mode)
        if von is not None:
            stmt = stmt.where(PortfolioSnapshot.snapshot_at >= von)
        if bis is not None:
            stmt = stmt.where(PortfolioSnapshot.snapshot_at <= bis)
        stmt = stmt.order_by(PortfolioSnapshot.snapshot_at.asc())
        zeilen = self._session.execute(stmt).scalars().all()
        return [
            PortfolioSnapshotEintrag(
                zeitpunkt=zeile.snapshot_at,
                portfolio_wert=zeile.total_value_chf,
                cash_quote=zeile.cash_quote_pct,
            )
            for zeile in zeilen
        ]

    def schreibe_snapshot(
        self,
        *,
        mode: Modus,
        zeitpunkt: datetime,
        portfolio_wert: Decimal,
        cash_quote: Decimal,
    ) -> bool:
        """AC32/BR-142: Insert-Then-Catch statt Read-then-Write-Dedupe
        (Lehre aus `app/db/silver.py`/`bronze.py`, `.claude/lessons
        /coder.md`) — der DB-`UNIQUE (mode, snapshot_datum)`-Constraint
        (Migration `1f4a9c6e0b2d`) ist die einzige Nebenläufigkeits-
        sichere Idempotenz-Quelle; ein `IntegrityError` bei bereits
        vorhandenem Snapshot desselben Kalendertags/Modus wird abgefangen
        und als `False` (kein neuer Snapshot) gemeldet, kein Crash."""
        snapshot = PortfolioSnapshot(
            mode=mode,
            snapshot_at=zeitpunkt,
            snapshot_datum=zeitpunkt.date(),
            total_value_chf=portfolio_wert,
            cash_quote_pct=cash_quote,
        )
        self._session.add(snapshot)
        try:
            self._session.commit()
        except IntegrityError:
            self._session.rollback()
            return False
        return True
