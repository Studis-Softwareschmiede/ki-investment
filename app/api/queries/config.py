"""Query-Funktionen Konfigurations-View (Story S-069, `docs/specs/
frontend-cockpit.md` AC9/AC10).

Covers (frontend-cockpit): AC9, AC10

Je EINE read-only Query-Funktion für die zwei Konfigurations-Read-Routen
(AC9: `GET /api/config/anlageklassen`, `GET /api/config/depotstrategie`) —
von der JSON-Route (`app.api.config`) konsumiert und für die künftige
HTML-View (S-076, ausserhalb dieser Story) wiederverwendbar (AC10: "kein
zweiter Datenzusammenbau").

Nimmt gemäss Paket-Konvention (`app/api/queries/__init__.py`: "nie eine
eigene DB-Session ... — Repository-Lese-Ports") keine eigene DB-Session
entgegen, sondern einen bereits an eine Session gebundenen, zero-arg
Lese-Callable (DI-Factory in `app.api.config`, analog `PositionRepository`/
`LivePriceProvider` in `app.api.dashboard`) — kein `sqlalchemy`-Import,
keine eigene Query in dieser Datei (AC2 Boundary, `tests/architecture/
test_ui_boundary.py`)."""

from __future__ import annotations

from collections.abc import Callable

from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.contracts.risikomanagement import DepotstrategieKonfiguration


def lade_anlageklassen_konfiguration(
    anlageklassen_lesen: Callable[[], list[AnlageklasseEintrag]],
) -> list[AnlageklasseEintrag]:
    """AC9: die 11 Anlageklassen mit Toggle-Zustand + Prio — der
    Lese-Callable liest bereits über den bestehenden Lesepfad
    `app.db.asset_classes.lade_alle_anlageklassen`."""
    return anlageklassen_lesen()


def lade_depotstrategie_konfiguration(
    depotstrategie_lesen: Callable[[], DepotstrategieKonfiguration | None],
) -> DepotstrategieKonfiguration | None:
    """AC9: die aktiven Depotstrategie-Grenzwerte/das Preset — `None`,
    solange (noch) kein Preset aktiviert wurde (siehe `app.db.depotstrategie
    .lade_aktive_depotstrategie`-Docstring: Zustand vor der ersten
    Preset-Wahl, AC3 `docs/specs/risikomanagement.md`)."""
    return depotstrategie_lesen()


__all__ = ["lade_anlageklassen_konfiguration", "lade_depotstrategie_konfiguration"]
