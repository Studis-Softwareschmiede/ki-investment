"""Interne statistische Bausteine, geteilt zwischen Stufe A (Deflated Sharpe
Ratio, S-060, AC7) und Stufe B (Probabilistic Sharpe Ratio/MinTRL, S-061,
AC8/AC9) — alle drei Kennzahlen beruhen auf derselben Bailey/López-de-Prado-
Stichprobenkennzahl (Sharpe Ratio + Schiefe/Wölbung-Korrekturterm).

Reiner Domain-Kern (architecture.md §4 P1): keine I/O, keine DB. Dieses
Modul ist bewusst KEIN öffentlicher Modul-Vertrag (Unterstrich-Präfix im
Dateinamen) — es ist ausschliesslich für `stage_a`/`stage_b` innerhalb
dieses Pakets gedacht, kein `app/contracts/`-DTO-Übergang zwischen
Paketen (P2 gilt für Modul-*Paket*-Grenzen, nicht für private Helfer
innerhalb desselben Pakets).
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

#: Euler-Mascheroni-Konstante γ (DSR-Formel, AC7) — hier zentral, da auch
#: für eine künftige PSR-Erweiterung mit Trial-Korrektur relevant sein
#: könnte; aktuell nur von stage_a genutzt.
EULER_MASCHERONI = 0.5772156649015329


@dataclass(frozen=True)
class Stichprobenkennzahlen:
    """Ergebnis von `berechne_stichprobenkennzahlen`: Stichprobengrösse,
    Stichproben-Sharpe-Ratio (ddof=1) und der Schiefe/Wölbung-
    Korrekturterm, der DSR (AC7), PSR (AC8) und MinTRL (AC9) gemeinsam
    zugrunde liegt."""

    t: int
    sr_hat: float
    skew: float
    kurt: float
    nenner_term: float


def _skewness(werte: Sequence[float], mittelwert: float, populations_std: float) -> float:
    n = len(werte)
    if populations_std == 0:
        return 0.0
    m3 = sum((x - mittelwert) ** 3 for x in werte) / n
    return m3 / populations_std**3


def _kurtosis(werte: Sequence[float], mittelwert: float, populations_std: float) -> float:
    n = len(werte)
    if populations_std == 0:
        return 3.0  # Normalverteilungs-Kurtosis (keine Wölbungs-Korrektur)
    m4 = sum((x - mittelwert) ** 4 for x in werte) / n
    return m4 / populations_std**4


def berechne_stichprobenkennzahlen(renditen: Sequence[Decimal]) -> Stichprobenkennzahlen:
    """Gemeinsamer Kern für DSR (AC7)/PSR (AC8)/MinTRL (AC9): Stichproben-
    Sharpe-Ratio (`sr_hat`, ddof=1, Sharpe-Ratio-Konvention) + Schiefe/
    Wölbung-Korrekturterm (`nenner_term`) nach Bailey/López de Prado.

    Wirft `ValueError` bei degenerierten Eingaben (< 2 Renditen,
    Standardabweichung 0, extreme Schiefe/Wölbung mit nicht-positivem
    Varianzterm) — der jeweilige Aufrufer (stage_a/stage_b-Orchestrator)
    fängt diese Exception und wertet kontrolliert statt abzustürzen
    (S-060-DSR-Robustheits-Konvention, siehe `stage_a.bewerte_stufe_a`)."""
    werte = [float(r) for r in renditen]
    t = len(werte)
    if t < 2:
        raise ValueError("mindestens 2 Renditen erforderlich")

    mittelwert = statistics.fmean(werte)
    stichproben_std = statistics.stdev(werte)  # ddof=1, Sharpe-Ratio-Konvention
    if stichproben_std == 0:
        raise ValueError("Standardabweichung 0 — Sharpe Ratio nicht definiert")
    sr_hat = mittelwert / stichproben_std

    populations_std = statistics.pstdev(werte)  # ddof=0, für Schiefe/Kurtosis
    skew = _skewness(werte, mittelwert, populations_std)
    kurt = _kurtosis(werte, mittelwert, populations_std)

    nenner_term = 1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat**2
    if nenner_term <= 0:
        raise ValueError("Varianzterm nicht positiv (extreme Schiefe/Wölbung)")

    return Stichprobenkennzahlen(t=t, sr_hat=sr_hat, skew=skew, kurt=kurt, nenner_term=nenner_term)


__all__ = ["EULER_MASCHERONI", "Stichprobenkennzahlen", "berechne_stichprobenkennzahlen"]
