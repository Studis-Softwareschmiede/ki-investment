"""Tests für `Scheduler.tick` (Story S-020).

Covers (dateneingang): AC4, AC9

- **AC4** (Abrufintervall je Quelle konfigurierbar): `Scheduler.tick`
  reiht eine Quelle nur ein, sobald `DataSource.frequenz_sekunden`
  verstrichen ist — die DB-Spalte ist ohne Codeänderung überschreibbar
  (S-006), dieser Test belegt, dass der Scheduler sie tatsächlich als
  Trigger-Intervall verwendet.
- **AC9** (Toggle-Skip): eine Quelle, deren zugeordnete Anlageklasse(n)
  ausnahmslos inaktiv sind, wird übersprungen — kein Arbeitselement, kein
  externer Aufruf, keine Datenkosten. Ist mindestens eine zugeordnete
  Klasse aktiv, wird die Quelle regulär eingereiht.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.scheduler import Arbeitselement
from app.db.base import Base
from app.db.models import AssetClass, DataSource, DataSourceAssetClass
from app.scheduler.queue import ArbeitsQueue
from app.scheduler.scheduler import Scheduler


class _FakeQueue(ArbeitsQueue):
    def __init__(self) -> None:
        self.eingereiht: list[Arbeitselement] = []

    async def enqueue(self, item: Arbeitselement) -> None:
        self.eingereiht.append(item)

    async def dequeue(  # pragma: no cover — hier ungenutzt
        self, *, data_source_id, timeout_sekunden
    ):
        raise NotImplementedError


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _quelle(session: Session, *, frequenz_sekunden: int, asset_class_ids: list[int]) -> DataSource:
    quelle = DataSource(
        id=uuid.uuid4(),
        name=f"Testquelle-{uuid.uuid4().hex[:6]}",
        kategorie="makro_anleihen",
        frequenz_sekunden=frequenz_sekunden,
        aktiv=True,
    )
    session.add(quelle)
    session.flush()
    for asset_class_id in asset_class_ids:
        session.add(DataSourceAssetClass(data_source_id=quelle.id, asset_class_id=asset_class_id))
    session.commit()
    return quelle


def _asset_class(session: Session, *, id_: int, aktiv: bool) -> None:
    session.add(AssetClass(id=id_, name=f"Klasse-{id_}", prio_stufe="MVP", aktiv=aktiv))
    session.commit()


def test_first_tick_enqueues_a_due_source_immediately() -> None:
    """@trace dateneingang#AC4 — vor dem ersten Tick gibt es keinen
    Vorgänger-Abruf, die Quelle ist sofort fällig (analog RateLimiter
    "erster Aufruf wartet nie")."""
    session = _session()
    _asset_class(session, id_=1, aktiv=True)
    quelle = _quelle(session, frequenz_sekunden=60, asset_class_ids=[1])
    jetzt = datetime(2026, 1, 1, tzinfo=UTC)
    queue = _FakeQueue()
    scheduler = Scheduler(queue, jetzt=lambda: jetzt)

    eingereiht = asyncio.run(scheduler.tick(session))

    assert len(eingereiht) == 1
    assert eingereiht[0].data_source_id == quelle.id
    assert queue.eingereiht == eingereiht


def test_tick_before_interval_elapsed_does_not_reenqueue() -> None:
    """@trace dateneingang#AC4 — innerhalb von `frequenz_sekunden` seit
    dem letzten Abruf wird die Quelle nicht erneut eingereiht."""
    session = _session()
    _asset_class(session, id_=1, aktiv=True)
    _quelle(session, frequenz_sekunden=60, asset_class_ids=[1])
    jetzt = [datetime(2026, 1, 1, tzinfo=UTC)]
    queue = _FakeQueue()
    scheduler = Scheduler(queue, jetzt=lambda: jetzt[0])

    asyncio.run(scheduler.tick(session))  # erster Tick: fällig
    jetzt[0] = jetzt[0].replace(second=30)  # 30s später, Intervall ist 60s
    eingereiht_zweiter_tick = asyncio.run(scheduler.tick(session))

    assert eingereiht_zweiter_tick == []
    assert len(queue.eingereiht) == 1


def test_tick_after_interval_elapsed_reenqueues() -> None:
    """@trace dateneingang#AC4 — nach Ablauf von `frequenz_sekunden` wird
    die Quelle beim nächsten Tick erneut eingereiht (der DB-Wert steuert
    das Intervall, ohne Codeänderung überschreibbar)."""
    session = _session()
    _asset_class(session, id_=1, aktiv=True)
    _quelle(session, frequenz_sekunden=45, asset_class_ids=[1])
    from datetime import timedelta

    jetzt = [datetime(2026, 1, 1, tzinfo=UTC)]
    queue = _FakeQueue()
    scheduler = Scheduler(queue, jetzt=lambda: jetzt[0])

    asyncio.run(scheduler.tick(session))
    jetzt[0] = jetzt[0] + timedelta(seconds=45)
    eingereiht_zweiter_tick = asyncio.run(scheduler.tick(session))

    assert len(eingereiht_zweiter_tick) == 1
    assert len(queue.eingereiht) == 2


def test_source_with_only_inactive_asset_classes_is_skipped() -> None:
    """@trace dateneingang#AC9 — ist die (einzige) zugeordnete
    Anlageklasse per Toggle inaktiv, entsteht kein Arbeitselement (kein
    Abruf, keine Datenkosten)."""
    session = _session()
    _asset_class(session, id_=4, aktiv=False)
    _quelle(session, frequenz_sekunden=60, asset_class_ids=[4])
    queue = _FakeQueue()
    scheduler = Scheduler(queue, jetzt=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    eingereiht = asyncio.run(scheduler.tick(session))

    assert eingereiht == []
    assert queue.eingereiht == []


def test_source_with_at_least_one_active_asset_class_is_enqueued() -> None:
    """@trace dateneingang#AC9 — bedient eine Quelle mehrere Klassen und
    ist mindestens eine davon aktiv, wird die Quelle regulär eingereiht
    (der Scheduler kennt keine Fetch-Granularität unterhalb der Quelle)."""
    session = _session()
    _asset_class(session, id_=3, aktiv=False)
    _asset_class(session, id_=4, aktiv=True)
    _asset_class(session, id_=10, aktiv=False)
    _quelle(session, frequenz_sekunden=60, asset_class_ids=[3, 4, 10])
    queue = _FakeQueue()
    scheduler = Scheduler(queue, jetzt=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    eingereiht = asyncio.run(scheduler.tick(session))

    assert len(eingereiht) == 1


def test_run_forever_ticks_repeatedly_until_cancelled() -> None:
    """@trace dateneingang#AC4 — `run_forever` pollt wiederholt via die
    injizierte `sleep`-Funktion (kein echtes Warten im Test)."""
    session = _session()
    _asset_class(session, id_=1, aktiv=True)
    _quelle(session, frequenz_sekunden=60, asset_class_ids=[1])
    queue = _FakeQueue()
    scheduler = Scheduler(queue, jetzt=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    tick_count = 0

    async def _fake_sleep(_seconds: float) -> None:
        nonlocal tick_count
        tick_count += 1
        if tick_count >= 3:
            raise asyncio.CancelledError

    async def _run() -> None:
        try:
            await scheduler.run_forever(lambda: session, sleep=_fake_sleep)
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())

    assert tick_count == 3
    assert len(queue.eingereiht) == 1  # nur der allererste Tick war faellig
