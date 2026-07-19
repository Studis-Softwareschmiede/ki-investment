"""Repository-Port für das Warteliste-Read-Modell (architecture.md §4:
"abstrakte Protokolle in `app/domain/**/ports.py`", P1; Story S-079,
`docs/specs/frontend-cockpit.md` AC26).

Eigener, von `app.domain.risikomanagement` bewusst getrennter
Domänen-Namensraum: die UI-/Query-Boundary (`tests/architecture
/test_ui_boundary.py`, AC2) verbietet `app/api/ui.py` +
`app/api/queries/**` jeden Import aus `app.domain.risikomanagement`
(Gate-Logik) — dieser Port liefert AUSSCHLIESSLICH das bereits
persistierte Warteliste-Read-Modell (`app.db.models.WartelisteEintrag`),
nie einen Gate-Direktaufruf (AC26 wörtlich: "Daten ausschliesslich aus dem
Read-Modell/Repository, nie per Gate-Direktaufruf")."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

Modus = Literal["echt", "simuliert"]
BlockadeGrund = Literal["klumpenrisiko", "korrelation", "drawdown", "kelly_cap"]


@dataclass(frozen=True)
class WartelisteEintrag:
    """Ein Eintrag der Warteliste (AC26): Titel, Anlageklasse, geplante
    Grösse, Blockade-Grund (welche Prüfmatrix-Dimension) und Zeitpunkt."""

    id: str
    titel_id: str
    titel: str
    name: str
    asset_class_id: int
    geplante_groesse: Decimal
    blockade_grund: BlockadeGrund
    blockiert_am: datetime


class WartelisteRepository(Protocol):
    def liste_warteliste(self, *, mode: Modus) -> list[WartelisteEintrag]:
        """AC26: alle Warteliste-Einträge des angegebenen Modus (→
        BR-130), neueste zuerst."""
        ...
