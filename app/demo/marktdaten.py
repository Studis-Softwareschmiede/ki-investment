"""Demo-Marktdaten Bronze/Silver/Gold (Story S-070,
`docs/specs/frontend-cockpit.md` AC22).

Schreibt ausschliesslich über die bestehenden, bereits idempotenten
Store-Funktionen `app.db.bronze.record_observation`,
`app.db.silver.record_silver_observation`,
`app.db.gold.record_gold_observation` (kein eigener Insert, keine
Order-Pfad-Berührung — reine Marktdaten-Schicht, S-022/S-024/S-051). Jede
dieser Funktionen ist bei identischem Payload/`observed_at` bereits
selbst idempotent (siehe deren Docstrings) — ein `session.commit()` je
Schicht (Bronze/Silver/Gold, statt eines gesammelten Commits am Ende)
begrenzt den Rollback-Radius eines eventuellen, von der jeweiligen
Store-Funktion selbst gefangenen `IntegrityError`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.bronze import record_observation
from app.db.gold import record_gold_observation
from app.db.models import DataSource
from app.db.silver import record_silver_observation

#: Bereits von der bestehenden `data_source`-Seed-Migration (`ea80c97626ee`,
#: AC13) angelegte, aktive Quelle — der Demo-Seed erfindet keine eigene
#: Quelle, sondern nutzt eine real registrierte.
_DEMO_QUELLE_NAME = "SEC Form 4 Insider-Trades"

_DEMO_MARKTDATEN: tuple[dict[str, Any], ...] = (
    {
        "symbol": "NESN",
        "asset_class_tag": 1,
        "source_event_id": "demo-seed-marktdaten-nesn-1",
        "wert": Decimal("95.50"),
        "observed_at": datetime(2026, 6, 2, 8, 0, tzinfo=UTC),
    },
    {
        "symbol": "NOVN",
        "asset_class_tag": 1,
        "source_event_id": "demo-seed-marktdaten-novn-1",
        "wert": Decimal("88.20"),
        "observed_at": datetime(2026, 6, 5, 8, 0, tzinfo=UTC),
    },
)


def seed_marktdaten(session: Session) -> None:
    """AC22: Bronze/Silver/Gold-Beispieldaten — je Demo-Symbol EINE
    vollständige Bronze→Silver→Gold-Kette."""
    quelle_id = session.execute(
        select(DataSource.id).where(DataSource.name == _DEMO_QUELLE_NAME)
    ).scalar_one()

    for eintrag in _DEMO_MARKTDATEN:
        bronze_zeile = record_observation(
            session,
            data_source_id=quelle_id,
            source_event_id=eintrag["source_event_id"],
            payload={"kurs": str(eintrag["wert"]), "waehrung": "CHF"},
            beobachtungs_zeitpunkt=eintrag["observed_at"],
            anlageklassen_tag=eintrag["asset_class_tag"],
            symbol=eintrag["symbol"],
            quality_indicator="hoch",
        )
        session.commit()

        silber_zeile = record_silver_observation(
            session,
            bronze_zeile=bronze_zeile,
            normalisierter_wert=eintrag["wert"],
            einheit="CHF",
        )
        session.commit()

        record_gold_observation(session, bronze_zeile=bronze_zeile, silber_zeile=silber_zeile)
        session.commit()
