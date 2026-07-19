"""Konfigurations-Read-Endpunkte (Story S-069, `docs/specs/frontend-cockpit.md`
AC9/AC10; architecture.md §13.7 Prüfkriterium 4).

`GET /api/config/anlageklassen` + `GET /api/config/depotstrategie` sind reine
Anzeige-Endpunkte (AC9, C-006/C-015) — die schreibende Gegenseite (Klassen-
Toggle setzen, Depotstrategie-Preset wählen/feinjustieren) läuft
ausschliesslich über die getrennte Control-Plane `app/api/control.py`
(S-074, AC20), NICHT hier (diese Story ist rein lesend, siehe Task-Kontext).

Jede Route trägt `response_model` (AC10, P2) und konsumiert dieselbe
Query-Funktion (`app.api.queries.config`), die die künftige HTML-View
(S-076) wiederverwenden wird — kein zweiter Datenzusammenbau.

Die eigentliche DB-Session bleibt bewusst auf diese Router-Datei beschränkt
(DI-Factories unten) — `app/api/queries/config.py` nimmt laut Paket-
Konvention keine eigene Session entgegen, sondern einen bereits an die
Session gebundenen Lese-Callable (siehe dortiger Moduldocstring)."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.queries.config import (
    lade_anlageklassen_konfiguration,
    lade_depotstrategie_konfiguration,
)
from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.contracts.risikomanagement import DepotstrategieKonfiguration
from app.db.asset_classes import lade_alle_anlageklassen
from app.db.depotstrategie import lade_aktive_depotstrategie
from app.db.session import get_session

router = APIRouter(prefix="/api/config", tags=["config"])


def get_anlageklassen_reader(
    session: Session = Depends(get_session),
) -> Callable[[], list[AnlageklasseEintrag]]:
    """DI-Factory (fastapi/A02): bindet `lade_alle_anlageklassen` an die
    Request-Session, ohne dass die Query-Funktion selbst eine Session
    kennen muss."""
    return partial(lade_alle_anlageklassen, session)


def get_depotstrategie_reader(
    session: Session = Depends(get_session),
) -> Callable[[], DepotstrategieKonfiguration | None]:
    """DI-Factory (fastapi/A02): bindet `lade_aktive_depotstrategie` an die
    Request-Session."""
    return partial(lade_aktive_depotstrategie, session)


@router.get("/anlageklassen", response_model=list[AnlageklasseEintrag])
def anlageklassen_konfiguration(
    reader: Callable[[], list[AnlageklasseEintrag]] = Depends(get_anlageklassen_reader),
) -> list[AnlageklasseEintrag]:
    """AC9: die 11 Anlageklassen mit Toggle-Zustand + Prio (→ C-006)."""
    return lade_anlageklassen_konfiguration(reader)


@router.get("/depotstrategie", response_model=DepotstrategieKonfiguration | None)
def depotstrategie_konfiguration(
    reader: Callable[[], DepotstrategieKonfiguration | None] = Depends(get_depotstrategie_reader),
) -> DepotstrategieKonfiguration | None:
    """AC9: die aktiven Depotstrategie-Grenzwerte/das Preset (→ C-015);
    `None`, solange (noch) kein Preset aktiviert wurde."""
    return lade_depotstrategie_konfiguration(reader)
