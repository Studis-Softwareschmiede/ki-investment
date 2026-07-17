"""Depot-Dashboard-Endpunkt (Modul 16 Depotmodul, `docs/specs/depot.md`
AC11, Story S-054; architecture.md §4 `app/api/dashboard.py` — "reine
Anzeige (Depot, Live-Kurse, Spinnennetz) — verändert nie Trading-Logik").

`GET /dashboard/depot` liest **ausschliesslich** über bestehende
Depotmodul-Bausteine:
- `app.domain.portfolio.ports.PositionRepository.alle_offenen_positionen`
  (S-036, AC8/AC9) für den offenen Bestand je Modus,
- `PositionRepository.historie_je_titel` (S-035, AC4/AC7) für die
  Kauf-Historie je Titel,
- `app.domain.portfolio.ports.LivePriceProvider` (Cross-Cutting
  Socket-Live-Kurs-Zugriff, P5) für aktuelle Kurse,
- `app.domain.portfolio.position_booking.berechne_unrealisierten_gv`/
  `aggregiere_gv` (AC2) für das laufende Plus/Minus.

Dieser Endpunkt bucht/entscheidet/schreibt NICHTS (keine der obigen
Abhängigkeiten hat einen Schreibpfad, den dieser Endpunkt aufruft) — reine
Anzeige-Schicht (AC11).

Mehrere offene Lots desselben Titels (FIFO, A2 aus `depot.md`) werden je
Titel aggregiert: `menge_gesamt` = Σ Lot-Mengen, `unrealisierter_gv_gesamt`
= `aggregiere_gv` über die je Lot berechneten unrealisierten G/V (AC2,
"aggregiert abrufbar") — derselbe aktuelle Kurs gilt für alle Lots eines
Titels."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.adapters.marketdata.live_price import NoOpLivePriceProvider
from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.contracts.dashboard import (
    DepotDashboardResponse,
    KaufHistorieEintrag,
    TitelDashboardEintrag,
)
from app.contracts.depot import Modus
from app.db.session import get_session
from app.domain.portfolio.ports import LivePriceProvider, PositionRepository, PositionsBestand
from app.domain.portfolio.position_booking import aggregiere_gv, berechne_unrealisierten_gv

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def get_position_repository(session: Session = Depends(get_session)) -> PositionRepository:
    """DI-Factory (fastapi/A02): reicht die Request-Session an den
    bestehenden `SqlAlchemyPositionRepository`-Adapter durch."""
    return SqlAlchemyPositionRepository(session)


def get_live_price_provider() -> LivePriceProvider:
    """DI-Factory (fastapi/A02): aktuell die einzige `LivePriceProvider`-
    Implementierung (`NoOpLivePriceProvider`, siehe `app.adapters.marketdata
    .live_price`-Moduldocstring)."""
    return NoOpLivePriceProvider()


def _gruppiere_nach_titel(
    positionen: Iterable[PositionsBestand],
) -> dict[str, list[PositionsBestand]]:
    """Gruppiert die (lot-weise) offenen Positionen nach `titel_id`,
    Reihenfolge-stabil (Repository liefert bereits nach `titel_id`
    sortiert)."""
    gruppiert: dict[str, list[PositionsBestand]] = {}
    for position in positionen:
        gruppiert.setdefault(position.titel_id, []).append(position)
    return gruppiert


def _baue_titel_eintrag(
    titel_id: str,
    lots: list[PositionsBestand],
    *,
    repository: PositionRepository,
    live_price: LivePriceProvider,
    mode: Modus,
) -> TitelDashboardEintrag:
    aktueller_preis: Decimal | None = live_price.aktueller_preis(titel_id)
    menge_gesamt = sum((lot.menge for lot in lots), Decimal("0"))

    unrealisierter_gv_gesamt: Decimal | None = None
    if aktueller_preis is not None:
        unrealisierter_gv_gesamt = aggregiere_gv(
            berechne_unrealisierten_gv(aktueller_preis, lot.einstand_preis, lot.menge)
            for lot in lots
        )

    kauf_historie = [
        KaufHistorieEintrag(
            trade_id=eintrag.trade_id,
            menge=eintrag.menge,
            fill_preis=eintrag.fill_preis,
            kosten=eintrag.kosten,
            zeitstempel=eintrag.zeitstempel,
        )
        for eintrag in repository.historie_je_titel(titel_id, mode=mode)
        if eintrag.richtung == "kauf"
    ]

    return TitelDashboardEintrag(
        titel_id=titel_id,
        menge_gesamt=menge_gesamt,
        aktueller_preis=aktueller_preis,
        unrealisierter_gv_gesamt=unrealisierter_gv_gesamt,
        kauf_historie=kauf_historie,
    )


@router.get("/depot", response_model=DepotDashboardResponse)
def depot_dashboard(
    mode: Modus = "echt",
    repository: PositionRepository = Depends(get_position_repository),
    live_price: LivePriceProvider = Depends(get_live_price_provider),
) -> DepotDashboardResponse:
    """AC11: Depot live (offener Bestand je Titel) + je Titel Kauf-Historie
    + laufendes Plus/Minus, mode-isoliert (BR-130, Default `echt`)."""
    positionen = repository.alle_offenen_positionen(mode=mode)
    titel = [
        _baue_titel_eintrag(titel_id, lots, repository=repository, live_price=live_price, mode=mode)
        for titel_id, lots in _gruppiere_nach_titel(positionen).items()
    ]
    return DepotDashboardResponse(mode=mode, titel=titel)
