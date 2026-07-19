"""Repository-Port für das Portfolio-Wert-Snapshot-Read-Modell
(architecture.md §4: "abstrakte Protokolle in `app/domain/**/ports.py`",
P1; Story S-081, `docs/specs/frontend-cockpit.md` AC32).

Eigener, von `app.domain.portfolio` bewusst getrennter Domänen-Namensraum
(analog `app.domain.warteliste`, S-079) — dieser Port deckt sowohl das
Lesen (Query-Funktion `app.api.queries.depot_verlauf`, Boundary AC2: kein
`sqlalchemy`-Import, kein `session.add`/`commit` in
`app/api/queries/**`/`app/api/ui.py`) als auch das Schreiben (periodischer
Scheduler-Job `app.scheduler.portfolio_snapshot_job`, AUSSERHALB der
Boundary-geprüften Dateien) über eine einzige Implementierung ab
(`app.adapters.repositories.portfolio_snapshot_repository
.SqlAlchemyPortfolioSnapshotRepository`) — analog zu `PositionRepository`
(Lese-/Schreib-Port in einem Protocol, `app.domain.portfolio.ports`)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol

Modus = Literal["echt", "simuliert"]


@dataclass(frozen=True)
class PortfolioSnapshotEintrag:
    """Ein Eintrag der Portfolio-Wert-Zeitreihe (AC32): Zeitpunkt,
    Portfolio-Wert und Cash-Quote (optionales Zusatzfeld laut AC32 wörtlich,
    hier stets gesetzt, da der Snapshot-Job es ohnehin aus den bestehenden
    Portfolio-Aggregaten mitberechnet)."""

    zeitpunkt: datetime
    portfolio_wert: Decimal
    cash_quote: Decimal


class PortfolioSnapshotRepository(Protocol):
    def verlauf(
        self,
        *,
        mode: Modus,
        von: datetime | None = None,
        bis: datetime | None = None,
    ) -> list[PortfolioSnapshotEintrag]:
        """AC32: liefert die Portfolio-Wert-Zeitreihe im angegebenen `mode`
        (→ BR-130), aufsteigend nach Zeitpunkt sortiert, optional auf den
        beidseitig inklusiven Zeitraum `[von, bis]` gefiltert (`None` = kein
        Filter je Grenze). Leere Liste, falls (noch) keine Historie
        existiert (AC32-Edge-Case, deckt E2-Muster)."""
        ...

    def schreibe_snapshot(
        self,
        *,
        mode: Modus,
        zeitpunkt: datetime,
        portfolio_wert: Decimal,
        cash_quote: Decimal,
    ) -> bool:
        """AC32: schreibt einen neuen Snapshot für den Kalendertag von
        `zeitpunkt` (UTC) — idempotent je (mode, Kalendertag, → BR-142):
        liefert `True` bei erfolgreichem Insert, `False`, wenn für diesen
        Kalendertag/Modus bereits ein Snapshot existiert (kein Duplikat,
        DB-`UNIQUE`-Constraint statt Read-then-Write-Dedupe)."""
        ...
