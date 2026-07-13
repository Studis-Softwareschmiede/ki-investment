"""Queue-of-Work je Quelle (AC11, `docs/specs/dateneingang.md`: "Jede
Abfrage wird als Arbeitselement in eine Queue-of-Work eingereiht und von
Workern ... abgearbeitet"). ADR-006 (architecture.md §8): Redis als
Scheduler-Queue, at-least-once-Zustellung (P8) — Konsumenten
(`app.scheduler.worker.Worker`) sind idempotent (dieselbe Abfrage doppelt
verarbeitet erzeugt keinen doppelten Bronze-Eintrag, siehe
`app.db.bronze.record_observation`, AC9 `datenqualitaet`).

Eine eigene Redis-Liste je Quelle (`scheduler:queue:{data_source_id}")
entkoppelt die Queues strukturell voneinander — ein Worker liest
ausschliesslich aus der Liste seiner eigenen Quelle, wodurch eine
gedrosselte/fehlschlagende Quelle nie die Queue einer anderen blockiert
(AC10-Edge-Case "ohne andere Quellen zu blockieren").
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.contracts.scheduler import Arbeitselement


def queue_key(data_source_id: uuid.UUID) -> str:
    """Redis-Key der Queue-of-Work EINER Quelle."""
    return f"scheduler:queue:{data_source_id}"


class ArbeitsQueue(Protocol):
    """Port für die Queue-of-Work (AC11) — `RedisArbeitsQueue` ist die
    Produktions-Implementierung; Tests injizieren einen Fake mit
    derselben Signatur (Hexagonal, analog `app.adapters.sockets.base
    .SocketAdapter`)."""

    async def enqueue(self, item: Arbeitselement) -> None: ...

    async def dequeue(
        self, *, data_source_id: uuid.UUID, timeout_sekunden: float
    ) -> Arbeitselement | None: ...


class RedisArbeitsQueue:
    """Redis-Listen-basierte `ArbeitsQueue` (ADR-006). `redis_client` ist
    ein async Redis-Client (`redis.asyncio.Redis`) bzw. jedes Objekt mit
    kompatiblen `rpush`/`blpop`-Coroutinen — injiziert statt hier
    instanziiert, damit Verbindungsaufbau/-lebenszyklus beim Aufrufer
    bleibt (fastapi/A04-Analogon: Ressourcen-Lebenszyklus nicht in der
    Fach-Klasse selbst)."""

    def __init__(self, redis_client) -> None:  # type: ignore[no-untyped-def]
        self._redis = redis_client

    async def enqueue(self, item: Arbeitselement) -> None:
        await self._redis.rpush(queue_key(item.data_source_id), item.model_dump_json())

    async def dequeue(
        self, *, data_source_id: uuid.UUID, timeout_sekunden: float
    ) -> Arbeitselement | None:
        ergebnis = await self._redis.blpop([queue_key(data_source_id)], timeout=timeout_sekunden)
        if ergebnis is None:
            return None
        _key, roh = ergebnis
        if isinstance(roh, bytes):
            roh = roh.decode("utf-8")
        return Arbeitselement.model_validate_json(roh)


__all__ = ["ArbeitsQueue", "RedisArbeitsQueue", "queue_key"]
