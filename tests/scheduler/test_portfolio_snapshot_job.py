"""Tests für den Portfolio-Wert-Snapshot-Job (`app.scheduler
.portfolio_snapshot_job`, Story S-081, `docs/specs/frontend-cockpit.md`
AC32).

Covers (frontend-cockpit): AC32

Deckt `nimm_portfolio_snapshot_auf` (Bewertungsgrundlage: Live-Kurs sonst
Ø-Einstand-Fallback, Cash-Quote, Idempotenz-Weiterreichung → BR-142) sowie
`PortfolioSnapshotScheduler.tick`/`run_forever` (In-Process-Zustand analog
`app.scheduler.scheduler.Scheduler`, S-020) — alles gegen Fakes, keine
echte DB nötig."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.portfolio.ports import ExitRegelnBestand, PositionsBestand
from app.scheduler.portfolio_snapshot_job import (
    ALLE_MODI,
    PortfolioSnapshotScheduler,
    nimm_portfolio_snapshot_auf,
)


def _exit_regeln_leer() -> ExitRegelnBestand:
    return ExitRegelnBestand(
        stop_loss_pct=None,
        take_profit_pct=None,
        stop_typ=None,
        atr_multiplikator=None,
        thesis_invalidation=None,
        time_box=None,
    )


def _position(
    titel_id: str, *, menge: Decimal, einstand_preis: Decimal, asset_class_id: int = 1
) -> PositionsBestand:
    return PositionsBestand(
        position_id=f"lot-{titel_id}",
        titel_id=titel_id,
        asset_class_id=asset_class_id,
        gics_branche="Technology",
        menge=menge,
        einstand_preis=einstand_preis,
        strategie="Index",
        exit_regeln=_exit_regeln_leer(),
    )


class _FakePositionRepository:
    def __init__(self, positionen: list[PositionsBestand]):
        self._positionen = positionen

    def alle_offenen_positionen(self, *, mode):
        return self._positionen


class _FakeLivePriceProvider:
    def __init__(self, preise: dict[str, Decimal] | None = None):
        self._preise = preise or {}

    def aktueller_preis(self, titel_id):
        return self._preise.get(titel_id)


class _FakePortfolioSnapshotRepository:
    def __init__(self, *, geschrieben: bool = True):
        self._geschrieben = geschrieben
        self.aufrufe: list[dict[str, object]] = []

    def schreibe_snapshot(self, *, mode, zeitpunkt, portfolio_wert, cash_quote):
        self.aufrufe.append(
            {
                "mode": mode,
                "zeitpunkt": zeitpunkt,
                "portfolio_wert": portfolio_wert,
                "cash_quote": cash_quote,
            }
        )
        return self._geschrieben


def test_wert_faellt_ohne_live_kurs_auf_einstand_zurueck() -> None:
    """Moduldocstring: der Job liefert IMMER einen konkreten Wert (nie
    `None`) — anders als `unrealisierter_gv_gesamt` (AC3/AC14)."""
    positionen = [_position("t1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    snapshot_repository = _FakePortfolioSnapshotRepository()

    nimm_portfolio_snapshot_auf(
        repository=_FakePositionRepository(positionen),
        snapshot_repository=snapshot_repository,
        live_price=_FakeLivePriceProvider({}),
        mode="simuliert",
        jetzt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    assert snapshot_repository.aufrufe[0]["portfolio_wert"] == Decimal("1000")


def test_wert_nutzt_live_kurs_wenn_vorhanden() -> None:
    positionen = [_position("t1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    snapshot_repository = _FakePortfolioSnapshotRepository()

    nimm_portfolio_snapshot_auf(
        repository=_FakePositionRepository(positionen),
        snapshot_repository=snapshot_repository,
        live_price=_FakeLivePriceProvider({"t1": Decimal("120")}),
        mode="simuliert",
        jetzt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    assert snapshot_repository.aufrufe[0]["portfolio_wert"] == Decimal("1200")


def test_gemischte_live_kurse_bewerten_je_position_einzeln() -> None:
    positionen = [
        _position("t1", menge=Decimal("10"), einstand_preis=Decimal("100")),
        _position("t2", menge=Decimal("5"), einstand_preis=Decimal("50")),
    ]
    snapshot_repository = _FakePortfolioSnapshotRepository()

    nimm_portfolio_snapshot_auf(
        repository=_FakePositionRepository(positionen),
        snapshot_repository=snapshot_repository,
        live_price=_FakeLivePriceProvider({"t1": Decimal("110")}),
        mode="simuliert",
        jetzt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    # t1: 10*110=1100 (Live), t2: 5*50=250 (Einstand-Fallback) -> 1350.
    assert snapshot_repository.aufrufe[0]["portfolio_wert"] == Decimal("1350")


def test_cash_quote_ist_anteil_der_cash_asset_class_3() -> None:
    positionen = [
        _position("t1", menge=Decimal("10"), einstand_preis=Decimal("90"), asset_class_id=1),
        _position("cash", menge=Decimal("10"), einstand_preis=Decimal("10"), asset_class_id=3),
    ]
    snapshot_repository = _FakePortfolioSnapshotRepository()

    nimm_portfolio_snapshot_auf(
        repository=_FakePositionRepository(positionen),
        snapshot_repository=snapshot_repository,
        live_price=_FakeLivePriceProvider({}),
        mode="simuliert",
        jetzt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    # Gesamtwert 1000 (900+100), Cash-Anteil 100 -> 10%.
    assert snapshot_repository.aufrufe[0]["cash_quote"] == Decimal("10.000")


def test_leeres_depot_liefert_wert_null_kein_fehler() -> None:
    snapshot_repository = _FakePortfolioSnapshotRepository()

    ergebnis = nimm_portfolio_snapshot_auf(
        repository=_FakePositionRepository([]),
        snapshot_repository=snapshot_repository,
        live_price=_FakeLivePriceProvider({}),
        mode="simuliert",
        jetzt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    assert ergebnis is True
    assert snapshot_repository.aufrufe[0]["portfolio_wert"] == Decimal("0")
    assert snapshot_repository.aufrufe[0]["cash_quote"] == Decimal("0")


def test_portfolio_wert_wird_auf_8_nachkommastellen_quantisiert() -> None:
    """Review-Fund Iteration 1 (Important): ein unquantisierter Geldwert mit
    mehr als 8 Nachkommastellen würde beim Schreiben in `NUMERIC(20,8)`
    still DB-seitig gerundet (ROUND_HALF_EVEN statt Projektkonvention
    ROUND_HALF_UP, P7/ADR-010) — `nimm_portfolio_snapshot_auf` muss selbst
    an der Schreibgrenze quantisieren (analog
    `position_booking._quantize_geld`)."""
    positionen = [_position("t1", menge=Decimal("3"), einstand_preis=Decimal("33.333333335"))]
    snapshot_repository = _FakePortfolioSnapshotRepository()

    nimm_portfolio_snapshot_auf(
        repository=_FakePositionRepository(positionen),
        snapshot_repository=snapshot_repository,
        live_price=_FakeLivePriceProvider({}),
        mode="simuliert",
        jetzt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    # 3 * 33.333333335 = 99.999999... exakt Decimal("100.000000005") ->
    # ROUND_HALF_UP auf 8 Nachkommastellen: 100.00000001.
    geschriebener_wert = snapshot_repository.aufrufe[0]["portfolio_wert"]
    assert geschriebener_wert == Decimal("100.00000001")
    assert -geschriebener_wert.as_tuple().exponent == 8


def test_idempotenz_wird_vom_repository_durchgereicht() -> None:
    """@trace frontend-cockpit#AC32 — → BR-142: liefert `False`, wenn das
    Repository bereits einen Snapshot für diesen Tag/Modus meldet."""
    snapshot_repository = _FakePortfolioSnapshotRepository(geschrieben=False)

    ergebnis = nimm_portfolio_snapshot_auf(
        repository=_FakePositionRepository([]),
        snapshot_repository=snapshot_repository,
        live_price=_FakeLivePriceProvider({}),
        mode="simuliert",
        jetzt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    assert ergebnis is False


def test_scheduler_zeichnet_beide_modi_beim_ersten_tick_auf() -> None:
    snapshot_repository = _FakePortfolioSnapshotRepository()
    scheduler = PortfolioSnapshotScheduler(
        repository_factory=lambda: _FakePositionRepository([]),
        snapshot_repository_factory=lambda: snapshot_repository,
        live_price_factory=lambda: _FakeLivePriceProvider({}),
        jetzt=lambda: datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    aufgezeichnet = scheduler.tick()

    assert sorted(aufgezeichnet) == sorted(ALLE_MODI)
    assert len(snapshot_repository.aufrufe) == 2


def test_scheduler_ueberspringt_noch_nicht_faellige_modi() -> None:
    snapshot_repository = _FakePortfolioSnapshotRepository()
    jetzt = [datetime(2026, 7, 1, 22, 0, tzinfo=UTC)]
    scheduler = PortfolioSnapshotScheduler(
        repository_factory=lambda: _FakePositionRepository([]),
        snapshot_repository_factory=lambda: snapshot_repository,
        live_price_factory=lambda: _FakeLivePriceProvider({}),
        intervall_sekunden=86400.0,
        jetzt=lambda: jetzt[0],
    )

    scheduler.tick()
    jetzt[0] = jetzt[0].replace(hour=23)  # 1h später, Intervall ist 24h
    zweiter_tick = scheduler.tick()

    assert zweiter_tick == []
    assert len(snapshot_repository.aufrufe) == 2  # nur der erste Tick


def test_fehlschlagender_mode_stoppt_weder_anderen_mode_noch_den_tick() -> None:
    """Review-Fund Iteration 1 (Important): EIN transienter/permanenter
    DB-/Provider-Fehler in `mode="echt"` darf `mode="simuliert"` im selben
    Tick nicht verhindern und `tick()` darf nicht propagieren (sonst
    beendet `run_forever()`s `while True`-Schleife dauerhaft)."""

    class _KaputteFuerEchtRepository:
        def alle_offenen_positionen(self, *, mode):
            if mode == "echt":
                raise ConnectionError("db weg")
            return []

    snapshot_repository = _FakePortfolioSnapshotRepository()
    scheduler = PortfolioSnapshotScheduler(
        repository_factory=lambda: _KaputteFuerEchtRepository(),
        snapshot_repository_factory=lambda: snapshot_repository,
        live_price_factory=lambda: _FakeLivePriceProvider({}),
        jetzt=lambda: datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )

    aufgezeichnet = scheduler.tick()  # darf NICHT werfen

    assert aufgezeichnet == ["simuliert"]
    assert [aufruf["mode"] for aufruf in snapshot_repository.aufrufe] == ["simuliert"]


def test_run_forever_tickt_trotz_fehlschlagendem_mode_weiter() -> None:
    """Wie oben, aber über `run_forever()`: ein dauerhaft fehlschlagender
    `mode="echt"` darf die Endlosschleife nicht nach dem ersten Tick
    beenden."""

    class _StetsKaputteRepository:
        def alle_offenen_positionen(self, *, mode):
            if mode == "echt":
                raise TimeoutError("provider timeout")
            return []

    snapshot_repository = _FakePortfolioSnapshotRepository()
    scheduler = PortfolioSnapshotScheduler(
        repository_factory=lambda: _StetsKaputteRepository(),
        snapshot_repository_factory=lambda: snapshot_repository,
        live_price_factory=lambda: _FakeLivePriceProvider({}),
        intervall_sekunden=0.0,
        jetzt=lambda: datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )
    tick_count = 0

    async def _fake_sleep(_seconds: float) -> None:
        nonlocal tick_count
        tick_count += 1
        if tick_count >= 3:
            raise asyncio.CancelledError

    async def _run() -> None:
        try:
            await scheduler.run_forever(sleep=_fake_sleep)
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())

    assert tick_count == 3
    # jeder der 3 Ticks zeichnet "simuliert" auf, "echt" scheitert stets.
    assert len(snapshot_repository.aufrufe) == 3
    assert {aufruf["mode"] for aufruf in snapshot_repository.aufrufe} == {"simuliert"}


def test_run_forever_tickt_wiederholt_bis_cancelled() -> None:
    snapshot_repository = _FakePortfolioSnapshotRepository()
    scheduler = PortfolioSnapshotScheduler(
        repository_factory=lambda: _FakePositionRepository([]),
        snapshot_repository_factory=lambda: snapshot_repository,
        live_price_factory=lambda: _FakeLivePriceProvider({}),
        jetzt=lambda: datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
    )
    tick_count = 0

    async def _fake_sleep(_seconds: float) -> None:
        nonlocal tick_count
        tick_count += 1
        if tick_count >= 3:
            raise asyncio.CancelledError

    async def _run() -> None:
        try:
            await scheduler.run_forever(sleep=_fake_sleep)
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())

    assert tick_count == 3
    assert len(snapshot_repository.aufrufe) == 2  # nur der allererste Tick war faellig
