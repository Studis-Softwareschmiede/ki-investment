"""Validierungs-Gate Stufe B (Paper-Bewährung) — Berechnungskern (S-061,
Spec `docs/specs/lernschleife.md` AC8/AC9).

Reiner Domain-Kern (architecture.md §4 P1): keine I/O, keine DB, kein
LLM. Wer die Paper-Trades aus dem Simuliert-Modus (`[[kauf-verkauf]]`,
S-046..S-049) beschafft, ist Sache des Aufrufers (Orchestration-Schicht)
— dieses Modul konsumiert nur bereits aufbereitete `TradeErgebnis`-Listen
(derselbe Vertrag wie Stufe A, S-060).

- **AC8 (Probabilistic Sharpe Ratio, PSR):**
  `berechne_probabilistic_sharpe_ratio` berechnet die PSR der Renditen
  GEGEN BENCHMARK-SHARPE 0 (im Unterschied zur DSR aus Stufe A, AC7, die
  gegen die aus `n_trials` erwartete MAXIMALE Sharpe Ratio unter
  Mehrfach-Test-Korrektur testet — PSR hier ist der Bailey/López-de-Prado-
  Sonderfall ohne Trial-Korrektur, `SR_0 = benchmark_sr`). Nutzt denselben
  statistischen Kern (`app.domain.lernschleife._statistik`,
  Stichproben-Sharpe-Ratio + Schiefe/Wölbung-Korrekturterm) wie die DSR
  aus S-060. Stufe B besteht bei PSR >= 95% (Default-Schwelle,
  `StufeBKonfiguration.psr_schwelle`, AC12).
- **AC9 (Minimum Track Record Length, MinTRL):**
  `berechne_min_trl_perioden` liefert die Bailey/López-de-Prado-MinTRL in
  Anzahl Perioden (Beobachtungen); `berechne_mintrl_restlaufzeit`
  übersetzt das in eine verbleibende Kalenderzeit (Restlaufzeit) über das
  durchschnittliche Handelsintervall der vorliegenden Trades — 0, wenn
  MinTRL bereits erreicht/überschritten ist. Reine Berechnung/Anzeige,
  KEIN eigenes Gate-Kriterium (die Spec verlangt für AC9 nur "wird
  berechnet und angezeigt", kein Schwellenwert).
- **Robustheit (S-060-DSR-Konvention):** degenerierte Renditeverteilungen
  (< 2 Trades, Standardabweichung 0, Sharpe Ratio 0) lassen die
  Low-Level-Formeln `ValueError` werfen — `bewerte_stufe_b` fängt das ab
  und liefert ein kontrolliertes Urteil (`psr`/`mintrl_restlaufzeit` =
  `None`, `psr_bestanden` = `False`, `begruendung`), statt abzustürzen.

`bewerte_stufe_b` verdrahtet PSR + MinTRL-Restlaufzeit zum vollen
`StufeBReport`.
"""

from __future__ import annotations

import statistics
import uuid
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

from app.contracts.lernschleife import StufeBKonfiguration, StufeBReport, TradeErgebnis
from app.domain.lernschleife._statistik import berechne_stichprobenkennzahlen


def berechne_probabilistic_sharpe_ratio(
    renditen: Sequence[Decimal], *, benchmark_sr: Decimal = Decimal("0")
) -> Decimal:
    """AC8 — Probabilistic Sharpe Ratio (Bailey & López de Prado): die
    Wahrscheinlichkeit, dass die WAHRE Sharpe Ratio der Renditen über
    `benchmark_sr` liegt (Default 0, wie von AC8 gefordert — "gegen
    Benchmark-Sharpe 0"). Formal identisch zur DSR-Formel aus Stufe A
    (`stage_a.berechne_deflated_sharpe_ratio`), aber mit `SR_0 =
    benchmark_sr` statt einer aus `n_trials` abgeleiteten
    Mehrfach-Test-Korrektur:

        PSR = Φ[(SR_hat - benchmark_sr)·sqrt(T-1)
                / sqrt(1 - γ3·SR_hat + (γ4-1)/4·SR_hat²)]

    Wirft `ValueError` bei degenerierten Eingaben (< 2 Renditen,
    Standardabweichung 0, nicht-positiver Varianzterm) — der Aufrufer
    (`bewerte_stufe_b`) fängt das kontrolliert ab (S-060-Konvention)."""
    kennzahlen = berechne_stichprobenkennzahlen(renditen)
    normal = statistics.NormalDist()
    psr = normal.cdf(
        (kennzahlen.sr_hat - float(benchmark_sr))
        * (kennzahlen.t - 1) ** 0.5
        / kennzahlen.nenner_term**0.5
    )
    return Decimal(str(psr))


