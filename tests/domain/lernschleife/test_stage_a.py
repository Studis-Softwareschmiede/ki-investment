"""Tests für den Validierungs-Gate-Stufe-A-Berechnungskern
`app.domain.lernschleife.stage_a` (Story S-060).

Covers (lernschleife): AC4, AC5, AC6, AC7

- **AC4 (Mindest-Stichprobe, deckt A3):** `pruefe_mindeststichprobe`-Tests
  belegen die drei Stichproben-Zonen (< 30 nicht bewertet, 30–99
  durchgefallen, >= 100 ausreichend, siehe Spec-Präzisierung
  `docs/specs/lernschleife.md` AC4); `bewerte_stufe_a`-Tests belegen
  dieselben Zonen End-to-End (inkl. „kein DSR/WFE bei zu kleiner
  Stichprobe").
- **AC5 (Walk-Forward mit Embargo):** `erzeuge_walk_forward_splits`-Tests
  belegen die Embargo-Purge (Trades im 30-Tage-Puffer vor dem
  Validierungsfenster fallen aus dem Trainingsfenster), dass mindestens
  zwei sequentielle Splits gebildet werden (nicht nur einer), und dass zu
  wenige/zu eng beieinanderliegende Trades zu keinen (statt fehlerhaften)
  Splits führen.
- **AC6 (Walk-Forward-Effizienz):** `berechne_walk_forward_effizienz`-Tests
  belegen die gepoolte Pro-Trade-Durchschnittsrendite über alle Splits
  (nicht nur einen) sowie die Overfit-Verdacht-Ablehnung bei sinkender
  Out-of-Sample-Performance im vollen `bewerte_stufe_a`-Flow.
- **AC7 (Deflated Sharpe Ratio):** `berechne_deflated_sharpe_ratio`-Tests
  belegen die Bailey/López-de-Prado-Formel (Vergleich mit einer manuell
  nachgerechneten Referenzimplementierung), die Korrektur um `n_trials`
  aus der Trial-Registry (DSR sinkt mit mehr getesteten Varianten) sowie
  die Fehlerfälle (zu wenige Renditen, Standardabweichung 0, `n_trials`
  < 1).
"""

from __future__ import annotations

import math
import statistics
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.contracts.lernschleife import StufeAKonfiguration, TradeErgebnis, WalkForwardSplitErgebnis
from app.domain.lernschleife.stage_a import (
    berechne_deflated_sharpe_ratio,
    berechne_walk_forward_effizienz,
    bewerte_stufe_a,
    erzeuge_walk_forward_splits,
    pruefe_mindeststichprobe,
)

_START = datetime(2024, 1, 1, tzinfo=UTC)


def _trade(tag_offset: int, rendite: str) -> TradeErgebnis:
    return TradeErgebnis(datum=_START + timedelta(days=tag_offset), rendite_pct=Decimal(rendite))


def _trades(n: int, *, schritt_tage: int, rendite: str) -> list[TradeErgebnis]:
    return [_trade(i * schritt_tage, rendite) for i in range(n)]


def _stabile_trades_mit_streuung(
    n: int, *, schritt_tage: int, basis: float, streuung: float = 4.0
) -> list[TradeErgebnis]:
    """Trades mit alternierender Rendite um `basis` (±`streuung`) — stabile
    Performance (kein Trend zwischen früh/spät), aber Standardabweichung
    != 0 (DSR sonst nicht definiert, siehe
    `berechne_deflated_sharpe_ratio`-Fehlerfall Std=0). `streuung` bewusst
    deutlich > 0 gewählt: bei sehr niedriger Streuung sättigt die DSR bei
    grossen Stichproben (T=150) nahe 1.0 (Sharpe-Ratio-Z-Statistik skaliert
    mit sqrt(T-1)) und wird dadurch unempfindlich gegenüber `n_trials` —
    das würde den AC7-Effekt (DSR sinkt mit mehr Trials) verdecken, nicht
    widerlegen."""
    return [
        _trade(i * schritt_tage, str(round(basis + (streuung if i % 2 == 0 else -streuung), 2)))
        for i in range(n)
    ]


# --- AC4: Mindest-Stichprobe --------------------------------------------------


@pytest.mark.parametrize(
    ("n_trades", "erwartet"),
    [
        (0, "nicht_bewertet"),
        (29, "nicht_bewertet"),
        (30, "durchgefallen_kleine_stichprobe"),
        (99, "durchgefallen_kleine_stichprobe"),
        (100, "ausreichend"),
        (250, "ausreichend"),
    ],
)
def test_pruefe_mindeststichprobe_ordnet_die_drei_zonen_korrekt_zu(
    n_trades: int, erwartet: str
) -> None:
    """@trace lernschleife#AC4 — < 30 nicht bewertet (A3), 30-99
    durchgefallen (Präzisierung), >= 100 ausreichend (volle Bewertung)."""
    ergebnis = pruefe_mindeststichprobe(n_trades, konfiguration=StufeAKonfiguration())
    assert ergebnis == erwartet


