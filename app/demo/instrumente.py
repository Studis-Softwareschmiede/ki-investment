"""Demo-Instrumente (Story S-070, `docs/specs/frontend-cockpit.md` AC22).

`app.db.models.Instrument` hat laut eigenem Docstring bislang KEINEN
Erst-Anlage-Schreibpfad — kein bestehendes Modul legt `instrument`-Zeilen
an (die Kandidatensuche/Analyse-Module, die einen Titel zuerst
identifizieren würden, sind noch nicht gebaut). Diese Datei füllt daher
direkt per ORM (klar markierter Fixture-Insert, AC22 "Fixture-Inserts" —
kein bestehender Repository-/Buchungs-Pfad existiert, den es stattdessen
zu nutzen gälte): eine reine, order-freie Stammdaten-Zeile ohne jeden
Order-/Sizing-/Risiko-Bezug.

Idempotent: `id` ist deterministisch aus dem Symbol-Slug abgeleitet
(`app.demo._namespace.demo_id`, analog zum `data_source`-Seed-Muster,
Migration `ea80c97626ee`) — ein wiederholter Aufruf trifft dieselbe Zeile
(Existenzprüfung vor Insert)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import Instrument
from app.demo._namespace import demo_id


@dataclass(frozen=True)
class DemoInstrument:
    slug: str
    symbol: str
    name: str
    asset_class_id: int
    gics_sector: str | None
    currency: str = "CHF"


#: Vier Demo-Titel über zwei Anlageklassen (Aktien, ETFs) — genug Vielfalt
#: für Branchen-/Klassen-Gewichtung im Depot-Aggregat (AC3/AC8/AC9,
#: `app.domain.portfolio.portfolio_aggregate`), ohne über AC22 hinaus zu
#: gehen (drei werden tatsächlich gehalten, siehe `app.demo.depot`; ROG
#: bleibt reiner Kandidat, siehe `app.demo.kandidaten`).
DEMO_INSTRUMENTS: tuple[DemoInstrument, ...] = (
    DemoInstrument(
        slug="demo-instrument-nesn",
        symbol="NESN",
        name="Nestlé SA",
        asset_class_id=1,
        gics_sector="Consumer Staples",
    ),
    DemoInstrument(
        slug="demo-instrument-novn",
        symbol="NOVN",
        name="Novartis AG",
        asset_class_id=1,
        gics_sector="Health Care",
    ),
    DemoInstrument(
        slug="demo-instrument-chspi",
        symbol="CHSPI",
        name="iShares Swiss Dividend ETF",
        asset_class_id=2,
        gics_sector=None,
    ),
    DemoInstrument(
        slug="demo-instrument-rog",
        symbol="ROG",
        name="Roche Holding AG",
        asset_class_id=1,
        gics_sector="Health Care",
    ),
)


def instrument_id(slug: str) -> uuid.UUID:
    """Deterministische `instrument.id` für einen Demo-Slug — von den
    übrigen Demo-Modulen (`app.demo.depot`, `app.demo.kandidaten`)
    referenziert, ohne die Zeile selbst erneut anzulegen."""
    return demo_id(slug)


def seed_instrumente(session: Session) -> None:
    """Legt alle `DEMO_INSTRUMENTS`-Zeilen idempotent an (Existenzprüfung
    vor Insert, ein Commit je Zeile — begrenzt den Rollback-Radius eines
    späteren, unabhängigen Demo-Schritts)."""
    for eintrag in DEMO_INSTRUMENTS:
        titel_id = instrument_id(eintrag.slug)
        if session.get(Instrument, titel_id) is not None:
            continue
        session.add(
            Instrument(
                id=titel_id,
                symbol=eintrag.symbol,
                name=eintrag.name,
                asset_class_id=eintrag.asset_class_id,
                gics_sector=eintrag.gics_sector,
                currency=eintrag.currency,
            )
        )
        session.commit()
