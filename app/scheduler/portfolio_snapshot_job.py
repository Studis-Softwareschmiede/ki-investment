"""Portfolio-Wert-Snapshot-Job (periodischer Scheduler-Job, `docs/specs/
frontend-cockpit.md` AC32, Story S-081; `docs/data-model.md` §5
`portfolio_snapshot`).

**Aufzeichnungs-Mechanik = periodischer Snapshot-Job, NICHT Write-on-Read**
(AC32 wörtlich): dieser Job berechnet den Portfolio-Gesamtwert je `mode`
(→ BR-130) ausschliesslich aus den bestehenden Lese-Ports
(`app.domain.portfolio.ports.PositionRepository`/`LivePriceProvider`) und
schreibt über `app.domain.portfolio_verlauf.ports
.PortfolioSnapshotRepository.schreibe_snapshot` eine neue
`portfolio_snapshot`-Zeile — die Query-/UI-Schicht (`app/api/queries/**`,
`app/api/ui.py`) bleibt dabei strikt read-only (Boundary AC2 unverändert,
`tests/architecture/test_ui_boundary.py` erfasst dieses Modul bewusst
NICHT, da es weder unter `app/api/queries/**` noch `app/api/ui.py` liegt).
Löst **keine** Order/Sizing/Risiko/Execution aus (§13.7-6).

**Bewertungsgrundlage (`_positionswert_fuer_snapshot`):** je Position der
aktuelle Live-Kurs (`LivePriceProvider.aktueller_preis`), sonst
Ø-Einstandspreis als Fallback — anders als `unrealisierter_gv_gesamt`
(AC3/AC14, liefert bei fehlendem Live-Kurs bewusst `None`) liefert dieser
Job IMMER einen konkreten Wert: ein Verlauf-Chart mit Lücken, sobald ein
einziger Titel keinen Live-Kurs hat, wäre für AC33 nutzlos (aktuell liefert
`NoOpLivePriceProvider`, S-054, ohnehin nie einen Kurs — der Job reduziert
sich damit produktiv auf die Kostenbasis, bis ein echter Live-Kurs-Adapter
verdrahtet ist, und beginnt dann automatisch echte Marktwerte
abzubilden, ohne Codeänderung hier).

**Idempotenz (→ BR-142):** `PortfolioSnapshotRepository.schreibe_snapshot`
ist je (mode, Kalendertag) idempotent (DB-`UNIQUE`-Constraint,
Insert-Then-Catch) — ein zusätzlicher Lauf am selben Tag erzeugt keine
Duplikat-Zeile, `nimm_portfolio_snapshot_auf` liefert dann `None` statt
eines neuen Eintrags.

**Scheduler-Wiring (analog `app.scheduler.scheduler.Scheduler`, S-020):**
`PortfolioSnapshotScheduler` bietet `tick()`/`run_forever()` im selben
In-Process-Zustands-Muster (nächster fälliger Lauf je `mode` gemerkt,
erster Tick nach Prozessstart löst sofort aus). Wie der bestehende
DataSource-`Scheduler` (S-020) ist dieser Job-Scheduler NICHT in
`app.main`/eine Lifespan-Hook verdrahtet — die tatsächliche
Prozess-/Deploy-Anbindung (`run_forever` in einem Worker-Prozess) ist
Infra-Scope einer künftigen Story (kein main.py-Anschluss in dieser
Story, `main.py höchstens +1 Router-Zeile`)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.domain.portfolio.ports import LivePriceProvider, PositionRepository, PositionsBestand
from app.domain.portfolio_verlauf.ports import Modus, PortfolioSnapshotRepository
from app.scheduler.errors import ist_transienter_fehler

logger = logging.getLogger(__name__)

#: Beide Modi werden je Tick unabhängig aufgezeichnet (→ BR-130, getrennte
#: Aggregate — nie vermischt).
ALLE_MODI: tuple[Modus, ...] = ("echt", "simuliert")

#: Rundungsraster an der Schreibgrenze (P7/ADR-010) — deckt sich mit dem
#: DB-Spaltentyp `NUMERIC(20,8)` (data-model.md §5 `portfolio_snapshot`),
#: private Kopie analog `position_booking._quantize_geld` (Hot-Spot-
#: Konvention, kein Cross-Import nur für eine Ein-Zeilen-Funktion).
_GELD_QUANTUM = Decimal("0.00000001")


def _quantize_geld(wert: Decimal) -> Decimal:
    """Rundet einen Geldwert an der Schreibgrenze auf 8 Nachkommastellen
    (NUMERIC(20,8), P7) — kaufmännisch gerundet (`ROUND_HALF_UP`), analog
    `app.domain.portfolio.position_booking._quantize_geld`."""
    return wert.quantize(_GELD_QUANTUM, rounding=ROUND_HALF_UP)


#: Anlageklasse 3 = "Cash / Geldmarkt" (identisch zu
#: `app.domain.portfolio.portfolio_aggregate.CASH_ASSET_CLASS_ID`, hier
#: keine Cross-Import-Kopplung nötig, da nur der Wert, nicht die volle
#: Aggregat-Formel wiederverwendet wird).
_CASH_ASSET_CLASS_ID = 3


def _positionswert_fuer_snapshot(
    position: PositionsBestand, *, live_price: LivePriceProvider
) -> Decimal:
    """Bewertungsgrundlage je Position für den Snapshot (Moduldocstring):
    aktueller Live-Kurs, sonst Ø-Einstandspreis als Fallback — liefert
    IMMER einen konkreten Wert (nie `None`)."""
    aktueller_preis = live_price.aktueller_preis(position.titel_id)
    preis = aktueller_preis if aktueller_preis is not None else position.einstand_preis
    return position.menge * preis


def _cash_quote_fuer_snapshot(
    positionen: list[PositionsBestand], *, gesamtwert: Decimal
) -> Decimal:
    """Cash-Quote (%) als Anteil der Kostenbasis der Anlageklasse 3 an der
    depotweiten Kostenbasis — dieselbe Bewertungsgrundlage (Kostenbasis)
    wie `app.domain.portfolio.portfolio_aggregate.berechne_portfolio_aggregat`,
    hier lokal nachgerechnet (kein zweiter Aufruf der vollen
    Aggregat-Formel nötig, nur die Cash-Teilsumme)."""
    if gesamtwert == 0:
        return Decimal("0")
    cash_positionen = (p for p in positionen if p.asset_class_id == _CASH_ASSET_CLASS_ID)
    cash_wert = sum((p.menge * p.einstand_preis for p in cash_positionen), Decimal("0"))
    return (cash_wert / gesamtwert * 100).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def nimm_portfolio_snapshot_auf(
    *,
    repository: PositionRepository,
    snapshot_repository: PortfolioSnapshotRepository,
    live_price: LivePriceProvider,
    mode: Modus,
    jetzt: datetime,
) -> bool:
    """AC32: ein Snapshot-Durchlauf für EINEN `mode` — liest die offenen
    Positionen (`PositionRepository.alle_offenen_positionen`), berechnet
    den Portfolio-Gesamtwert + die Cash-Quote und schreibt eine neue
    `portfolio_snapshot`-Zeile über `PortfolioSnapshotRepository
    .schreibe_snapshot` (idempotent je Kalendertag, → BR-142). Liefert
    `True` bei neu geschriebenem Snapshot, `False` bei bereits
    vorhandenem (kein Fehler — der Job darf beliebig oft/redundant
    laufen)."""
    positionen = repository.alle_offenen_positionen(mode=mode)
    portfolio_wert = sum(
        (_positionswert_fuer_snapshot(p, live_price=live_price) for p in positionen),
        Decimal("0"),
    )
    cash_quote = _cash_quote_fuer_snapshot(positionen, gesamtwert=portfolio_wert)

    geschrieben = snapshot_repository.schreibe_snapshot(
        mode=mode,
        zeitpunkt=jetzt,
        portfolio_wert=_quantize_geld(portfolio_wert),
        cash_quote=cash_quote,
    )
    if not geschrieben:
        logger.debug(
            "Portfolio-Snapshot für mode=%s/%s bereits vorhanden (Idempotenz, BR-142).",
            mode,
            jetzt.date(),
        )
    return geschrieben


class PortfolioSnapshotScheduler:
    """Periodischer Job-Scheduler (analog `app.scheduler.scheduler
    .Scheduler`, S-020) — merkt sich je `mode` den nächsten fälligen Lauf
    (In-Process-Zustand, bei Neustart beginnt die Zählung neu, der erste
    `tick()` löst sofort aus)."""

    def __init__(
        self,
        *,
        repository_factory: Callable[[], PositionRepository],
        snapshot_repository_factory: Callable[[], PortfolioSnapshotRepository],
        live_price_factory: Callable[[], LivePriceProvider],
        intervall_sekunden: float = 86400.0,
        jetzt: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository_factory = repository_factory
        self._snapshot_repository_factory = snapshot_repository_factory
        self._live_price_factory = live_price_factory
        self._intervall = timedelta(seconds=intervall_sekunden)
        self._jetzt = jetzt
        self._naechster_lauf: dict[Modus, datetime] = {}

    def tick(self) -> list[Modus]:
        """Ein Tick: nimmt für jeden fälligen `mode` einen Snapshot auf.
        Liefert die tatsächlich aufgezeichneten Modi (Inspektion, z. B.
        Tests).

        Jeder `mode` läuft in einem eigenen `try`/`except` (Review-Fund
        Iteration 1): ein transienter/permanenter DB-/Provider-Fehler in
        EINEM Modus darf weder den anderen Modus im selben Tick verhindern
        noch `run_forever()`s Endlosschleife dauerhaft beenden — beide
        Fehlerklassen werden geloggt (Klassifikation über
        `app.scheduler.errors.ist_transienter_fehler`, analog
        `app.scheduler.worker.Worker`, S-020) und der Tick läuft mit dem
        nächsten Modus weiter."""
        jetzt = self._jetzt()
        aufgezeichnet: list[Modus] = []
        repository = self._repository_factory()
        snapshot_repository = self._snapshot_repository_factory()
        live_price = self._live_price_factory()

        for mode in ALLE_MODI:
            faellig = self._naechster_lauf.get(mode)
            if faellig is not None and jetzt < faellig:
                continue
            self._naechster_lauf[mode] = jetzt + self._intervall
            try:
                geschrieben = nimm_portfolio_snapshot_auf(
                    repository=repository,
                    snapshot_repository=snapshot_repository,
                    live_price=live_price,
                    mode=mode,
                    jetzt=jetzt,
                )
            except Exception as fehler:  # noqa: BLE001 — je mode isolieren, s. Docstring.
                if ist_transienter_fehler(fehler):
                    logger.warning(
                        "Portfolio-Snapshot für mode=%s transient fehlgeschlagen, "
                        "nächster Tick versucht es erneut: %s",
                        mode,
                        fehler,
                    )
                else:
                    logger.error(
                        "Portfolio-Snapshot für mode=%s permanent fehlgeschlagen: %s",
                        mode,
                        fehler,
                    )
                continue
            if geschrieben:
                aufgezeichnet.append(mode)
        return aufgezeichnet

    async def run_forever(
        self,
        *,
        tick_interval_sekunden: float = 60.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Produktions-Endlosschleife (bis `asyncio.CancelledError`) —
        pollt alle `tick_interval_sekunden`, deutlich unter dem
        Aufzeichnungs-Intervall selbst (Default 1 Snapshot/Tag), damit
        `tick()` den fälligen Zeitpunkt nicht spürbar verpasst. NICHT in
        `app.main` verdrahtet (Moduldocstring)."""
        while True:
            self.tick()
            await sleep(tick_interval_sekunden)


__all__ = [
    "ALLE_MODI",
    "PortfolioSnapshotScheduler",
    "nimm_portfolio_snapshot_auf",
]
