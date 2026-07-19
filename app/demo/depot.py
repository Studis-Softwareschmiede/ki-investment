"""Demo-Depot-Positionen + Trade-Historie (Story S-070,
`docs/specs/frontend-cockpit.md` AC22).

**Order-frei (AC22-Kern-Invariante, §13.7-6):** schreibt ausschliesslich
über den bestehenden, selbst Order-Pfad-freien Buchungs-Kern
`app.domain.portfolio.position_booking.verbuche_fill` +
`app.adapters.repositories.position_repository
.SqlAlchemyPositionRepository` — beide importieren kein
`app.domain.sizing`/`app.domain.risikomanagement`/`app.domain.execution`
(Depotmodul, nicht Order-Pfad, siehe `tests/architecture
/test_order_pfad_invariante.py`-Glob-Katalog, der `domain/portfolio`
bewusst NICHT listet). Es wird keine `OrderAnfrage` gebaut/gesendet —
Fills sind hier reine Fixture-Daten, kein Broker-/Sizing-Ergebnis.

**Idempotent:** `verbuche_fill` markiert jeden Fill zuerst über den
bestehenden ADR-011-Dedup-Mechanismus (`depot_fill_dedup.client_order_id`,
S-016) — jeder Demo-Fill trägt eine deterministische
`client_order_id` (`"demo-seed-<richtung>-<titel>-NNN"`); ein
wiederholter Aufruf bricht pro Fill sofort mit
`BuchungsErgebnis.bereits_verbucht=True` ab, ohne den Bestand erneut zu
mutieren. Ein `session.commit()` je Fill (statt eines gesammelten Commits
am Ende) begrenzt den Rollback-Radius: `markiere_fill_verbucht` rollt bei
einem bereits bekannten `client_order_id` die GESAMTE offene Transaktion
zurück (siehe dessen Docstring) — bliebe vorherige Arbeit im selben
Commit-Fenster uncommitted, würde sie mit zurückgerollt."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.contracts.depot import ExitRegeln, FillInput, Modus, Richtung
from app.demo.instrumente import instrument_id
from app.domain.portfolio.position_booking import verbuche_fill

#: BR-112-Default (`app.config.Settings.einstand_methode_default`) — hier
#: bewusst als eigener, fixer Demo-Wert statt eines Settings-Imports: der
#: Demo-Seed soll unabhängig von einer künftigen Settings-Änderung
#: reproduzierbar bleiben.
_EINSTAND_METHODE_DEMO = "gleitender_durchschnitt"

#: AC22: ausschliesslich Paper-Fills.
_DEMO_MODE: Modus = "simuliert"

_DEMO_EXIT_REGELN = ExitRegeln(
    stop_typ="fix_pct",
    stop_parameter=8.0,
    take_profit=20.0,
    thesis_invalidierung="Demo-These invalidiert bei nachhaltigem Branchenabschwung.",
)


def _fill(
    *,
    client_order_id: str,
    titel_slug: str,
    anlageklasse: int,
    gics_branche: str,
    richtung: Richtung,
    menge: str,
    fill_preis: str,
    kosten: str,
    arrival_price: str,
    zeitstempel: datetime,
    strategie: str | None = None,
    zeithorizont: int | None = None,
    exit_regeln: ExitRegeln | None = None,
    these: str | None = None,
) -> FillInput:
    return FillInput(
        client_order_id=client_order_id,
        titel_id=str(instrument_id(titel_slug)),
        anlageklasse=anlageklasse,
        gics_branche=gics_branche,
        richtung=richtung,
        menge=Decimal(menge),
        fill_preis=Decimal(fill_preis),
        kosten=Decimal(kosten),
        arrival_price=Decimal(arrival_price),
        waehrung="CHF",
        zeitstempel=zeitstempel,
        mode=_DEMO_MODE,
        strategie=strategie,
        zeithorizont=zeithorizont,
        exit_regeln=exit_regeln,
        these=these,
    )


#: Drei Käufe (NESN, NOVN, CHSPI) + ein Teilverkauf (NESN) — "einige
#: Paper-Positionen" (AC22) mit Trade-Historie inkl. Slippage/TCA
#: (`arrival_price`/`slippage_abs`, von `schreibe_transaktion` für jeden
#: Fill gesetzt, S-035/AC7).
_DEMO_FILLS: tuple[FillInput, ...] = (
    _fill(
        client_order_id="demo-seed-kauf-nesn-001",
        titel_slug="demo-instrument-nesn",
        anlageklasse=1,
        gics_branche="Consumer Staples",
        richtung="kauf",
        menge="10",
        fill_preis="95.50",
        kosten="15",
        arrival_price="95.30",
        zeitstempel=datetime(2026, 6, 2, 9, 5, tzinfo=UTC),
        strategie="Index",
        zeithorizont=6,
        exit_regeln=_DEMO_EXIT_REGELN,
        these="Defensive Qualitätsposition, stabile Cashflows.",
    ),
    _fill(
        client_order_id="demo-seed-kauf-novn-001",
        titel_slug="demo-instrument-novn",
        anlageklasse=1,
        gics_branche="Health Care",
        richtung="kauf",
        menge="20",
        fill_preis="88.20",
        kosten="15",
        arrival_price="88.00",
        zeitstempel=datetime(2026, 6, 5, 9, 12, tzinfo=UTC),
        strategie="Index",
        zeithorizont=6,
        exit_regeln=_DEMO_EXIT_REGELN,
        these="Pipeline-getriebenes Wachstum, defensiver Sektor.",
    ),
    _fill(
        client_order_id="demo-seed-kauf-chspi-001",
        titel_slug="demo-instrument-chspi",
        anlageklasse=2,
        gics_branche="Diversifiziert",
        richtung="kauf",
        menge="30",
        fill_preis="130.00",
        kosten="12",
        arrival_price="129.80",
        zeitstempel=datetime(2026, 6, 10, 9, 20, tzinfo=UTC),
        strategie="Index",
        zeithorizont=6,
        exit_regeln=_DEMO_EXIT_REGELN,
        these="Breite Diversifikation über Schweizer Dividendentitel.",
    ),
    _fill(
        client_order_id="demo-seed-verkauf-nesn-001",
        titel_slug="demo-instrument-nesn",
        anlageklasse=1,
        gics_branche="Consumer Staples",
        richtung="verkauf",
        menge="4",
        fill_preis="99.00",
        kosten="8",
        arrival_price="98.80",
        zeitstempel=datetime(2026, 6, 25, 10, 0, tzinfo=UTC),
    ),
)


def seed_depot(session: Session) -> None:
    """AC22: Paper-Positionen + Trade-Historie — je Fill EIN
    `verbuche_fill`-Aufruf, gefolgt von einem eigenen `session.commit()`
    (Idempotenz-Rollback-Radius-Begrenzung, siehe Modul-Docstring)."""
    repository = SqlAlchemyPositionRepository(session)
    for fill in _DEMO_FILLS:
        verbuche_fill(fill, repository=repository, einstand_methode_default=_EINSTAND_METHODE_DEMO)
        session.commit()
