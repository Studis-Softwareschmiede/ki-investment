"""Tests für den Validierungs-Gate-Stufe-B-Berechnungskern
`app.domain.lernschleife.stage_b` (Story S-061).

Covers (lernschleife): AC8, AC9

- **AC8 (Probabilistic Sharpe Ratio):** `berechne_probabilistic_sharpe_ratio`-
  Tests belegen die Bailey/López-de-Prado-PSR-Formel (Vergleich mit einer
  manuell nachgerechneten Referenzimplementierung UND mit der DSR aus
  Stufe A bei `n_trials=1`, die formal identisch zur PSR gegen Benchmark 0
  ist), den Bestehen-Schwellenwert (95%, AC12) im vollen
  `bewerte_stufe_b`-Flow sowie die Fehlerfälle (zu wenige Renditen,
  Standardabweichung 0).
- **AC9 (MinTRL):** `berechne_min_trl_perioden`-Tests belegen die Formel
  gegen eine unabhängige Referenzimplementierung sowie die von der Spec
  genannten Richtwerte (Sharpe 1.0 ≈ 3 Jahre, Sharpe 0.5 ≈ 11 Jahre
  Monatsdaten, approximiert über eine Gauss-Quantil-Stichprobe mit
  Sample-Momenten nahe Skew 0/Kurtosis 3). `berechne_mintrl_restlaufzeit`-
  Tests belegen die Umrechnung in Kalenderzeit (inkl. „bereits erreicht"
  → 0) und den Fehlerfall Sharpe Ratio 0 (nicht bestimmbar).
  `bewerte_stufe_b`-Tests belegen, dass eine degenerierte
  Renditeverteilung NICHT abstürzt, sondern kontrolliert als nicht
  bestanden gewertet wird (analog der S-060-DSR-Robustheits-Konvention).
"""

from __future__ import annotations

import math
import statistics
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.contracts.lernschleife import StufeBKonfiguration, TradeErgebnis
from app.domain.lernschleife.stage_a import berechne_deflated_sharpe_ratio
from app.domain.lernschleife.stage_b import (
    berechne_min_trl_perioden,
    berechne_mintrl_restlaufzeit,
    berechne_probabilistic_sharpe_ratio,
    bewerte_stufe_b,
)

_START = datetime(2024, 1, 1, tzinfo=UTC)


def _trade(tag_offset: int, rendite: str) -> TradeErgebnis:
    return TradeErgebnis(datum=_START + timedelta(days=tag_offset), rendite_pct=Decimal(rendite))


def _trades(n: int, *, schritt_tage: int, rendite: str) -> list[TradeErgebnis]:
    return [_trade(i * schritt_tage, rendite) for i in range(n)]


def _stabile_trades_mit_streuung(
    n: int, *, schritt_tage: int, basis: float, streuung: float = 4.0
) -> list[TradeErgebnis]:
    """Trades mit alternierender Rendite um `basis` (±`streuung`) —
    Standardabweichung != 0, PSR/MinTRL sonst nicht definiert (analog
    `test_stage_a.py::_stabile_trades_mit_streuung`)."""
    return [
        _trade(i * schritt_tage, str(round(basis + (streuung if i % 2 == 0 else -streuung), 2)))
        for i in range(n)
    ]


def _gaussartige_renditen(n: int, *, mittelwert: float, std: float) -> list[Decimal]:
    """Erzeugt `n` Renditen über äquidistante Quantile einer Normalverteilung
    (Mittelwert/Std wie angegeben) — die Sample-Momente (Skew ≈ 0,
    Kurtosis ≈ 3) liegen für grosses `n` sehr nahe an den theoretischen
    Gauss-Werten, ohne echten Zufall (deterministisch, reproduzierbar) zu
    benötigen. Dient den Richtwerte-Golden-Tests (AC9)."""
    normal = statistics.NormalDist()
    return [Decimal(str(mittelwert + std * normal.inv_cdf((i + 0.5) / n))) for i in range(n)]


_BEISPIEL_RENDITEN = [Decimal(str(x)) for x in [1.2, 0.8, 1.5, -0.3, 0.9, 1.1, 0.4, 1.8, -0.6, 1.0]]


