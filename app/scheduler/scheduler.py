"""Scheduler — plant je aktiver Quelle periodische Abrufe gemäss ihrem
konfigurierten Abrufintervall (AC4) und reiht sie als Arbeitselement in
die Queue-of-Work der jeweiligen Quelle ein (AC11), sofern mindestens eine
zugeordnete Anlageklasse aktiv ist (AC9).

**AC4 (Abrufintervall konfigurierbar, provisorische Defaults):** das
Intervall selbst ist bereits `DataSource.frequenz_sekunden`
(`app.db.models`, S-006-Migration `ea80c97626ee` — Defaults 1:1 aus der
Spec: Polymarket/Whale/Nansen 30-60s, Reddit 15-30min, SEC 2h, FRED
täglich) — ohne Codeänderung überschreibbar (DB-Wert). Dieser Scheduler
liest den Wert je Tick und triggert entsprechend.

**AC9 (Toggle-Skip):** "Ist die einem Abruf zugeordnete Anlageklasse per
Toggle deaktiviert, findet weder Abruf noch Datenkosten statt; der
Scheduler überspringt die betroffenen Quellen für diese Klasse." Anders
als der Konsumenten-Kontrakt aus `docs/specs/anlageklassen-config.md`
(`app.domain.assetclasses.toggle_guard`, AC4/AC5 — der die
"Bestandspflege"-Ausnahme für offene Positionen kennt) prüft dieser
Scheduler NUR den reinen `AssetClass.aktiv`-Zustand: die
`dateneingang`-Spec grenzt das explizit ab ("Überwachung offener
Positionen ist Sache der nachgelagerten Module, nicht des Sockets" —
Edge-Cases-Abschnitt). Eine Quelle wird übersprungen, wenn KEINE ihrer
laut `DataSourceAssetClass` zugeordneten Anlageklassen aktiv ist; ist
mindestens eine aktiv, wird die Quelle (die ggf. mehrere Klassen
bedient) regulär eingereiht.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.scheduler import Arbeitselement
from app.db.models import AssetClass, DataSource, DataSourceAssetClass
from app.scheduler.queue import ArbeitsQueue

logger = logging.getLogger(__name__)


class Scheduler:
    """Hält je Quelle den Zeitpunkt des nächsten fälligen Abrufs
    (In-Process-Zustand — bei einem Neustart beginnt die Zählung neu, das
    erste `tick()` nach Prozessstart löst je Quelle sofort einen Abruf
    aus, analog `app.adapters.sockets.base.RateLimiter` "erster Aufruf
    wartet nie")."""

    def __init__(
        self,
        queue: ArbeitsQueue,
        *,
        jetzt: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._queue = queue
        self._jetzt = jetzt
        self._naechster_abruf: dict[uuid.UUID, datetime] = {}

    def _hat_aktive_anlageklasse(self, session: Session, *, data_source_id: uuid.UUID) -> bool:
        """AC9: True, sobald mindestens eine der laut
        `DataSourceAssetClass` zugeordneten Anlageklassen `aktiv` ist."""
        treffer = session.execute(
            select(AssetClass.id)
            .join(DataSourceAssetClass, DataSourceAssetClass.asset_class_id == AssetClass.id)
            .where(
                DataSourceAssetClass.data_source_id == data_source_id,
                AssetClass.aktiv.is_(True),
            )
            .limit(1)
        ).first()
        return treffer is not None

    async def tick(self, session: Session) -> list[Arbeitselement]:
        """Ein Scheduler-Tick: lädt alle aktiven Quellen (AC13-Kostentoggle
        — nur `DataSource.aktiv=True` wird überhaupt betrachtet), bestimmt
        die gemäss `frequenz_sekunden` fälligen (AC4) und reiht für jede
        fällige Quelle mit mindestens einer aktiven Anlageklasse (AC9) ein
        `Arbeitselement` in ihre Queue-of-Work ein (AC11). Liefert die
        tatsächlich eingereihten Arbeitselemente (Inspektion, z. B.
        Tests)."""
        jetzt = self._jetzt()
        eingereiht: list[Arbeitselement] = []
        quellen = (
            session.execute(select(DataSource).where(DataSource.aktiv.is_(True))).scalars().all()
        )

        for quelle in quellen:
            naechster = self._naechster_abruf.get(quelle.id)
            if naechster is not None and jetzt < naechster:
                continue
            self._naechster_abruf[quelle.id] = jetzt + timedelta(seconds=quelle.frequenz_sekunden)

            if not self._hat_aktive_anlageklasse(session, data_source_id=quelle.id):
                logger.debug(
                    "Quelle %s übersprungen — keine zugeordnete Anlageklasse aktiv (AC9).",
                    quelle.name,
                )
                continue

            item = Arbeitselement(data_source_id=quelle.id, eingereiht_am=jetzt)
            await self._queue.enqueue(item)
            eingereiht.append(item)

        return eingereiht

    async def run_forever(
        self,
        session_factory: Callable[[], Session],
        *,
        tick_interval_sekunden: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Produktions-Endlosschleife (bis `asyncio.CancelledError`, z. B.
        beim App-Shutdown): pollt alle `tick_interval_sekunden` (Default
        1s, deutlich unter dem kürzesten AC4-Intervall von 30s), damit
        keine Quelle ihr Intervall spürbar verpasst."""
        while True:
            with session_factory() as session:
                await self.tick(session)
            await sleep(tick_interval_sekunden)


__all__ = ["Scheduler"]