def test_pruefe_mindeststichprobe_respektiert_konfigurierte_schwellen() -> None:
    """@trace lernschleife#AC4,AC12 — Schwellen sind konfigurierbar, nicht
    hartkodiert."""
    konfiguration = StufeAKonfiguration(mindest_stichprobe=50, bewertungsuntergrenze=10)

    assert pruefe_mindeststichprobe(9, konfiguration=konfiguration) == "nicht_bewertet"
    assert (
        pruefe_mindeststichprobe(49, konfiguration=konfiguration)
        == "durchgefallen_kleine_stichprobe"
    )
    assert pruefe_mindeststichprobe(50, konfiguration=konfiguration) == "ausreichend"


# --- AC5: Walk-Forward mit Embargo --------------------------------------------


def test_erzeuge_walk_forward_splits_liefert_leere_liste_bei_zu_wenig_trades() -> None:
    """@trace lernschleife#AC5 — ein einzelner Trade kann kein
    Trainings-/Validierungsfenster bilden."""
    assert erzeuge_walk_forward_splits([_trade(0, "1")], embargo_tage=30) == []


def test_erzeuge_walk_forward_splits_purged_trades_innerhalb_des_embargo_puffers() -> None:
    """@trace lernschleife#AC5 — Trades, die weniger als `embargo_tage` vor
    dem Start des Validierungsfensters liegen, fallen aus dem
    Trainingsfenster (Datenleckage-Schutz)."""
    # Gruppe 0 (Training-Kandidaten): Tag 0..9. Gruppe 1 (Validierung): Tag 35..44.
    trades = _trades(10, schritt_tage=1, rendite="1") + [_trade(35 + i, "2") for i in range(10)]

    splits = erzeuge_walk_forward_splits(trades, embargo_tage=30, n_splits=1)

    assert len(splits) == 1
    split = splits[0]
    # embargo_grenze = Tag 35 - 30 = Tag 5 -> nur Tage 0..5 (6 Trades) bleiben im Training.
    assert split.n_trades_train == 6
    assert split.n_trades_validierung == 10


def test_erzeuge_walk_forward_splits_liefert_leere_liste_wenn_embargo_alles_aufzehrt() -> None:
    """@trace lernschleife#AC5 — frisst das Embargo das gesamte
    Trainingsfenster auf, entsteht kein Split (statt eines falschen
    Ergebnisses mit leerem Trainingsfenster)."""
    trades = _trades(10, schritt_tage=1, rendite="1") + [_trade(15 + i, "2") for i in range(10)]

    splits = erzeuge_walk_forward_splits(trades, embargo_tage=30, n_splits=1)

    assert splits == []


def test_erzeuge_walk_forward_splits_deckt_mehrere_sequentielle_splits_ab() -> None:
    """@trace lernschleife#AC5 — „über alle sequentiellen Splits geprüft,
    nicht nur über einen": bei ausreichend zeitlichem Abstand entstehen
    mehrere Splits, jeweils mit wachsendem Trainingsfenster (anchored)."""
    trades = _trades(150, schritt_tage=5, rendite="1")  # Spanne ~745 Tage

    splits = erzeuge_walk_forward_splits(trades, embargo_tage=30, n_splits=5)

    assert len(splits) >= 2
    for a, b in zip(splits, splits[1:], strict=False):
        assert a.split_index < b.split_index
        assert a.n_trades_train < b.n_trades_train  # anchored: Trainingsfenster wächst
        assert a.validierung_bis < b.validierung_von


# --- AC6: Walk-Forward-Effizienz ----------------------------------------------


def test_berechne_walk_forward_effizienz_ist_pro_trade_durchschnitt_gepoolt() -> None:
    """@trace lernschleife#AC6 — Verhältnis der gepoolten Pro-Trade-
    Durchschnittsrenditen (OOS/IS) über alle Splits, nicht die reine
    Summe (die das wachsende Trainingsfenster verzerren würde)."""
    jetzt = datetime(2024, 1, 1, tzinfo=UTC)
    splits = [
        WalkForwardSplitErgebnis(
            split_index=0,
            train_von=jetzt,
            train_bis=jetzt,
            validierung_von=jetzt,
            validierung_bis=jetzt,
            n_trades_train=10,
            n_trades_validierung=10,
            is_rendite=Decimal("20"),  # Ø 2 pro Trade
            oos_rendite=Decimal("10"),  # Ø 1 pro Trade
        ),
        WalkForwardSplitErgebnis(
            split_index=1,
            train_von=jetzt,
            train_bis=jetzt,
            validierung_von=jetzt,
            validierung_bis=jetzt,
            n_trades_train=10,
            n_trades_validierung=10,
            is_rendite=Decimal("20"),  # Ø 2 pro Trade
            oos_rendite=Decimal("10"),  # Ø 1 pro Trade
        ),
    ]

    wfe = berechne_walk_forward_effizienz(splits)

    assert wfe == Decimal("0.5")