# --- AC8: Probabilistic Sharpe Ratio -------------------------------------------


def _manuelle_psr(renditen: list[float], benchmark_sr: float) -> float:
    """Unabhängig hingeschriebene Referenzimplementierung der PSR-Formel
    (Docstring von `berechne_probabilistic_sharpe_ratio`)."""
    t = len(renditen)
    mittelwert = statistics.fmean(renditen)
    s = statistics.stdev(renditen)
    sr_hat = mittelwert / s
    pop_s = statistics.pstdev(renditen)
    m3 = sum((x - mittelwert) ** 3 for x in renditen) / t
    m4 = sum((x - mittelwert) ** 4 for x in renditen) / t
    skew = m3 / pop_s**3
    kurt = m4 / pop_s**4
    nenner = 1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat**2
    normal = statistics.NormalDist()
    return normal.cdf((sr_hat - benchmark_sr) * math.sqrt(t - 1) / math.sqrt(nenner))


def test_berechne_probabilistic_sharpe_ratio_entspricht_der_referenzformel() -> None:
    """@trace lernschleife#AC8 — die Implementierung reproduziert exakt die
    im Docstring zitierte Bailey/López-de-Prado-PSR-Formel gegen
    Benchmark-Sharpe 0."""
    psr = berechne_probabilistic_sharpe_ratio(_BEISPIEL_RENDITEN)
    erwartet = _manuelle_psr([float(r) for r in _BEISPIEL_RENDITEN], benchmark_sr=0.0)

    assert float(psr) == pytest.approx(erwartet, abs=1e-9)


def test_berechne_probabilistic_sharpe_ratio_liegt_zwischen_0_und_1() -> None:
    """@trace lernschleife#AC8 — PSR ist eine Wahrscheinlichkeit (Φ-Wert)."""
    psr = berechne_probabilistic_sharpe_ratio(_BEISPIEL_RENDITEN)
    assert Decimal("0") <= psr <= Decimal("1")


def test_berechne_probabilistic_sharpe_ratio_entspricht_dsr_bei_einem_trial() -> None:
    """@trace lernschleife#AC8 — „im Unterschied zur DSR aus Stufe A": bei
    `n_trials=1` ist die DSR aus Stufe A (S-060, AC7) formal identisch zur
    PSR gegen Benchmark-Sharpe 0 (beide setzen SR_0 = 0) — Cross-Modul-
    Konsistenzprüfung zwischen `stage_a` und `stage_b`."""
    dsr_ein_trial = berechne_deflated_sharpe_ratio(_BEISPIEL_RENDITEN, n_trials=1)
    psr_benchmark_null = berechne_probabilistic_sharpe_ratio(
        _BEISPIEL_RENDITEN, benchmark_sr=Decimal("0")
    )

    assert dsr_ein_trial == psr_benchmark_null


def test_berechne_probabilistic_sharpe_ratio_sinkt_mit_hoeherem_benchmark() -> None:
    """@trace lernschleife#AC8 — ein höherer Benchmark (SR* > 0) senkt die
    Wahrscheinlichkeit, dass die Renditen ihn übertreffen."""
    psr_gegen_null = berechne_probabilistic_sharpe_ratio(
        _BEISPIEL_RENDITEN, benchmark_sr=Decimal("0")
    )
    psr_gegen_hoch = berechne_probabilistic_sharpe_ratio(
        _BEISPIEL_RENDITEN, benchmark_sr=Decimal("1")
    )

    assert psr_gegen_hoch < psr_gegen_null


def test_berechne_probabilistic_sharpe_ratio_wirft_bei_zu_wenig_renditen() -> None:
    """@trace lernschleife#AC8 — eine einzelne Rendite liefert keine
    Standardabweichung, PSR ist nicht definiert."""
    with pytest.raises(ValueError):
        berechne_probabilistic_sharpe_ratio([Decimal("1")])


def test_berechne_probabilistic_sharpe_ratio_wirft_bei_standardabweichung_null() -> None:
    """@trace lernschleife#AC8 — konstante Renditen (Std=0) machen die
    Sharpe Ratio nicht definiert."""
    with pytest.raises(ValueError):
        berechne_probabilistic_sharpe_ratio([Decimal("1"), Decimal("1"), Decimal("1")])


