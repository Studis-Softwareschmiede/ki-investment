"""Validierungs-Gate Stufe A (historisch) — Berechnungskern (S-060, Spec
`docs/specs/lernschleife.md` AC4/AC5/AC6/AC7).

Reiner Domain-Kern (architecture.md §4 P1): keine I/O, keine DB, kein
LLM. Wer `n_trials` (aus der Trial-Registry, `app.db.trial_registry`)
oder die Point-in-Time-saubere Trade-Historie beschafft, ist Sache des
Aufrufers (Orchestration-Schicht) — dieses Modul konsumiert nur bereits
aufbereitete `TradeErgebnis`-Listen und einen `n_trials`-Zähler.

- **AC4 (Mindest-Stichprobe, deckt A3):** `pruefe_mindeststichprobe`
  unterscheidet DREI Zonen (die AC12-Trennung von "Mindest-Stichprobe"
  und "Bewertungs-Untergrenze" als zwei unabhängig konfigurierbare
  Schwellen macht dies notwendig, siehe Spec-Präzisierung AC4):
  - `< bewertungsuntergrenze` (Default 30): **nicht bewertet** — kein
    Urteil, keine Übernahme (A3).
  - `bewertungsuntergrenze <= n < mindest_stichprobe` (Default
    [30, 100)): **durchgefallen** — die Variante wird gezählt (AC3), aber
    die Stichprobe reicht nicht für ein Bestehen; WFE/DSR werden dafür
    nicht mehr berechnet (kein sinnvolles Ergebnis bei so wenigen Trades).
  - `>= mindest_stichprobe`: **ausreichend** — volle Bewertung
    (Walk-Forward + DSR) läuft.
- **AC5 (Walk-Forward mit Embargo):** `erzeuge_walk_forward_splits` baut
  ein anchored/expanding Walk-Forward über ALLE sequentiellen Splits
  (mind. 2, sonst gilt AC5 als nicht erfüllbar) — zwischen dem Ende des
  Trainingsfensters und dem Start des Validierungsfensters liegt ein
  `embargo_tage`-Tage-Puffer; Trades, die in diesen Puffer fallen, werden
  aus BEIDEN Fenstern entfernt (Datenleckage-Schutz).
- **AC6 (Walk-Forward-Effizienz):** `berechne_walk_forward_effizienz`
  poolt die durchschnittliche In-Sample-/Out-of-Sample-Rendite PRO TRADE
  über ALLE Splits — eine einzelne Kennzahl über die gesamte
  Walk-Forward-Sequenz, nicht nur den letzten/besten Split (Durchschnitt
  statt Summe, damit das mit jedem Split wachsende Trainingsfenster des
  anchored Walk-Forward das Verhältnis nicht künstlich verzerrt). `< 0.5`
  (Default) gilt als Overfit-Verdacht, die Hypothese besteht Stufe A
  nicht.
- **AC7 (Deflated Sharpe Ratio):** `berechne_deflated_sharpe_ratio`
  implementiert die Bailey/López-de-Prado-DSR (siehe Docstring der
  Funktion) — korrigiert um `n_trials` (aus der Trial-Registry). **Kein**
  eigener Zahlen-Schwellenwert für die DSR ist Teil dieser Story: AC7
  verlangt nur die Berechnung; die einzigen genannten Stufe-A-Gate-
  Kriterien sind Stichprobe (AC4) und WFE (AC6) — deckungsgleich mit
  `docs/architecture.md` BR-119 ("🟢 nur wenn ... sample ≥ 100, WFE ≥
  0.5, PSR ≥ 0.95"), das DSR ebenfalls nicht als eigenes Ampel-Kriterium
  nennt. Der DSR-Wert wird trotzdem immer berechnet und im
  `StufeAReport` ausgewiesen (Audit/Transparenz).

`bewerte_stufe_a` verdrahtet die vier Bausteine zum vollen
`StufeAReport`.
"""

from __future__ import annotations

import math
import statistics
import uuid
from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from app.contracts.lernschleife import (
    StufeAErgebnis,
    StufeAKonfiguration,
    StufeAReport,
    TradeErgebnis,
    WalkForwardSplitErgebnis,
)
from app.domain.lernschleife._statistik import EULER_MASCHERONI, berechne_stichprobenkennzahlen

#: Default-Anzahl Walk-Forward-Splits (AC5). Bewusst NICHT Teil der
#: AC12-Schwellenliste (die nennt nur Mindest-Stichprobe,
#: Bewertungs-Untergrenze, Embargo-Dauer, WF-Effizienz, PSR-Schwelle) —
#: trotzdem als Parameter konfigurierbar für Testbarkeit/Tuning.
_STANDARD_N_SPLITS = 5

