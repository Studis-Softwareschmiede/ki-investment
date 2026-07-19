"""Demo-Portfolio-Wert-Snapshot-Historie (Story S-081,
`docs/specs/frontend-cockpit.md` AC22/AC32/AC33 — deckt den Demo-Seed-Teil
von AC33: "Der Demo-Seed füllt das Snapshot-Read-Modell deterministisch +
order-frei, sodass der Chart gefüllt und Playwright-testbar ist").

**Order-frei (AC22-Kern-Invariante, §13.7-6):** schreibt ausschliesslich
über `app.adapters.repositories.portfolio_snapshot_repository
.SqlAlchemyPortfolioSnapshotRepository.schreibe_snapshot` (reines Insert
in `portfolio_snapshot`, kein Order-/Sizing-/Risiko-/Execution-Aufruf).

**Idempotent:** `schreibe_snapshot` ist je (mode, Kalendertag) idempotent
(DB-`UNIQUE`-Constraint, → BR-142) — ein wiederholter Seed-Lauf überschreibt
nichts und erzeugt keine Duplikate, `schreibe_snapshot` liefert dann
einfach `False`.

**Deterministisch, kein `random`:** 60 Tage synthetischer Verlauf über
`math.sin` (keine Zufallsquelle, reproduzierbar) — Aufwärtstrend (linearer
Anteil) überlagert von einer leichten Auf-und-Ab-Bewegung (Sinus-Anteil),
Werte auf 2 Nachkommastellen gerundet (`Decimal(str(round(...)))`, analog
S-062-Konvention `.claude/lessons/coder.md`: `Decimal(str(float))` statt
`Decimal(float)`, um Binärfliesskomma-Rauschen nicht in die Spalte zu
übernehmen)."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.adapters.repositories.portfolio_snapshot_repository import (
    SqlAlchemyPortfolioSnapshotRepository,
)

#: AC22: ausschliesslich Paper-Daten.
_DEMO_MODE = "simuliert"

#: Fixer Endtag (kein `date.today()` — reproduzierbarer Seed unabhängig
#: vom Lauf-Zeitpunkt, analog den festen Zeitstempeln in `app.demo.depot`).
_END_DATUM = date(2026, 7, 19)
_ANZAHL_TAGE = 60

_STARTWERT = Decimal("5000.00")
_TREND_PRO_TAG = Decimal("25.00")
_OSZILLATION_AMPLITUDE = Decimal("180.00")
_CASH_QUOTE_BASIS = Decimal("9.500")
_CASH_QUOTE_AMPLITUDE = Decimal("2.500")


def _portfolio_wert(tag_index: int) -> Decimal:
    trend = _STARTWERT + _TREND_PRO_TAG * tag_index
    oszillation = float(_OSZILLATION_AMPLITUDE) * math.sin(tag_index / 5.0)
    return (trend + Decimal(str(round(oszillation, 2)))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _cash_quote(tag_index: int) -> Decimal:
    oszillation = float(_CASH_QUOTE_AMPLITUDE) * math.sin(tag_index / 9.0)
    wert = _CASH_QUOTE_BASIS + Decimal(str(round(oszillation, 3)))
    return max(wert, Decimal("0")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def seed_depot_verlauf(session: Session) -> None:
    """AC32/AC33: ~60 Tage plausibler Portfolio-Wert-Historie
    (mode=simuliert), leichte Auf-und-Ab-Bewegung mit Aufwärtstrend,
    idempotent."""
    repository = SqlAlchemyPortfolioSnapshotRepository(session)
    start_datum = _END_DATUM - timedelta(days=_ANZAHL_TAGE - 1)

    for tag_index in range(_ANZAHL_TAGE):
        tag = start_datum + timedelta(days=tag_index)
        zeitpunkt = datetime(tag.year, tag.month, tag.day, 22, 0, tzinfo=UTC)
        repository.schreibe_snapshot(
            mode=_DEMO_MODE,
            zeitpunkt=zeitpunkt,
            portfolio_wert=_portfolio_wert(tag_index),
            cash_quote=_cash_quote(tag_index),
        )