# --- AC9: MinTRL -----------------------------------------------------------------


def _manuelle_min_trl(renditen: list[float], konfidenz: float) -> float:
    """Unabhängig hingeschriebene Referenzimplementierung der MinTRL-Formel
    (Docstring von `berechne_min_trl_perioden`)."""
    t = len(renditen)
    mittelwert = statistics.fmean(renditen)
    s = statistics.stdev(renditen)
    sr_hat = mittelwert / s
    pop_s = statistics.pstdev(renditen)
    m3 = sum((x - mittelwert) ** 3 for x in renditen) / t
    m4 = sum((x - mittelwert) ** 4 for x in renditen) / t
    skew = m3 / pop_s**3
    kurt = m4 / pop_s**4
    nenner = 1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat**2
    z = statistics.NormalDist().inv_cdf(konfidenz)
    return 1 + nenner * (z / sr_hat) ** 2


def test_berechne_min_trl_perioden_entspricht_der_referenzformel() -> None:
    """@trace lernschleife#AC9 — die Implementierung reproduziert exakt die
    im Docstring zitierte Bailey/López-de-Prado-MinTRL-Formel."""
    min_trl = berechne_min_trl_perioden(_BEISPIEL_RENDITEN)
    erwartet = _manuelle_min_trl([float(r) for r in _BEISPIEL_RENDITEN], konfidenz=0.95)

    assert float(min_trl) == pytest.approx(erwartet, abs=1e-9)


def test_berechne_min_trl_perioden_richtwert_sharpe_eins_ungefaehr_drei_jahre() -> None:
    """@trace lernschleife#AC9 — Spec-Richtwert: „Sharpe 1.0 ≈ 3 Jahre
    Monatsdaten". Monatlicher Sharpe = 1.0/sqrt(12); Golden-Value-Test
    gegen eine Gauss-Quantil-Stichprobe (Sample-Momente nahe Skew 0/
    Kurtosis 3, siehe `_gaussartige_renditen`)."""
    monats_sharpe = 1.0 / math.sqrt(12)
    renditen = _gaussartige_renditen(2000, mittelwert=monats_sharpe, std=1.0)

    min_trl_monate = berechne_min_trl_perioden(renditen)
    jahre = float(min_trl_monate) / 12

    assert jahre == pytest.approx(3.0, rel=0.25)


def test_berechne_min_trl_perioden_richtwert_sharpe_halb_ungefaehr_elf_jahre() -> None:
    """@trace lernschleife#AC9 — Spec-Richtwert: „Sharpe 0.5 ≈ 11 Jahre
    Monatsdaten"."""
    monats_sharpe = 0.5 / math.sqrt(12)
    renditen = _gaussartige_renditen(2000, mittelwert=monats_sharpe, std=1.0)

    min_trl_monate = berechne_min_trl_perioden(renditen)
    jahre = float(min_trl_monate) / 12

    assert jahre == pytest.approx(11.0, rel=0.25)


def test_berechne_min_trl_perioden_wirft_bei_sharpe_ratio_null() -> None:
    """@trace lernschleife#AC9 — Sharpe Ratio exakt 0 (Mittelwert 0) macht
    MinTRL nicht definiert (Division durch 0 in der Formel)."""
    renditen = [Decimal("1"), Decimal("-1"), Decimal("1"), Decimal("-1")]
    with pytest.raises(ValueError):
        berechne_min_trl_perioden(renditen)


def test_berechne_min_trl_perioden_wirft_bei_zu_wenig_renditen() -> None:
    """@trace lernschleife#AC9 — < 2 Renditen liefern keine
    Standardabweichung."""
    with pytest.raises(ValueError):
        berechne_min_trl_perioden([Decimal("1")])


# --- AC9: MinTRL-Restlaufzeit ------------------------------------------------


def test_berechne_mintrl_restlaufzeit_liefert_positive_restlaufzeit_bei_zu_kurzer_historie() -> (
    None
):
    """@trace lernschleife#AC9 — „die verbleibende Zeit": bei einer noch zu
    kurzen Paper-Historie liefert die Restlaufzeit eine positive
    Zeitspanne (grösser 0)."""
    monats_sharpe = 0.5 / math.sqrt(12)
    trades = _stabile_trades_mit_streuung(20, schritt_tage=30, basis=monats_sharpe, streuung=1.0)

    restlaufzeit = berechne_mintrl_restlaufzeit(trades)

    assert restlaufzeit > timedelta(0)