def test_berechne_walk_forward_effizienz_liefert_none_ohne_splits() -> None:
    """@trace lernschleife#AC6 — keine Splits, keine sinnvolle Kennzahl."""
    assert berechne_walk_forward_effizienz([]) is None


def test_berechne_walk_forward_effizienz_liefert_none_bei_nicht_positiver_is_rendite() -> None:
    """@trace lernschleife#AC6 — eine nicht-positive gepoolte
    In-Sample-Rendite macht das Verhältnis "OOS >= Hälfte IS" bedeutungslos."""
    jetzt = datetime(2024, 1, 1, tzinfo=UTC)
    splits = [
        WalkForwardSplitErgebnis(
            split_index=0,
            train_von=jetzt,
            train_bis=jetzt,
            validierung_von=jetzt,
            validierung_bis=jetzt,
            n_trades_train=10,
            n_trades_validierung=10,
            is_rendite=Decimal("-5"),
            oos_rendite=Decimal("10"),
        )
    ]

    assert berechne_walk_forward_effizienz(splits) is None


# --- AC7: Deflated Sharpe Ratio ------------------------------------------------


def _manuelle_dsr(renditen: list[float], n_trials: int) -> float:
    """Unabhängig hingeschriebene Referenzimplementierung der Bailey/López-
    de-Prado-Formel (Docstring von `berechne_deflated_sharpe_ratio`) — dient
    dem Abgleich, dass die Produktivfunktion exakt dieselbe Formel
    verdrahtet."""
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
    gamma = 0.5772156649015329
    if n_trials <= 1:
        sr0 = 0.0
    else:
        varianz = nenner / (t - 1)
        sr0 = math.sqrt(varianz) * (
            (1 - gamma) * normal.inv_cdf(1 - 1 / n_trials)
            + gamma * normal.inv_cdf(1 - 1 / (n_trials * math.e))
        )
    return normal.cdf((sr_hat - sr0) * math.sqrt(t - 1) / math.sqrt(nenner))


_BEISPIEL_RENDITEN = [Decimal(str(x)) for x in [1.2, 0.8, 1.5, -0.3, 0.9, 1.1, 0.4, 1.8, -0.6, 1.0]]


def test_berechne_deflated_sharpe_ratio_entspricht_der_referenzformel() -> None:
    """@trace lernschleife#AC7 — die Implementierung reproduziert exakt die
    im Docstring zitierte Bailey/López-de-Prado-DSR-Formel."""
    dsr = berechne_deflated_sharpe_ratio(_BEISPIEL_RENDITEN, n_trials=20)
    erwartet = _manuelle_dsr([float(r) for r in _BEISPIEL_RENDITEN], n_trials=20)

    assert float(dsr) == pytest.approx(erwartet, abs=1e-9)


def test_berechne_deflated_sharpe_ratio_liegt_zwischen_0_und_1() -> None:
    """@trace lernschleife#AC7 — DSR ist eine Wahrscheinlichkeit (Φ-Wert)."""
    dsr = berechne_deflated_sharpe_ratio(_BEISPIEL_RENDITEN, n_trials=5)
    assert Decimal("0") <= dsr <= Decimal("1")


def test_berechne_deflated_sharpe_ratio_sinkt_mit_steigender_trial_anzahl() -> None:
    """@trace lernschleife#AC7 — „korrigiert um die aus der Trial-Registry
    bekannte Anzahl aller getesteten Regelvarianten": mehr getestete
    Varianten (Mehrfach-Test-Bias) senken die DSR bei identischen
    Renditen."""
    dsr_wenige = berechne_deflated_sharpe_ratio(_BEISPIEL_RENDITEN, n_trials=1)
    dsr_viele = berechne_deflated_sharpe_ratio(_BEISPIEL_RENDITEN, n_trials=500)

    assert dsr_viele < dsr_wenige


def test_berechne_deflated_sharpe_ratio_wirft_bei_zu_wenig_renditen() -> None:
    """@trace lernschleife#AC7 — eine einzelne Rendite liefert keine
    Standardabweichung, DSR ist nicht definiert."""
    with pytest.raises(ValueError):
        berechne_deflated_sharpe_ratio([Decimal("1")], n_trials=10)


