"""Query-Funktion Trade-Historie-View (`docs/specs/frontend-cockpit.md`
AC6/AC7, Story S-067; siehe `app/api/queries/__init__.py`-Konvention).

**AC7 — Read-Modell-Gap geschlossen:** die depotweite Trade-Historie lag
bislang nur je Titel abfragbar vor (`PositionRepository.historie_je_titel`,
S-035); diese Query-Funktion ist der einzige Ort, an dem der depotweite
Zugriff (`PositionRepository.historie_depotweit`, S-067) auf ein
HTTP-abfragbares Read-Modell (`app.contracts.trades.TradesResponse`)
abgebildet wird — rein lesend, kein neues Order-Pfad-Verhalten.

Wird künftig (S-073) sowohl von der JSON-Route (`app.api.trades`) als auch
von der HTML-Route (`app.api.ui.trades_view`) konsumiert (AC1/AC10, P4/DRY)."""

from __future__ import annotations

from datetime import datetime

from app.contracts.depot import Modus
from app.contracts.trades import TradeHistorieEintrag, TradesResponse
from app.domain.portfolio.ports import PositionRepository


def hole_trade_historie(
    repository: PositionRepository,
    *,
    mode: Modus = "echt",
    titel_id: str | None = None,
    von: datetime | None = None,
    bis: datetime | None = None,
) -> TradesResponse:
    """AC6: liefert die depotweite Fill-/Transaktionshistorie im
    angegebenen `mode` (BR-130), optional gefiltert auf `titel_id` und/oder
    den Zeitraum `[von, bis]` (je `None` = kein Filter) — liest
    ausschliesslich über `PositionRepository.historie_depotweit`
    (AC7-Gap-Schluss, S-067), baut keine eigene DB-Abfrage."""
    eintraege = repository.historie_depotweit(mode=mode, titel_id=titel_id, von=von, bis=bis)
    trades = [
        TradeHistorieEintrag(
            trade_id=eintrag.trade_id,
            titel_id=eintrag.titel_id,
            richtung=eintrag.richtung,
            menge=eintrag.menge,
            fill_preis=eintrag.fill_preis,
            arrival_price=eintrag.arrival_price,
            slippage=eintrag.slippage,
            kosten=eintrag.kosten,
            waehrung=eintrag.waehrung,
            zeitstempel=eintrag.zeitstempel,
            fx_rate=eintrag.fx_rate,
            kapital_gv_chf=eintrag.kapital_gv_chf,
            waehrungs_gv_chf=eintrag.waehrungs_gv_chf,
            titel=eintrag.titel,
            name=eintrag.name,
        )
        for eintrag in eintraege
    ]
    return TradesResponse(mode=mode, trades=trades)
