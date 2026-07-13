"""Worker — arbeitet die Queue-of-Work EINER Quelle ab, gedrosselt durch
einen Token-Bucket (AC11), mit Exponential Backoff + Dead-Letter-Queue bei
transienten Fehlern (AC10, `docs/specs/dateneingang.md`).

**Bewusste Nicht-Ziele dieser Story (kein Gold-Plating):** was genau "ein
Arbeitselement verarbeiten" bedeutet (Adapter-Fetch aufrufen, Ergebnis
normalisieren, nach Bronze schreiben — AC1/AC2/`datenqualitaet`-Schicht)
ist NICHT Teil dieser Story (S-020 implementiert nur AC4/AC9/AC10/AC11).
`Worker` bekommt die konkrete Verarbeitung als injizierte `abrufen`-
Callable — eine künftige `app.orchestration.ingest_pipeline` (siehe
architecture.md §4-Verzeichnisstruktur) verdrahtet Adapter ↔ Worker,
dieses Modul kennt nur die Queue-/Retry-/DLQ-Mechanik.

**AC10 "ohne andere Quellen zu blockieren":** ein Retry blockiert NICHT
den Worker-Loop (der sonst hinter der Backoff-Wartezeit "hängen" würde,
bis er das nächste Arbeitselement DERSELBEN Quelle abarbeiten kann,
geschweige denn andere Quellen betreffen könnte, da jeder Worker ohnehin
nur eine Quelle bedient) — die Wartezeit läuft in einem eigenen
Hintergrund-Task, der Worker kehrt sofort zur Queue zurück.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.orm import Session

from app.contracts.scheduler import Arbeitselement
from app.db.ingest_dead_letter import record_dead_letter
from app.scheduler.errors import ist_transienter_fehler
from app.scheduler.queue import ArbeitsQueue
from app.scheduler.token_bucket import TokenBucket

logger = logging.getLogger(__name__)

#: Signatur des Dead-Letter-Sinks — nimmt das endgültig aufgegebene
#: Arbeitselement + den letzten Fehler entgegen (AC10 "protokolliert").
DeadLetterSink = Callable[[Arbeitselement, BaseException], Awaitable[None]]


def dead_letter_sink_via_db(session_factory: Callable[[], Session]) -> DeadLetterSink:
    """Produktions-`DeadLetterSink`: schreibt über `session_factory` eine
    `IngestDeadLetter`-Zeile (`app.db.ingest_dead_letter.record_dead_letter`,
    AC10 — durable Ablage). Der synchrone DB-Aufruf läuft über
    `asyncio.to_thread`, damit er den Event-Loop nicht blockiert
    (fastapi/A03)."""

    async def _sink(item: Arbeitselement, exc: BaseException) -> None:
        def _schreiben() -> None:
            with session_factory() as session:
                record_dead_letter(
                    session,
                    data_source_id=item.data_source_id,
                    fehler=str(exc),
                    retry_count=item.versuch,
                )

        await asyncio.to_thread(_schreiben)

    return _sink


class Worker:
    """Bedient die Queue-of-Work EINER Quelle (`quelle_id`) — je aktiver
    Quelle instanziiert die Aufrufer-Ebene (künftig
    `app.orchestration.ingest_pipeline`) einen eigenen `Worker` mit
    eigenem `TokenBucket` (AC11, strukturelle Entkopplung der
    Quellen-Frequenzen)."""

    def __init__(
        self,
        *,
        quelle_id: uuid.UUID,
        queue: ArbeitsQueue,
        bucket: TokenBucket,
        abrufen: Callable[[Arbeitselement], Awaitable[Any]],
        dead_letter_sink: DeadLetterSink,
        max_versuche: int,
        backoff_basis_sekunden: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        dequeue_timeout_sekunden: float = 1.0,
    ) -> None:
        if max_versuche < 1:
            raise ValueError("max_versuche muss mindestens 1 sein.")
        if backoff_basis_sekunden <= 0:
            raise ValueError("backoff_basis_sekunden muss positiv sein.")
        self._quelle_id = quelle_id
        self._queue = queue
        self._bucket = bucket
        self._abrufen = abrufen
        self._dead_letter_sink = dead_letter_sink
        self._max_versuche = max_versuche
        self._backoff_basis = backoff_basis_sekunden
        self._sleep = sleep
        self._dequeue_timeout = dequeue_timeout_sekunden
        # Referenzen auf laufende Retry-Hintergrund-Tasks — sonst würde der
        # Task ggf. vom GC eingesammelt, bevor er die Backoff-Wartezeit
        # abgeschlossen hat (siehe asyncio-Doku "Save a reference").
        self._laufende_retries: set[asyncio.Task[None]] = set()

    async def verarbeite_naechstes_element(self) -> bool:
        """Ein Verarbeitungsschritt: dequeued (falls vorhanden) das
        nächste Arbeitselement dieser Quelle, wartet auf ein Token (AC11)
        und verarbeitet es. `True`, wenn ein Element bearbeitet wurde
        (auch bei Fehlschlag), `False` wenn die Queue leer war (kein
        Element innerhalb `dequeue_timeout_sekunden`)."""
        item = await self._queue.dequeue(
            data_source_id=self._quelle_id, timeout_sekunden=self._dequeue_timeout
        )
        if item is None:
            return False

        await self._bucket.acquire()
        try:
            await self._abrufen(item)
        except Exception as exc:  # noqa: BLE001 — bewusst breit: jede Adapter-Exception wird klassifiziert (AC10)
            await self._behandle_fehler(item, exc)
        return True

    async def _behandle_fehler(self, item: Arbeitselement, exc: Exception) -> None:
        if not ist_transienter_fehler(exc):
            logger.error(
                "Arbeitselement für Quelle %s permanent fehlgeschlagen (kein Retry, "
                "kein AC10-Backoff — nicht transient): %s",
                item.data_source_id,
                exc,
            )
            return

        if item.versuch >= self._max_versuche:
            logger.error(
                "Arbeitselement für Quelle %s nach %d Versuchen aufgegeben — "
                "Dead-Letter-Queue (AC10): %s",
                item.data_source_id,
                item.versuch,
                exc,
            )
            await self._dead_letter_sink(item, exc)
            return

        wartezeit = self._backoff_basis * (2 ** (item.versuch - 1))
        logger.warning(
            "Transienter Fehler bei Quelle %s (Versuch %d/%d) — Retry in %.1fs (AC10): %s",
            item.data_source_id,
            item.versuch,
            self._max_versuche,
            wartezeit,
            exc,
        )
        naechstes_element = item.naechster_versuch()
        # Nicht-blockierend (E1/AC10 "ohne andere Quellen zu blockieren"):
        # die Backoff-Wartezeit läuft in einem eigenen Task, der Aufrufer
        # (Worker-Loop) kehrt sofort zur Queue zurück.
        task = asyncio.ensure_future(self._retry_spaeter(naechstes_element, wartezeit))
        self._laufende_retries.add(task)
        task.add_done_callback(self._laufende_retries.discard)

    async def _retry_spaeter(self, item: Arbeitselement, wartezeit: float) -> None:
        await self._sleep(wartezeit)
        await self._queue.enqueue(item)

    async def run_forever(self) -> None:
        """Produktions-Endlosschleife (bis `asyncio.CancelledError`, z. B.
        beim App-Shutdown)."""
        while True:
            await self.verarbeite_naechstes_element()


__all__ = ["Worker", "DeadLetterSink", "dead_letter_sink_via_db"]
