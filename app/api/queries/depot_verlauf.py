"""Query-Funktion Depot-Verlauf-View (`docs/specs/frontend-cockpit.md`
AC32/AC33, Story S-081; siehe `app/api/queries/__init__.py`-Konvention).

Read-only Query-Funktion für den Depot-Verlauf-Chart: liest ausschliesslich
über `app.domain.portfolio_verlauf.ports.PortfolioSnapshotRepository`
(kein `sqlalchemy`-Import, kein `session.add`/`commit`,
`tests/architecture/test_ui_boundary.py` erzwingt das statisch) — dieselbe
Funktion speist sowohl die JSON-Route (`app.api.depot_verlauf`) als auch
die HTML-Route (`app.api.ui.depot_view`, AC1/AC10, P4/DRY)."""

from __future__ import annotations

from datetime import datetime

from app.contracts.depot import Modus
from app.contracts.depot_verlauf import DepotVerlaufEintrag, DepotVerlaufResponse
from app.domain.portfolio_verlauf.ports import PortfolioSnapshotRepository


def hole_depot_verlauf(
    repository: PortfolioSnapshotRepository,
    *,
    mode: Modus = "echt",
    von: datetime | None = None,
    bis: datetime | None = None,
) -> DepotVerlaufResponse:
    """AC32: liefert die Portfolio-Wert-Zeitreihe im angegebenen `mode`
    (→ BR-130), optional gefiltert auf den Zeitraum `[von, bis]` (je `None`
    = kein Filter)."""
    eintraege = [
        DepotVerlaufEintrag(
            zeitpunkt=eintrag.zeitpunkt,
            portfolio_wert=eintrag.portfolio_wert,
            cash_quote=eintrag.cash_quote,
        )
        for eintrag in repository.verlauf(mode=mode, von=von, bis=bis)
    ]
    return DepotVerlaufResponse(mode=mode, eintraege=eintraege)
