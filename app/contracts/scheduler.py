"""Modul-Vertrag Scheduler — Arbeitselement der Queue-of-Work (Story
S-020, Spec `docs/specs/dateneingang.md` AC11: "Jede Abfrage wird als
Arbeitselement in eine Queue-of-Work eingereiht ...").

architecture.md §2 P2 ("Explizite Modul-Verträge"): der Übergang
Scheduler → Queue → Worker läuft über dieses typisierte DTO, damit die
Redis-Serialisierung (`app.scheduler.queue.RedisArbeitsQueue`) und die
Worker-Verarbeitung (`app.scheduler.worker.Worker`) denselben Vertrag
teilen — keine impliziten `dict`-Strukturen an der Queue-Grenze.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Arbeitselement(BaseModel):
    """Eine geplante Abfrage EINER Quelle (AC11 "Arbeitselement").

    `versuch` zählt Verarbeitungsversuche (beginnend bei 1) — der Worker
    erhöht ihn bei jedem Retry nach einem transienten Quellenfehler
    (AC10); übersteigt er `Settings.scheduler_max_versuche`, wandert das
    Arbeitselement in die Dead-Letter-Queue statt erneut eingereiht zu
    werden."""

    model_config = ConfigDict(frozen=True)

    data_source_id: uuid.UUID
    eingereiht_am: datetime
    versuch: int = Field(default=1, ge=1)

    def naechster_versuch(self) -> "Arbeitselement":
        """Liefert eine Kopie mit um 1 erhöhtem `versuch` (Retry nach
        transientem Fehler, AC10) — `Arbeitselement` ist unveränderlich
        (`frozen=True`), daher keine In-Place-Mutation."""
        return self.model_copy(update={"versuch": self.versuch + 1})


__all__ = ["Arbeitselement"]
