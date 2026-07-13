"""Dead-Letter-Queue-Store — dauerhafte Ablage endgültig aufgegebener
Arbeitselemente (Story S-020, Spec `docs/specs/dateneingang.md` AC10).

`app.scheduler.worker.Worker` ruft `record_dead_letter()` genau dann auf,
wenn ein `Arbeitselement` (`app.scheduler.queue.Arbeitselement`) nach
erschöpften Exponential-Backoff-Versuchen endgültig aufgegeben wird (AC10:
"... wird das Arbeitselement in eine Dead-Letter-Queue verschoben und
protokolliert"). Diese Tabelle ist die durable, abfragbare Seite davon
(`app.db.models.IngestDeadLetter`, data-model.md §7); die Protokollierung
selbst (Log-Zeile) erfolgt bereits im Worker via Standard-`logging`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IngestDeadLetter


def record_dead_letter(
    session: Session,
    *,
    data_source_id: uuid.UUID,
    fehler: str,
    retry_count: int,
    source_event_id: str | None = None,
    payload: Any | None = None,
    erstellt_am: datetime | None = None,
) -> IngestDeadLetter:
    """Legt einen Dead-Letter-Datensatz an (AC10) — ein reiner Insert, kein
    Dedupe/Idempotenz-Mechanismus: jede endgültig aufgegebene Abfrage ist
    ein eigenes, meldenswertes Ereignis (analog
    `app.core.quellenausfall.melde_ausfall`). `erstellt_am` ist wie dessen
    `zeitstempel`-Parameter injizierbar (Default: jetzt) — deterministische
    Zeitachse für Tests."""
    eintrag = IngestDeadLetter(
        id=uuid.uuid4(),
        data_source_id=data_source_id,
        source_event_id=source_event_id,
        payload=payload,
        fehler=fehler,
        retry_count=retry_count,
        created_at=erstellt_am or datetime.now(UTC),
    )
    session.add(eintrag)
    session.commit()
    return eintrag


def dead_letters_for_source(
    session: Session, *, data_source_id: uuid.UUID
) -> list[IngestDeadLetter]:
    """Liest alle bislang aufgezeichneten Dead-Letter-Zeilen einer Quelle
    (neueste zuerst) — DLQ-Backlog-Monitoring (data-model.md §8-Index)."""
    return list(
        session.execute(
            select(IngestDeadLetter)
            .where(IngestDeadLetter.data_source_id == data_source_id)
            .order_by(IngestDeadLetter.created_at.desc())
        )
        .scalars()
        .all()
    )


__all__ = ["record_dead_letter", "dead_letters_for_source"]
