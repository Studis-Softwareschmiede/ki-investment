"""Query-Funktion Warteliste-View (`docs/specs/frontend-cockpit.md` AC26,
Story S-079; siehe `app/api/queries/__init__.py`-Konvention).

Liest ausschliesslich über `app.domain.warteliste.ports
.WartelisteRepository` (kein `sqlalchemy`-Import, kein
`session.add`/`commit`, `tests/architecture/test_ui_boundary.py` erzwingt
das statisch) — dieselbe Funktion speist sowohl die JSON-Route
(`app.api.warteliste`) als auch die HTML-View
(`app.api.ui.warteliste_view`, AC1/AC10, P4/DRY)."""

from __future__ import annotations

from app.contracts.depot import Modus
from app.contracts.warteliste import WartelisteEintragResponse, WartelisteResponse
from app.domain.warteliste.ports import WartelisteRepository


def hole_warteliste(
    repository: WartelisteRepository, *, mode: Modus = "echt"
) -> WartelisteResponse:
    """AC26: liefert die Warteliste blockierter Kauf-Kandidaten im
    angegebenen `mode` (→ BR-130)."""
    eintraege = [
        WartelisteEintragResponse(
            id=eintrag.id,
            titel_id=eintrag.titel_id,
            titel=eintrag.titel,
            name=eintrag.name,
            asset_class_id=eintrag.asset_class_id,
            geplante_groesse=eintrag.geplante_groesse,
            blockade_grund=eintrag.blockade_grund,
            blockiert_am=eintrag.blockiert_am,
        )
        for eintrag in repository.liste_warteliste(mode=mode)
    ]
    return WartelisteResponse(mode=mode, eintraege=eintraege)
