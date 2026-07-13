"""Tests für `Worker` (Story S-020).

Covers (dateneingang): AC10, AC11

`app.scheduler.worker.Worker` bedient die Queue-of-Work EINER Quelle
(AC11), gedrosselt durch den injizierten `TokenBucket`. Bei einem
transienten Fehler (AC10) wird das Arbeitselement mit Exponential Backoff
erneut eingereiht; nach `max_versuche` erschöpften Versuchen wandert es
über den injizierten `dead_letter_sink` in die Dead-Letter-Queue.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import pytest

from app.contracts.scheduler import Arbeitselement
from app.scheduler.queue import ArbeitsQueue
from app.scheduler.token_bucket import TokenBucket
from app.scheduler.worker import Worker


class _FakeQueue(ArbeitsQueue):
    """FIFO-Queue EINER Quelle (Test-Double, kein Redis nötig)."""

    def __init__(self, *anfangselemente: Arbeitselement) -> None:
        self._elemente: list[Arbeitselement] = list(anfangselemente)
        self.enqueue_calls: list[Arbeitselement] = []

    async def enqueue(self, item: Arbeitselement) -> None:
        self.enqueue_calls.append(item)
        self._elemente.append(item)

    async def dequeue(self, *, data_source_id, timeout_sekunden):
        for i, element in enumerate(self._elemente):
            if element.data_source_id == data_source_id:
                return self._elemente.pop(i)
        return None


class _SofortigerBucket(TokenBucket):
    """Ein Bucket, der nie drosselt — die Token-Bucket-Mechanik selbst ist
    bereits in `test_token_bucket.py` gedeckt; hier soll nur die
    Worker-Retry-/DLQ-Logik isoliert getestet werden."""

    def __init__(self) -> None:
        super().__init__(capacity=1_000_000, refill_rate_pro_sekunde=1_000_000.0)


class _FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        # Kein echtes Warten — dem Test-Event-Loop trotzdem einmal die
        # Kontrolle abgeben, damit `asyncio.ensure_future`-Retry-Tasks
        # zum Zug kommen.
        await asyncio.sleep(0)


def _item(quelle_id: uuid.UUID, *, versuch: int = 1) -> Arbeitselement:
    return Arbeitselement(
        data_source_id=quelle_id, eingereiht_am=datetime.now(UTC), versuch=versuch
    )


def test_empty_queue_returns_false_and_does_not_call_abrufen() -> None:
    """@trace dateneingang#AC11 — eine leere Queue führt zu keinem
    Verarbeitungsversuch."""
    quelle_id = uuid.uuid4()
    queue = _FakeQueue()
    aufgerufen: list[Arbeitselement] = []

    async def abrufen(item: Arbeitselement) -> None:
        aufgerufen.append(item)

    async def dlq(item: Arbeitselement, exc: BaseException) -> None:
        raise AssertionError("DLQ darf hier nicht aufgerufen werden")

    worker = Worker(
        quelle_id=quelle_id,
        queue=queue,
        bucket=_SofortigerBucket(),
        abrufen=abrufen,
        dead_letter_sink=dlq,
        max_versuche=3,
        backoff_basis_sekunden=1.0,
        sleep=_FakeSleep(),
    )

    ergebnis = asyncio.run(worker.verarbeite_naechstes_element())

    assert ergebnis is False
    assert aufgerufen == []


def test_successful_processing_consumes_the_item_without_retry_or_dlq() -> None:
    """@trace dateneingang#AC11 — ein erfolgreich verarbeitetes
    Arbeitselement löst weder Retry noch Dead-Letter aus."""
    quelle_id = uuid.uuid4()
    queue = _FakeQueue(_item(quelle_id))
    verarbeitet: list[Arbeitselement] = []

    async def abrufen(item: Arbeitselement) -> None:
        verarbeitet.append(item)

    async def dlq(item: Arbeitselement, exc: BaseException) -> None:
        raise AssertionError("DLQ darf bei Erfolg nicht aufgerufen werden")

    worker = Worker(
        quelle_id=quelle_id,
        queue=queue,
        bucket=_SofortigerBucket(),
        abrufen=abrufen,
        dead_letter_sink=dlq,
        max_versuche=3,
        backoff_basis_sekunden=1.0,
        sleep=_FakeSleep(),
    )

    ergebnis = asyncio.run(worker.verarbeite_naechstes_element())

    assert ergebnis is True
    assert len(verarbeitet) == 1
    assert queue.enqueue_calls == []


def test_transient_error_reenqueues_with_incremented_versuch_after_backoff() -> None:
    """@trace dateneingang#AC10 — ein transienter Fehler (429/5xx/Timeout)
    führt zu einem erneuten Einreihen mit erhöhtem `versuch` NACH der
    Exponential-Backoff-Wartezeit — kein Dead-Letter, solange
    `max_versuche` nicht erschöpft ist."""
    quelle_id = uuid.uuid4()
    queue = _FakeQueue(_item(quelle_id, versuch=1))
    sleep = _FakeSleep()
    dlq_calls: list[Arbeitselement] = []

    async def abrufen(item: Arbeitselement) -> None:
        raise TimeoutError("Quelle antwortet nicht")

    async def dlq(item: Arbeitselement, exc: BaseException) -> None:
        dlq_calls.append(item)

    worker = Worker(
        quelle_id=quelle_id,
        queue=queue,
        bucket=_SofortigerBucket(),
        abrufen=abrufen,
        dead_letter_sink=dlq,
        max_versuche=5,
        backoff_basis_sekunden=2.0,
        sleep=sleep,
    )

    async def _run() -> None:
        await worker.verarbeite_naechstes_element()
        # Retry-Task laeuft im Hintergrund — dem Event-Loop Gelegenheit geben.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert dlq_calls == []
    assert sleep.calls == pytest.approx([2.0])  # basis * 2**(1-1)
    assert len(queue.enqueue_calls) == 1
    assert queue.enqueue_calls[0].versuch == 2


def test_transient_error_after_exhausted_attempts_goes_to_dead_letter_queue() -> None:
    """@trace dateneingang#AC10 — nach erschöpften Versuchen wandert das
    Arbeitselement in die Dead-Letter-Queue statt erneut eingereiht zu
    werden."""
    quelle_id = uuid.uuid4()
    queue = _FakeQueue(_item(quelle_id, versuch=3))
    dlq_calls: list[tuple[Arbeitselement, BaseException]] = []

    async def abrufen(item: Arbeitselement) -> None:
        raise TimeoutError("Quelle antwortet nicht")

    async def dlq(item: Arbeitselement, exc: BaseException) -> None:
        dlq_calls.append((item, exc))

    worker = Worker(
        quelle_id=quelle_id,
        queue=queue,
        bucket=_SofortigerBucket(),
        abrufen=abrufen,
        dead_letter_sink=dlq,
        max_versuche=3,
        backoff_basis_sekunden=1.0,
        sleep=_FakeSleep(),
    )

    asyncio.run(worker.verarbeite_naechstes_element())

    assert len(dlq_calls) == 1
    assert dlq_calls[0][0].versuch == 3
    assert queue.enqueue_calls == []  # kein weiterer Retry


def test_non_transient_error_is_neither_retried_nor_dead_lettered() -> None:
    """@trace dateneingang#AC10 — ein NICHT-transienter Fehler (z. B.
    Parsing-Fehler ohne HTTP-Status) wird protokolliert, aber löst weder
    Retry noch Dead-Letter aus — AC10 beschreibt Backoff/DLQ explizit nur
    für transiente Fehler."""
    quelle_id = uuid.uuid4()
    queue = _FakeQueue(_item(quelle_id))

    async def abrufen(item: Arbeitselement) -> None:
        raise ValueError("kaputtes JSON")

    dlq_calls: list[Arbeitselement] = []

    async def dlq(item: Arbeitselement, exc: BaseException) -> None:
        dlq_calls.append(item)

    worker = Worker(
        quelle_id=quelle_id,
        queue=queue,
        bucket=_SofortigerBucket(),
        abrufen=abrufen,
        dead_letter_sink=dlq,
        max_versuche=3,
        backoff_basis_sekunden=1.0,
        sleep=_FakeSleep(),
    )

    asyncio.run(worker.verarbeite_naechstes_element())

    assert dlq_calls == []
    assert queue.enqueue_calls == []


def test_backoff_wait_does_not_block_processing_of_the_next_item() -> None:
    """@trace dateneingang#AC10 — Edge-Case "ohne andere Quellen zu
    blockieren": die Backoff-Wartezeit eines fehlgeschlagenen
    Arbeitselements blockiert NICHT die Verarbeitung eines nachfolgenden
    Arbeitselements derselben Quelle (a fortiori einer anderen) — der
    Retry läuft in einem Hintergrund-Task."""
    quelle_id = uuid.uuid4()
    queue = _FakeQueue(_item(quelle_id, versuch=1))
    verarbeitete_ids: list[int] = []

    async def abrufen(item: Arbeitselement) -> None:
        if item.versuch == 1:
            raise TimeoutError("erster Versuch scheitert transient")
        verarbeitete_ids.append(item.versuch)

    async def dlq(item: Arbeitselement, exc: BaseException) -> None:
        raise AssertionError("DLQ wird hier nicht erwartet")

    # Sleep, der NIE zurueckkehrt (simuliert eine lange Backoff-Wartezeit) —
    # blockiert der Worker-Loop trotzdem NICHT, kann das zweite,
    # eigenstaendige Arbeitselement (bereits mit versuch=2 in der Queue)
    # dennoch sofort verarbeitet werden.
    async def _sleep_haengt_ewig(_seconds: float) -> None:
        await asyncio.Event().wait()

    worker = Worker(
        quelle_id=quelle_id,
        queue=queue,
        bucket=_SofortigerBucket(),
        abrufen=abrufen,
        dead_letter_sink=dlq,
        max_versuche=5,
        backoff_basis_sekunden=1.0,
        sleep=_sleep_haengt_ewig,
    )
    queue._elemente.append(_item(quelle_id, versuch=2))

    async def _run() -> None:
        # scheitert transient, Retry haengt im Hintergrund
        await worker.verarbeite_naechstes_element()
        # zweites Element, sofort dran
        ergebnis_zwei = await worker.verarbeite_naechstes_element()
        assert ergebnis_zwei is True

    asyncio.run(_run())

    assert verarbeitete_ids == [2]
