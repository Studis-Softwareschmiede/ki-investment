"""SQLAlchemy-Implementierung des `HybridEntscheidungRepository`-Ports
(architecture.md §4 `app/adapters/repositories/`, Story S-080, Spec
`docs/specs/frontend-cockpit.md` AC29).

Implementiert `app.domain.hybrid_entscheidung.ports
.HybridEntscheidungRepository` strukturell (Protocol, keine explizite
Vererbung nötig, analog `app.adapters.repositories.gate_result_repository
.SqlAlchemyGateErgebnisRepository`) gegen die `hybrid_entscheid`-Tabelle
(`app.db.models.HybridEntscheid`, S-080). Read-only: der Status-Wechsel-
Schreibpfad (AC30 "bestätigen"/"ablehnen") lebt bewusst separat in
`app.db.hybrid_entscheide` (Control-Plane-Aufrufer, ausserhalb der
AC2-Boundary)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import HybridEntscheid, Instrument
from app.domain.hybrid_entscheidung.ports import OffenerEntscheidZeile


class SqlAlchemyHybridEntscheidungRepository:
    """Liest ausschliesslich `status="offen"` **und** `mode="simuliert"`
    (BR-141/AC30-MVP-Live-Sperre — auch wenn das Schema `mode` bereits auf
    `simuliert` fixiert, filtert die Query defensiv mit, statt sich
    implizit auf den DB-CHECK zu verlassen), aufsteigend nach `frist`
    (nächster Ablauf zuerst). `Instrument`-Join löst `titel`/`name` auf
    (S-066/S-071-Lehre — kein rohes `titel_id` als Anzeigefeld)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def offene_entscheide(self) -> list[OffenerEntscheidZeile]:
        stmt = (
            select(HybridEntscheid, Instrument.symbol, Instrument.name)
            .join(Instrument, Instrument.id == HybridEntscheid.instrument_id)
            .where(HybridEntscheid.status == "offen", HybridEntscheid.mode == "simuliert")
            .order_by(HybridEntscheid.frist.asc())
        )
        zeilen = self._session.execute(stmt).all()
        return [
            OffenerEntscheidZeile(
                entscheid_id=str(zeile.id),
                titel_id=str(zeile.instrument_id),
                titel=symbol,
                name=name,
                richtung=zeile.richtung,  # type: ignore[arg-type]
                groesse=zeile.groesse,
                vorgeschlagene_order=zeile.vorgeschlagene_order,
                frist=zeile.frist,
                begruendung=zeile.begruendung,
                erstellt_am=zeile.erstellt_am,
            )
            for zeile, symbol, name in zeilen
        ]
