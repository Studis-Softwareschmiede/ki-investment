"""Tests für `RedisArbeitsQueue` (Story S-020).

Covers (dateneingang): AC11

`app.scheduler.queue.RedisArbeitsQueue` reiht jede Abfrage als
`Arbeitselement` in eine (je Quelle eigene) Redis-Liste ein (AC11). Statt
eines echten Redis-Servers wird ein minimaler Fake injiziert, der die
`rpush`/`blpop`-Coroutinen-Signatur des `redis.asyncio`-Clients
nachbildet — konsistent mit der DI-Konvention des Projekts (analog
`app.adapters.sockets.base.RateLimiter`s injizierbarem `sleep`).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from app.contracts.scheduler import Arbeitselement
from app.scheduler.queue import RedisArbeitsQueue, queue_key


class _FakeRedis:
    """Minimaler In-Memory-Fake für die im Produktionscode genutzten
    `rpush`/`blpop`-Aufrufe (Listen-Semantik, FIFO)."""

    def __init__(self) -> None:
        self._listen: dict[str, list[str]] = {}

    async def rpush(self, key: str, value: str) -> None:
        self._listen.setdefault(key, []).append(value)

    async def blpop(self, keys: list[str], *, timeout: float) -> tuple[str, str] | None:
        for key in keys:
            werte = self._listen.get(key)
            if werte:
                return key, werte.pop(0)
        return None


def test_enqueue_writes_to_the_sources_own_queue_key() -> None:
    """@trace dateneingang#AC11 — jede Quelle bekommt eine eigene
    Redis-Liste (`scheduler:queue:{data_source_id}`), keine gemeinsame
    Queue über alle Quellen (Voraussetzung für die Entkopplung, AC10)."""
    redis = _FakeRedis()
    queue = RedisArbeitsQueue(redis)
    quelle_id = uuid.uuid4()
    item = Arbeitselement(data_source_id=quelle_id, eingereiht_am=datetime.now(UTC))

    asyncio.run(queue.enqueue(item))

    assert redis._listen[queue_key(quelle_id)] == [item.model_dump_json()]


def test_dequeue_returns_the_enqueued_item_roundtripped() -> None:
    """@trace dateneingang#AC11 — ein eingereihtes Arbeitselement kommt
    strukturell unverändert zurück (JSON-Roundtrip über die Queue)."""
    redis = _FakeRedis()
    queue = RedisArbeitsQueue(redis)
    quelle_id = uuid.uuid4()
    item = Arbeitselement(data_source_id=quelle_id, eingereiht_am=datetime.now(UTC), versuch=2)

    asyncio.run(queue.enqueue(item))
    ergebnis = asyncio.run(queue.dequeue(data_source_id=quelle_id, timeout_sekunden=0.1))

    assert ergebnis == item


def test_dequeue_returns_none_when_queue_is_empty() -> None:
    """@trace dateneingang#AC11 — eine leere Queue liefert `None` statt zu
    blockieren/zu werfen."""
    redis = _FakeRedis()
    queue = RedisArbeitsQueue(redis)

    ergebnis = asyncio.run(queue.dequeue(data_source_id=uuid.uuid4(), timeout_sekunden=0.1))

    assert ergebnis is None


def test_dequeue_only_reads_the_requested_sources_queue() -> None:
    """@trace dateneingang#AC10 — ein Arbeitselement einer anderen Quelle
    wird nicht zurückgegeben (strukturelle Entkopplung — Voraussetzung,
    dass eine Quelle eine andere nie blockiert)."""
    redis = _FakeRedis()
    queue = RedisArbeitsQueue(redis)
    quelle_a, quelle_b = uuid.uuid4(), uuid.uuid4()
    asyncio.run(
        queue.enqueue(Arbeitselement(data_source_id=quelle_a, eingereiht_am=datetime.now(UTC)))
    )

    ergebnis = asyncio.run(queue.dequeue(data_source_id=quelle_b, timeout_sekunden=0.1))

    assert ergebnis is None
