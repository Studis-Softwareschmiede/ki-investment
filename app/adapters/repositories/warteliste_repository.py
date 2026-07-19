"""SQLAlchemy-Implementierung des `WartelisteRepository`-Ports
(architecture.md §4 `app/adapters/repositories/`, Story S-079,
`docs/specs/frontend-cockpit.md` AC26).

Liest `warteliste_eintrag` (data-model.md §4) + einen `instrument`-Join
für den menschenlesbaren Titel (Symbol/Name) — analog zu
`app.adapters.repositories.analysis_result_repository
.SqlAlchemyKandidatenRepository` (S-066 Iteration 1, Titel-Auflösung statt
roher `instrument_id`, coder-Lesson S-073: "gilt für JEDE AC mit
demselben Wortlaut").

Rein lesend (AC26, kein `session.add`/`commit`): dieser Adapter bucht/
entscheidet/schreibt nichts. Bewusst UNABHÄNGIG von
`app.domain.risikomanagement` (Boundary AC2) — die Tabelle wird
ausschliesslich vom Demo-Seed befüllt (AC28)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Instrument
from app.db.models import WartelisteEintrag as WartelisteEintragModell
from app.domain.warteliste.ports import Modus, WartelisteEintrag


class SqlAlchemyWartelisteRepository:
    """Implementiert `app.domain.warteliste.ports.WartelisteRepository`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def liste_warteliste(self, *, mode: Modus) -> list[WartelisteEintrag]:
        """AC26: mode-isoliert (→ BR-130), neueste zuerst."""
        zeilen = (
            self._session.execute(
                select(WartelisteEintragModell)
                .where(WartelisteEintragModell.mode == mode)
                .order_by(WartelisteEintragModell.blockiert_am.desc())
            )
            .scalars()
            .all()
        )
        if not zeilen:
            return []

        instrumente_je_id = {
            zeile.id: zeile
            for zeile in self._session.execute(
                select(Instrument).where(
                    Instrument.id.in_([eintrag.instrument_id for eintrag in zeilen])
                )
            )
            .scalars()
            .all()
        }
        return [
            WartelisteEintrag(
                id=str(eintrag.id),
                titel_id=str(eintrag.instrument_id),
                titel=instrumente_je_id[eintrag.instrument_id].symbol,
                name=instrumente_je_id[eintrag.instrument_id].name,
                asset_class_id=eintrag.asset_class_id,
                geplante_groesse=eintrag.geplante_groesse,
                blockade_grund=eintrag.blockade_grund,
                blockiert_am=eintrag.blockiert_am,
            )
            for eintrag in zeilen
        ]
