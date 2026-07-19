"""Demo-Warteliste (Story S-079, `docs/specs/frontend-cockpit.md` AC28).

`app.db.models.WartelisteEintrag` hat laut eigenem Docstring KEINEN
Backend-Schreib-/Re-Prüf-Pfad (Spec-Nicht-Ziel: "Keine Warteliste-Schreib-
/Re-Prüf-Mechanik ... Im MVP speist ausschliesslich der Demo-Seed das
Read-Modell") — diese Datei füllt daher direkt per ORM (klar markierter
Fixture-Insert, AC28 "deterministische, order-freie Beispiel-Einträge"):
reine Warteliste-Read-Modell-Zeilen, kein Order-/Sizing-/Risiko-/
Execution-Aufruf (§13.7-6).

Referenziert ausschliesslich bereits von `app.demo.instrumente` geseedete
Titel (`instrument_id`, kein neuer Instrument-Seed nötig) — muss daher
NACH `seed_instrumente` laufen (siehe `app.demo.seed.seed_demo_data`-
Reihenfolge).

Idempotent: `id` ist deterministisch aus einem Demo-Slug abgeleitet
(`app.demo._namespace.demo_id`) — ein wiederholter Aufruf überspringt
einen bereits vorhandenen Eintrag vollständig."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import WartelisteEintrag
from app.demo._namespace import demo_id
from app.demo.instrumente import instrument_id


@dataclass(frozen=True)
class _DemoWartelisteEintrag:
    slug: str
    titel_slug: str
    asset_class_id: int
    geplante_groesse: Decimal
    blockade_grund: str
    blockiert_am: datetime


#: Zwei blockierte Kauf-Kandidaten über zwei unterschiedliche
#: Prüfmatrix-Dimensionen (AC28 "deterministische, order-freie
#: Beispiel-Einträge") — beide referenzieren bereits im
#: `app.demo.instrumente`-Katalog vorhandene Titel, kein neuer
#: Instrument-Seed nötig.
_DEMO_WARTELISTE: tuple[_DemoWartelisteEintrag, ...] = (
    _DemoWartelisteEintrag(
        slug="demo-warteliste-chspi",
        titel_slug="demo-instrument-chspi",
        asset_class_id=2,
        geplante_groesse=Decimal("5000.00"),
        blockade_grund="klumpenrisiko",
        blockiert_am=datetime(2026, 6, 10, 8, 30, tzinfo=UTC),
    ),
    _DemoWartelisteEintrag(
        slug="demo-warteliste-rog",
        titel_slug="demo-instrument-rog",
        asset_class_id=1,
        geplante_groesse=Decimal("3200.00"),
        blockade_grund="korrelation",
        blockiert_am=datetime(2026, 6, 12, 14, 15, tzinfo=UTC),
    ),
)


def seed_warteliste(session: Session) -> None:
    """AC28: füllt `warteliste_eintrag` idempotent, ausschliesslich
    `mode="simuliert"` (AC22-Kern-Invariante)."""
    for eintrag in _DEMO_WARTELISTE:
        eintrag_id = demo_id(eintrag.slug)
        if session.get(WartelisteEintrag, eintrag_id) is not None:
            continue
        session.add(
            WartelisteEintrag(
                id=eintrag_id,
                instrument_id=instrument_id(eintrag.titel_slug),
                asset_class_id=eintrag.asset_class_id,
                geplante_groesse=eintrag.geplante_groesse,
                blockade_grund=eintrag.blockade_grund,
                mode="simuliert",
                blockiert_am=eintrag.blockiert_am,
            )
        )
        session.commit()