def test_berechne_deflated_sharpe_ratio_wirft_bei_standardabweichung_null() -> None:
    """@trace lernschleife#AC7 — konstante Renditen (Std=0) machen die
    Sharpe Ratio nicht definiert."""
    with pytest.raises(ValueError):
        berechne_deflated_sharpe_ratio([Decimal("1"), Decimal("1"), Decimal("1")], n_trials=10)


def test_berechne_deflated_sharpe_ratio_wirft_bei_n_trials_unter_1() -> None:
    """@trace lernschleife#AC7 — die Trial-Registry zählt jede Variante
    (AC3); 0 Trials ist ein Programmierfehler-Symptom (Variante wurde nie
    registriert)."""
    with pytest.raises(ValueError):
        berechne_deflated_sharpe_ratio(_BEISPIEL_RENDITEN, n_trials=0)


# --- Voller Flow: bewerte_stufe_a ---------------------------------------------


def test_bewerte_stufe_a_liefert_nicht_bewertet_unter_bewertungsuntergrenze() -> None:
    """@trace lernschleife#AC4 — unter 30 Trades: kein Urteil, kein
    WFE/DSR berechnet (A3)."""
    report = bewerte_stufe_a(
        _trades(10, schritt_tage=5, rendite="1"),
        hypothesis_id=uuid.uuid4(),
        n_trials=1,
    )

    assert report.ergebnis == "nicht_bewertet"
    assert report.n_trades == 10
    assert report.walk_forward_effizienz is None
    assert report.dsr is None


def test_bewerte_stufe_a_liefert_durchgefallen_bei_kleiner_stichprobe() -> None:
    """@trace lernschleife#AC4 — 30–99 Trades: gezählt (AC3), aber
    „durchgefallen" — kein WFE/DSR (Präzisierung docs/specs/lernschleife.md)."""
    report = bewerte_stufe_a(
        _trades(50, schritt_tage=5, rendite="1"),
        hypothesis_id=uuid.uuid4(),
        n_trials=1,
    )

    assert report.ergebnis == "durchgefallen"
    assert report.n_trades == 50
    assert report.walk_forward_effizienz is None
    assert report.dsr is None


def test_bewerte_stufe_a_besteht_bei_ausreichender_stichprobe_und_stabiler_performance() -> None:
    """@trace lernschleife#AC4,AC5,AC6,AC7 — voller Flow: >= 100 Trades,
    stabile (identische) Rendite in Training und Validierung -> WFE ~1.0
    (>= Schwelle), DSR berechnet, Stufe A bestanden."""
    report = bewerte_stufe_a(
        _stabile_trades_mit_streuung(150, schritt_tage=5, basis=1.0),
        hypothesis_id=uuid.uuid4(),
        n_trials=3,
    )

    assert report.ergebnis == "bestanden"
    assert report.n_trades == 150
    assert report.walk_forward_effizienz is not None
    assert report.walk_forward_effizienz >= Decimal("0.5")
    assert report.dsr is not None
    assert len(report.splits) >= 2


def test_bewerte_stufe_a_faellt_durch_bei_einbrechender_out_of_sample_performance() -> None:
    """@trace lernschleife#AC6 — deutlich schwächere Out-of-Sample- als
    In-Sample-Rendite (WFE < Schwelle) -> Overfit-Verdacht, Stufe A nicht
    bestanden, obwohl die Stichprobe ausreicht."""
    trades = _trades(75, schritt_tage=5, rendite="5") + [
        _trade(75 * 5 + i * 5, "-5") for i in range(75)
    ]

    report = bewerte_stufe_a(trades, hypothesis_id=uuid.uuid4(), n_trials=3)

    assert report.n_trades == 150
    assert report.ergebnis == "durchgefallen"
    assert report.walk_forward_effizienz is not None
    assert report.walk_forward_effizienz < Decimal("0.5")


def test_bewerte_stufe_a_dsr_sinkt_mit_steigender_trial_anzahl_im_vollen_flow() -> None:
    """@trace lernschleife#AC7 — Trial-Registry-Korrektur wirkt end-to-end
    über `bewerte_stufe_a`, nicht nur in der isolierten DSR-Funktion."""
    trades = _stabile_trades_mit_streuung(150, schritt_tage=5, basis=1.0)

    report_wenige = bewerte_stufe_a(trades, hypothesis_id=uuid.uuid4(), n_trials=1)
    report_viele = bewerte_stufe_a(trades, hypothesis_id=uuid.uuid4(), n_trials=500)

    assert report_wenige.dsr is not None
    assert report_viele.dsr is not None
    assert report_viele.dsr < report_wenige.dsr
