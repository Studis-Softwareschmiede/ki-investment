"""SQLAlchemy-Implementierung des `ExecutionRepository`-Ports (architecture.md
§4 `app/adapters/repositories/`, Story S-048, Spec
`docs/specs/ausfuehrung-paper.md` AC7/AC8).

Implementiert `app.domain.execution.ports.ExecutionRepository` strukturell
(Protocol, keine explizite Vererbung nötig) gegen die `order`/`trade_fill`-
Tabellen (`app.db.models.Order`/`TradeFill`, `docs/data-model.md` §4,
C-016) — die Order-Ausführungs-eigene TCA, getrennt von der Depot-
`transaction`-Historie (C-017, `app.adapters.repositories
.position_repository`).

`speichere_ausfuehrung` legt IMMER eine `order`-Zeile mit dem in
`ergebnis.status` ermittelten Endzustand an; nur bei `status ∈ {"filled",
"partial"}` zusätzlich eine `trade_fill`-Zeile (BR-139: kein Fill-Eintrag
bei `"rejected"`/`"timeout"` — kein Bestand wird ohne bestätigten Fill
verändert). `position_id` bleibt in dieser Story immer `NULL` (die
Positions-Zuordnung geschieht erst nach der — hier NICHT verdrahteten —
Fill→Depot-Meldung, siehe `app.contracts.ausfuehrung_paper`-Moduldocstring).
`mode` ist im MVP strukturell immer `"simuliert"` (AC3/BR-019, `"echt"` ist
hart gesperrt, siehe `app.domain.execution.order_ausfuehrung
.bestimme_wirksamen_modus`) — als expliziter Parameter statt hartkodiert,
damit ein künftiger Live-Adapter diesen Aufruf unverändert wiederverwenden
kann."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contracts.ausfuehrung_paper import Ausfuehrungsergebnis, OrderAnfrage
from app.contracts.depot import Modus
from app.db.models import Order, TradeFill

#: AC7/AC8: `Ausfuehrungsergebnis.status` -> `order.status` (data-model.md
#: §4, `ORDER_STATUS_VALUES`) — `"partial"` heisst auf DB-Ebene `"teilfill"`
#: (deutsches Vokabular in `order.status`, siehe Präzisierungsnote).
_ORDER_STATUS_MAP: dict[str, str] = {
    "filled": "filled",
    "partial": "teilfill",
    "rejected": "rejected",
    "timeout": "timeout",
}

#: AC1 (S-046)/AC7 (S-048): `OrderAnfrage.richtung` ("kauf"/"verkauf") ->
#: `order.richtung` (data-model.md §4, `ORDER_RICHTUNG_VALUES`).
_RICHTUNG_MAP: dict[str, str] = {"kauf": "buy", "verkauf": "sell"}

#: Fill-Stati, für die BR-139 einen `trade_fill`-Eintrag erlaubt (ein
#: bestätigter Fill liegt vor).
_FILL_STATI: tuple[str, ...] = ("filled", "partial")


class SqlAlchemyExecutionRepository:
    """Liest/schreibt die Order-Lifecycle-Zustände über eine injizierte
    SQLAlchemy-`Session` (Ports & Adapters, P1 — kein eigenes
    Connection-/Engine-Management hier)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def speichere_ausfuehrung(
        self,
        anfrage: OrderAnfrage,
        ergebnis: Ausfuehrungsergebnis,
        *,
        instrument_id: uuid.UUID,
        platform_id: uuid.UUID | None = None,
        mode: Modus = "simuliert",
    ) -> None:
        """AC7/AC8: legt eine `order`-Zeile an (immer) sowie — nur bei
        `ergebnis.status ∈ {"filled", "partial"}` — eine `trade_fill`-Zeile
        (BR-139)."""
        order = Order(
            id=uuid.uuid4(),
            position_id=None,
            instrument_id=instrument_id,
            platform_id=platform_id,
            richtung=_RICHTUNG_MAP[anfrage.richtung],
            order_typ=anfrage.order_typ,
            menge=anfrage.groesse,
            limit_preis=anfrage.preis,
            arrival_price=ergebnis.arrival_price,
            exit_urgency=None,
            tranche_index=None,
            tranche_total=None,
            status=_ORDER_STATUS_MAP[ergebnis.status],
            mode=mode,
        )
        self._session.add(order)

        if ergebnis.status in _FILL_STATI:
            self._session.add(_trade_fill_aus_ergebnis(order.id, ergebnis))

        self._session.flush()


def _trade_fill_aus_ergebnis(order_id: uuid.UUID, ergebnis: Ausfuehrungsergebnis) -> TradeFill:
    """AC7 (S-048): baut die `trade_fill`-Zeile aus einem bereits als Fill
    erkannten `Ausfuehrungsergebnis` (`fill_preis`/`slippage` sind laut
    `verarbeite_fill` bei `status ∈ {"filled", "partial"}` immer gesetzt).
    `courtage_chf` übernimmt `tatsaechliche_kosten` unaufgeteilt
    (`spread_kosten_chf` bleibt beim Schema-Default `0`, siehe
    `app.db.models.TradeFill`-Docstring — Courtage-/Spread-Aufschlüsselung
    setzt das AC9-Slippage-/Spread-Modell voraus, S-049, Nicht-Ziel dieser
    Story).

    Raises:
        ValueError: `ergebnis.fill_preis`/`ergebnis.slippage` ist `None` —
            das verletzt die Vertrags-Invariante von `app.domain.execution
            .order_ausfuehrung.verarbeite_fill` (beide sind bei
            `status ∈ {"filled", "partial"}` immer gesetzt); ein Aufrufer
            hätte diese Funktion mit einem inkonsistenten `Ausfuehrungsergebnis`
            aufgerufen."""
    if ergebnis.fill_preis is None or ergebnis.slippage is None:
        raise ValueError(
            f"Ausfuehrungsergebnis mit status={ergebnis.status!r} ohne fill_preis/slippage "
            "ist inkonsistent (ein bestätigter Fill trägt immer beide)."
        )
    return TradeFill(
        id=uuid.uuid4(),
        order_id=order_id,
        fill_preis=ergebnis.fill_preis,
        fill_menge=ergebnis.ausgefuehrte_menge,
        courtage_chf=ergebnis.tatsaechliche_kosten,
        spread_kosten_chf=Decimal("0"),
        slippage_abs=ergebnis.slippage,
        executed_at=datetime.now(UTC),
    )


__all__ = ["SqlAlchemyExecutionRepository"]
