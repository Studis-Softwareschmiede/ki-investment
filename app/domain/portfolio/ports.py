"""Repository-Port für das Depotmodul (Modul 16, architecture.md §4:
"abstrakte Protokolle in `app/domain/**/ports.py`", P1).

Der reine Domain-Kern (`app.domain.portfolio.fill_booking`) darf laut P1
kein SQLAlchemy/DB importieren — er greift auf den Bestand ausschliesslich
über dieses `Protocol` zu; die konkrete Implementierung liegt im Adapter
`app.adapters.repositories.position_repository.SqlAlchemyPositionRepository`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol


class PositionRepository(Protocol):
    """Lese-Zugriff auf den aktuellen Bestand.

    Für S-015 (AC10, "resultierende negative Menge") genügt die aktuell
    gehaltene Menge je Titel. Schreib-/Fortschreibungs-Methoden (Positions-
    Erstellung, Ø-Einstand-Update, Gebühren-Netting, ...) sind NICHT Teil
    dieses Ports — die eigentliche Buchungsmechanik ist S-016.
    """

    def aktuelle_menge(self, titel_id: str) -> Decimal:
        """Liefert die Summe der `menge` aller offenen Positionen für
        `titel_id` (`Decimal("0")`, falls keine offene Position
        existiert)."""
        ...