#: Rückgabewert von `pruefe_mindeststichprobe` (AC4/A3 — die drei
#: Stichproben-Zonen, siehe Modul-Docstring).
StichprobenStatus = Literal["nicht_bewertet", "durchgefallen_kleine_stichprobe", "ausreichend"]


def pruefe_mindeststichprobe(
    n_trades: int, *, konfiguration: StufeAKonfiguration
) -> StichprobenStatus:
    """AC4/A3 — ordnet die Trade-Zahl einer der drei Stichproben-Zonen zu:
    `"nicht_bewertet"`, `"durchgefallen_kleine_stichprobe"` oder
    `"ausreichend"` (siehe Modul-Docstring für die Grenzen)."""
    if n_trades < konfiguration.bewertungsuntergrenze:
        return "nicht_bewertet"
    if n_trades < konfiguration.mindest_stichprobe:
        return "durchgefallen_kleine_stichprobe"
    return "ausreichend"


def erzeuge_walk_forward_splits(
    trades: Sequence[TradeErgebnis],
    *,
    embargo_tage: int,
    n_splits: int = _STANDARD_N_SPLITS,
) -> list[WalkForwardSplitErgebnis]:
    """AC5 — baut ein anchored Walk-Forward über die chronologisch
    sortierten `trades`: die Trades werden in `n_splits + 1` etwa gleich
    grosse, zeitlich aufeinanderfolgende Gruppen geteilt (Gruppe 0 =
    initiales Trainingsfenster, Gruppen 1..n_splits = sequentielle
    Validierungsfenster). Für jeden Split `i` besteht das Trainingsfenster
    aus allen Trades der vorangehenden Gruppen, die **mindestens
    `embargo_tage` Tage vor** dem Start des Validierungsfensters liegen —
    Trades innerhalb dieses Embargo-Puffers werden aus dem Trainingsfenster
    entfernt (purged), damit kein Datenleck zwischen den Fenstern
    entsteht.

    Liefert eine leere Liste, wenn zu wenige Trades vorhanden sind, um
    mindestens 2 Gruppen zu bilden, oder wenn das Embargo ein
    Trainingsfenster vollständig aufzehrt."""
    if n_splits < 1:
        raise ValueError("n_splits muss >= 1 sein")

    sortiert = sorted(trades, key=lambda t: t.datum)
    n = len(sortiert)
    if n < 2:
        return []

    embargo = timedelta(days=embargo_tage)
    gruppen_anzahl = n_splits + 1
    if n < gruppen_anzahl * 2:
        # Zu wenige Trades für die gewünschte Split-Anzahl — so viele
        # Gruppen bilden, wie sinnvoll möglich sind (mind. 2).
        gruppen_anzahl = max(2, n // 2)

    basisgroesse, rest = divmod(n, gruppen_anzahl)
    gruppen: list[list[TradeErgebnis]] = []
    start = 0
    for i in range(gruppen_anzahl):
        groesse = basisgroesse + (1 if i < rest else 0)
        gruppen.append(sortiert[start : start + groesse])
        start += groesse

    splits: list[WalkForwardSplitErgebnis] = []
    for i in range(1, len(gruppen)):
        validierung = gruppen[i]
        if not validierung:
            continue
        validierung_von = validierung[0].datum
        validierung_bis = validierung[-1].datum
        embargo_grenze = validierung_von - embargo

        kandidaten_train = [t for gruppe in gruppen[:i] for t in gruppe]
        train = [t for t in kandidaten_train if t.datum <= embargo_grenze]
        if not train:
            continue  # Embargo hat das Trainingsfenster vollständig aufgezehrt

        splits.append(
            WalkForwardSplitErgebnis(
                split_index=len(splits),
                train_von=train[0].datum,
                train_bis=train[-1].datum,
                validierung_von=validierung_von,
                validierung_bis=validierung_bis,
                n_trades_train=len(train),
                n_trades_validierung=len(validierung),
                is_rendite=sum((t.rendite_pct for t in train), Decimal("0")),
                oos_rendite=sum((t.rendite_pct for t in validierung), Decimal("0")),
            )
        )
    return splits


def berechne_walk_forward_effizienz(
    splits: Sequence[WalkForwardSplitErgebnis],
) -> Decimal | None:
    """AC6 — Verhältnis der durchschnittlichen Out-of-Sample-Rendite pro
    Trade zur durchschnittlichen In-Sample-Rendite pro Trade, gepoolt
    ÜBER ALLE `splits` (nicht nur ein einzelner Split — AC5 "über alle
    sequentiellen Splits geprüft"). Bewusst als Durchschnitt PRO TRADE
    (nicht als Verhältnis der Renditesummen): beim anchored Walk-Forward
    (AC5) wächst das Trainingsfenster von Split zu Split, eine reine
    Summenbildung würde spätere (grössere) Trainingsfenster überproportional
    gewichten und selbst bei stabiler Performance ein Verhältnis < 1
    erzwingen — ein Artefakt der Fenstergrösse, kein Overfit-Signal.
    Liefert `None`, wenn keine Splits vorliegen oder die gepoolte
    durchschnittliche In-Sample-Rendite nicht positiv ist (Ratio dann
    nicht sinnvoll interpretierbar als "OOS erreicht mindestens die
    Hälfte der IS-Rendite")."""
    if not splits:
        return None
    n_is_gesamt = sum(s.n_trades_train for s in splits)
    n_oos_gesamt = sum(s.n_trades_validierung for s in splits)
    if n_is_gesamt == 0 or n_oos_gesamt == 0:
        return None
    is_durchschnitt = sum((s.is_rendite for s in splits), Decimal("0")) / n_is_gesamt
    oos_durchschnitt = sum((s.oos_rendite for s in splits), Decimal("0")) / n_oos_gesamt
    if is_durchschnitt <= 0:
        return None
    return oos_durchschnitt / is_durchschnitt


def berechne_deflated_sharpe_ratio(renditen: Sequence[Decimal], *, n_trials: int) -> Decimal:
    """AC7 — Deflated Sharpe Ratio (Bailey & López de Prado, 2014, "The
    Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
    Overfitting, and Non-Normality"): die Probabilistic-Sharpe-Ratio
    (PSR) der Renditen gegen die ERWARTETE MAXIMALE Sharpe Ratio unter
    `n_trials` unabhängigen, aus der Trial-Registry gezählten Versuchen
    (statt gegen Benchmark 0 wie die reine PSR in Stufe B, AC8) —
    korrigiert damit für Mehrfach-Test-/Selektions-Bias.

    `n_trials <= 1` (nur diese eine Variante je getestet) → keine
    Mehrfach-Test-Korrektur nötig, erwartete maximale Sharpe Ratio = 0.

    Formel (nicht-normale Renditen, T = Stichprobengrösse, γ3 = Schiefe,
    γ4 = Kurtosis, SR_hat = Stichproben-Sharpe-Ratio):

        Var[SR_hat]  = (1 - γ3·SR_hat + (γ4-1)/4·SR_hat²) / (T-1)
        SR_0         = sqrt(Var[SR_hat]) · [(1-γ)·Φ⁻¹(1-1/N)
                        + γ·Φ⁻¹(1-1/(N·e))]                    (γ = 0.5772…)
        DSR          = Φ[(SR_hat - SR_0)·sqrt(T-1)
                        / sqrt(1 - γ3·SR_hat + (γ4-1)/4·SR_hat²)]
    """
    if n_trials < 1:
        raise ValueError("n_trials muss >= 1 sein (Trial-Registry zählt jede Variante, AC3)")

    kennzahlen = berechne_stichprobenkennzahlen(renditen)
    t, sr_hat, nenner_term = kennzahlen.t, kennzahlen.sr_hat, kennzahlen.nenner_term

    normal = statistics.NormalDist()
    if n_trials <= 1:
        sr0 = 0.0
    else:
        varianz_sr_hat = nenner_term / (t - 1)
        sr0 = math.sqrt(varianz_sr_hat) * (
            (1 - EULER_MASCHERONI) * normal.inv_cdf(1 - 1 / n_trials)
            + EULER_MASCHERONI * normal.inv_cdf(1 - 1 / (n_trials * math.e))
        )

    dsr = normal.cdf((sr_hat - sr0) * math.sqrt(t - 1) / math.sqrt(nenner_term))
    return Decimal(str(dsr))


def bewerte_stufe_a(
    trades: Sequence[TradeErgebnis],
    *,
    hypothesis_id: uuid.UUID,
    n_trials: int,
    konfiguration: StufeAKonfiguration | None = None,
    n_splits: int = _STANDARD_N_SPLITS,
) -> StufeAReport:
    """Orchestriert AC4 → AC5 → AC6 → AC7 zum vollen `StufeAReport`
    (Main Success Scenario Schritt 4). `n_trials` kommt vom Aufrufer aus
    der Trial-Registry (`app.db.trial_registry.anzahl_trials`) — dieses
    Modul selbst greift nicht auf die DB zu (P1)."""
    konfiguration = konfiguration or StufeAKonfiguration()
    n_trades = len(trades)
    stichprobenstatus = pruefe_mindeststichprobe(n_trades, konfiguration=konfiguration)

    if stichprobenstatus == "nicht_bewertet":
        return _report(
            hypothesis_id,
            n_trades,
            konfiguration,
            ergebnis="nicht_bewertet",
            begruendung=(
                f"Stichprobe ({n_trades} Trades) < Bewertungsuntergrenze "
                f"({konfiguration.bewertungsuntergrenze}) — kein Urteil (AC4/A3)."
            ),
        )

    if stichprobenstatus == "durchgefallen_kleine_stichprobe":
        return _report(
            hypothesis_id,
            n_trades,
            konfiguration,
            ergebnis="durchgefallen",
            begruendung=(
                f"Stichprobe ({n_trades} Trades) < Mindest-Stichprobe "
                f"({konfiguration.mindest_stichprobe}) — Stufe A nicht bestanden (AC4)."
            ),
        )

    splits = erzeuge_walk_forward_splits(
        trades, embargo_tage=konfiguration.embargo_tage, n_splits=n_splits
    )
    wfe = berechne_walk_forward_effizienz(splits)

    if len(splits) < 2 or wfe is None:
        return _report(
            hypothesis_id,
            n_trades,
            konfiguration,
            ergebnis="durchgefallen",
            begruendung=(
                "Walk-Forward mit Embargo über mindestens zwei sequentielle Splits "
                "nicht durchführbar oder gepoolte In-Sample-Rendite nicht positiv "
                "— Stufe A nicht bestanden (AC5/AC6)."
            ),
            splits=splits,
        )

    try:
        dsr = berechne_deflated_sharpe_ratio([t.rendite_pct for t in trades], n_trials=n_trials)
    except ValueError as exc:
        # Degenerierte Renditeverteilung (z.B. konstante Renditen → Std 0,
        # oder extreme Schiefe/Wölbung → Varianzterm <= 0): die DSR ist
        # mathematisch nicht definiert. Das AC4-Drei-Zonen-Modell verspricht
        # für jede "ausreichende" Stichprobe ein Urteil, keinen Absturz —
        # daher kontrolliert als "durchgefallen" werten (analog splits<2/
        # wfe-None-Fallback oben), statt die Exception nach oben zu reissen.
        return _report(
            hypothesis_id,
            n_trades,
            konfiguration,
            ergebnis="durchgefallen",
            begruendung=(
                f"Deflated Sharpe Ratio nicht berechenbar ({exc}) — degenerierte "
                "Renditeverteilung, Stufe A nicht bestanden (AC7)."
            ),
            walk_forward_effizienz=wfe,
            splits=splits,
        )

    if wfe < konfiguration.wfe_schwelle:
        return _report(
            hypothesis_id,
            n_trades,
            konfiguration,
            ergebnis="durchgefallen",
            begruendung=(
                f"Walk-Forward-Effizienz {wfe} < Schwelle {konfiguration.wfe_schwelle} "
                "— Overfit-Verdacht (AC6)."
            ),
            walk_forward_effizienz=wfe,
            dsr=dsr,
            splits=splits,
        )

    return _report(
        hypothesis_id,
        n_trades,
        konfiguration,
        ergebnis="bestanden",
        begruendung=(
            f"Stufe A bestanden: {n_trades} Trades, WFE {wfe} >= "
            f"{konfiguration.wfe_schwelle}, DSR {dsr}."
        ),
        walk_forward_effizienz=wfe,
        dsr=dsr,
        splits=splits,
    )


def _report(
    hypothesis_id: uuid.UUID,
    n_trades: int,
    konfiguration: StufeAKonfiguration,
    *,
    ergebnis: StufeAErgebnis,
    begruendung: str,
    walk_forward_effizienz: Decimal | None = None,
    dsr: Decimal | None = None,
    splits: list[WalkForwardSplitErgebnis] | None = None,
) -> StufeAReport:
    return StufeAReport(
        hypothesis_id=hypothesis_id,
        n_trades=n_trades,
        embargo_tage=konfiguration.embargo_tage,
        walk_forward_effizienz=walk_forward_effizienz,
        dsr=dsr,
        ergebnis=ergebnis,
        begruendung=begruendung,
        splits=splits or [],
    )


__all__ = [
    "pruefe_mindeststichprobe",
    "erzeuge_walk_forward_splits",
    "berechne_walk_forward_effizienz",
    "berechne_deflated_sharpe_ratio",
    "bewerte_stufe_a",
]