def berechne_min_trl_perioden(
    renditen: Sequence[Decimal], *, konfidenz: Decimal = Decimal("0.95")
) -> Decimal:
    """AC9 — Minimum Track Record Length (Bailey & López de Prado) in
    Anzahl Perioden (Beobachtungen): die Mindestanzahl an Renditen, ab
    der die Sharpe Ratio beim gegebenen `konfidenz`-Niveau (Default 95%,
    einseitig) von Benchmark 0 statistisch unterscheidbar ist:

        MinTRL = 1 + [1 - γ3·SR_hat + (γ4-1)/4·SR_hat²] · (Z_α / SR_hat)²

    (Z_α = Φ⁻¹(konfidenz), derselbe Schiefe/Wölbung-Korrekturterm wie bei
    DSR/PSR.) Wirft `ValueError` bei degenerierten Eingaben — inklusive
    Sharpe Ratio exakt 0 (Division durch 0: bei Sharpe 0 ist die
    Renditequalität nie von Null unterscheidbar, MinTRL wäre unendlich)."""
    kennzahlen = berechne_stichprobenkennzahlen(renditen)
    if kennzahlen.sr_hat == 0:
        raise ValueError("MinTRL bei Sharpe Ratio 0 nicht definiert (unendliche Beobachtungsdauer)")

    z_alpha = statistics.NormalDist().inv_cdf(float(konfidenz))
    min_trl = 1 + kennzahlen.nenner_term * (z_alpha / kennzahlen.sr_hat) ** 2
    return Decimal(str(min_trl))


def berechne_mintrl_restlaufzeit(
    trades: Sequence[TradeErgebnis], *, konfidenz: Decimal = Decimal("0.95")
) -> timedelta:
    """AC9 — "die verbleibende Zeit, bis das Ergebnis beim aktuellen
    Sharpe mit 95% Konfidenz von Null unterscheidbar ist": MinTRL in
    Perioden (`berechne_min_trl_perioden`) minus bereits beobachtete
    Perioden (`len(trades)`), umgerechnet in Kalenderzeit über das
    durchschnittliche Handelsintervall der chronologisch sortierten
    `trades`. Liefert `timedelta(0)`, wenn MinTRL bereits
    erreicht/überschritten ist.

    Wirft `ValueError`, wenn `berechne_min_trl_perioden` das tut
    (degenerierte Renditeverteilung) — der Aufrufer (`bewerte_stufe_b`)
    fängt das kontrolliert ab."""
    renditen = [t.rendite_pct for t in trades]
    min_trl_perioden = berechne_min_trl_perioden(renditen, konfidenz=konfidenz)

    n = len(trades)
    fehlende_perioden = min_trl_perioden - n
    if fehlende_perioden <= 0:
        return timedelta(0)

    sortiert = sorted(trades, key=lambda t: t.datum)
    gesamt_spanne = sortiert[-1].datum - sortiert[0].datum
    durchschnitts_intervall = gesamt_spanne / (n - 1)

    return durchschnitts_intervall * float(fehlende_perioden)


def bewerte_stufe_b(
    trades: Sequence[TradeErgebnis],
    *,
    hypothesis_id: uuid.UUID,
    konfiguration: StufeBKonfiguration | None = None,
) -> StufeBReport:
    """Orchestriert AC8 (PSR) + AC9 (MinTRL-Restlaufzeit) zum vollen
    `StufeBReport` (Main Success Scenario Schritt 5: "PSR und laufende
    MinTRL werden berechnet und angezeigt"). Degenerierte
    Renditeverteilungen crashen NICHT (S-060-DSR-Robustheits-Konvention),
    sondern liefern ein kontrolliertes Urteil (`psr`/
    `mintrl_restlaufzeit` = `None`, `psr_bestanden` = `False`)."""
    konfiguration = konfiguration or StufeBKonfiguration()
    n_trades = len(trades)
    renditen = [t.rendite_pct for t in trades]

    try:
        psr = berechne_probabilistic_sharpe_ratio(renditen)
    except ValueError as exc:
        return StufeBReport(
            hypothesis_id=hypothesis_id,
            n_trades=n_trades,
            psr=None,
            psr_schwelle=konfiguration.psr_schwelle,
            psr_bestanden=False,
            mintrl_restlaufzeit=None,
            begruendung=(
                f"Probabilistic Sharpe Ratio nicht berechenbar ({exc}) — "
                "degenerierte Renditeverteilung, Stufe B nicht bestanden (AC8)."
            ),
        )

    try:
        restlaufzeit = berechne_mintrl_restlaufzeit(trades)
    except ValueError:
        # MinTRL selbst ist nicht als Gate-Kriterium spezifiziert (AC9
        # verlangt nur "berechnet und angezeigt") — eine nicht bestimmbare
        # Restlaufzeit (z.B. Sharpe Ratio exakt 0) blockiert daher NICHT
        # das PSR-Urteil, sondern bleibt schlicht unbestimmt (`None`).
        restlaufzeit = None

    psr_bestanden = psr >= konfiguration.psr_schwelle
    begruendung = (
        f"PSR {psr} {'>=' if psr_bestanden else '<'} Schwelle {konfiguration.psr_schwelle} "
        f"— Stufe B {'bestanden' if psr_bestanden else 'nicht bestanden'} (AC8)."
    )

    return StufeBReport(
        hypothesis_id=hypothesis_id,
        n_trades=n_trades,
        psr=psr,
        psr_schwelle=konfiguration.psr_schwelle,
        psr_bestanden=psr_bestanden,
        mintrl_restlaufzeit=restlaufzeit,
        begruendung=begruendung,
    )


__all__ = [
    "berechne_probabilistic_sharpe_ratio",
    "berechne_min_trl_perioden",
    "berechne_mintrl_restlaufzeit",
    "bewerte_stufe_b",
]
