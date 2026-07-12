"""Transaktionshistorie (append-only) & Transaction-Cost-Analysis (TCA)
(Modul 16 Depotmodul, Spec `docs/specs/depot.md`, Story S-035, AC4/AC7).

- **AC4** — jeder Fill wird als unveränderlicher Eintrag in einer
  append-only Transaktionshistorie festgehalten. Diese Datei liefert dafür
  nur die reine Slippage-Formel (s.u.); das eigentliche Schreiben/Lesen ist
  Repository-Sache (`app.domain.portfolio.ports.PositionRepository
  .schreibe_transaktion`/`historie_je_titel`,
  `app.adapters.repositories.position_repository`).
  `app.domain.portfolio.position_booking.verbuche_fill` ruft
  `schreibe_transaktion` nach jeder erfolgreichen Buchung auf, damit
  Positions-Mutation und Historie-Eintrag im selben Commit landen
  (analog zur bestehenden Dedup-Marker/Positions-Mutation-Invariante,
  S-016 DBA-Zweit-Review).
- **AC7** — `berechne_slippage` ist die reine Formel (Fill-Preis −
  Arrival-Price, identisch zu BR-114 `trade_fill.slippage_abs`, hier auf
  die Depot-eigene Historie angewandt, C-017); `aggregiere_slippage`
  summiert mehrere je-Trade ermittelte Slippage-Werte zu einem TCA-Wert
  ("je Trade und aggregiert abrufbar" — dieselbe Summen-Konvention wie
  `position_booking.aggregiere_gv`, AC2).
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal


def berechne_slippage(fill_preis: Decimal, arrival_price: Decimal) -> Decimal:
    """AC7: realisierte Arrival-Price-Slippage je Trade = Fill-Preis −
    Arrival-Price (identische Formel zu BR-114 `trade_fill.slippage_abs`).
    Positiv heisst: der Fill war teurer/schlechter als der Kurs bei
    Signal-/Order-Auslösung (Kauf-Kontext); negativ heisst günstiger."""
    return fill_preis - arrival_price


def aggregiere_slippage(werte: Iterable[Decimal]) -> Decimal:
    """AC7: aggregiert mehrere je-Trade ermittelte Slippage-Werte zu einem
    TCA-Summenwert — gleiche Aggregations-Konvention wie
    `app.domain.portfolio.position_booking.aggregiere_gv` (AC2): Summe des
    Gesamteffekts über die betrachteten Trades."""
    return sum(werte, Decimal("0"))