def test_berechne_mintrl_restlaufzeit_null_wenn_min_trl_bereits_erreicht() -> None:
    """@trace lernschleife#AC9 — ist die Stichprobe bereits mindestens so
    lang wie MinTRL verlangt, ist die Restlaufzeit 0 (kein negativer
    Wert)."""
    trades = _stabile_trades_mit_streuung(300, schritt_tage=1, basis=5.0, streuung=0.5)

    restlaufzeit = berechne_mintrl_restlaufzeit(trades)

    assert restlaufzeit == timedelta(0)


def test_berechne_mintrl_restlaufzeit_wirft_bei_sharpe_ratio_null() -> None:
    """@trace lernschleife#AC9 — degenerierte Eingaben propagieren aus
    `berechne_min_trl_perioden` (Sharpe Ratio 0 nicht bestimmbar)."""
    trades = [
        _trade(0, "1"),
        _trade(1, "-1"),
        _trade(2, "1"),
        _trade(3, "-1"),
    ]
    with pytest.raises(ValueError):
        berechne_mintrl_restlaufzeit(trades)


# --- bewerte_stufe_b: voller Flow ------------------------------------------------


def test_bewerte_stufe_b_besteht_bei_hoher_psr() -> None:
    """@trace lernschleife#AC8 — stabile, deutlich positive Renditen mit
    grosser Stichprobe bestehen die 95%-PSR-Schwelle."""
    trades = _stabile_trades_mit_streuung(200, schritt_tage=1, basis=5.0, streuung=0.5)

    report = bewerte_stufe_b(trades, hypothesis_id=uuid.uuid4())

    assert report.psr is not None
    assert report.psr_bestanden is True
    assert report.psr >= report.psr_schwelle


def test_bewerte_stufe_b_besteht_nicht_bei_niedriger_psr() -> None:
    """@trace lernschleife#AC8 — eine kleine, verrauschte Stichprobe ohne
    klaren positiven Edge unterschreitet die 95%-PSR-Schwelle."""
    trades = _stabile_trades_mit_streuung(5, schritt_tage=1, basis=0.1, streuung=4.0)

    report = bewerte_stufe_b(trades, hypothesis_id=uuid.uuid4())

    assert report.psr is not None
    assert report.psr_bestanden is False
    assert report.psr < report.psr_schwelle


def test_bewerte_stufe_b_konstante_renditen_faellt_durch_statt_zu_crashen() -> None:
    """@trace lernschleife#AC8 — degenerierte Renditeverteilung
    (Standardabweichung 0) darf `bewerte_stufe_b` NICHT mit ValueError
    abstürzen lassen (S-060-DSR-Robustheits-Konvention), sondern muss ein
    kontrolliertes 'nicht bestanden'-Urteil liefern."""
    trades = _trades(50, schritt_tage=1, rendite="2.0")

    report = bewerte_stufe_b(trades, hypothesis_id=uuid.uuid4())

    assert report.n_trades == 50
    assert report.psr is None
    assert report.psr_bestanden is False
    assert report.mintrl_restlaufzeit is None


def test_bewerte_stufe_b_respektiert_konfigurierte_psr_schwelle() -> None:
    """@trace lernschleife#AC12 (i.V.m. AC8) — die PSR-Schwelle ist
    konfigurierbar; eine niedrigere Schwelle lässt dieselbe Stichprobe
    bestehen, die gegen den Default (95%) nicht bestanden hätte."""
    trades = _stabile_trades_mit_streuung(5, schritt_tage=1, basis=0.1, streuung=4.0)

    report_default = bewerte_stufe_b(trades, hypothesis_id=uuid.uuid4())
    report_niedrig = bewerte_stufe_b(
        trades,
        hypothesis_id=uuid.uuid4(),
        konfiguration=StufeBKonfiguration(psr_schwelle=Decimal("0.01")),
    )

    assert report_default.psr_bestanden is False
    assert report_niedrig.psr_bestanden is True
