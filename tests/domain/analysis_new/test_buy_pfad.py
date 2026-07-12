"""Tests für den Buy-Pfad "Analyse neue Titel" (Story S-028).

Covers (analyse-pipelines): AC1, AC2, AC3, AC4

`app.domain.analysis_new.buy_pfad.bewerte_kandidat` verdrahtet die
Score-Engine (`app.domain.scoring.score_engine`, S-010) mit der
No-Evidence-No-Trade-Prüfung (`app.domain.no_evidence_no_trade`, S-014) zu
einem deterministischen Buy-Pfad: Gesamtscore über das gemeinsame
Framework, Buy-Signal genau bei Gesamtscore ≥ 8 nach Risiko-Sanity-Cap
(AC1, deckt A2), Signal-Inhalt + strukturelle Pfad-Trennung vom (noch
nicht gebauten) Sell-Pfad (AC2), Durchreichen der bereits geerdeten Fakten
gemäß LLM-Grounding-Verträgen (AC3) und No-Evidence-No-Trade-Überspringen
bei fehlender Kategorie-Datengrundlage (AC4, deckt E1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.contracts.analyse_framework import Kategoriegewichte
from app.contracts.analyse_pipelines import BuySignal
from app.contracts.llm_grounding import AnalyseFakt, AnalyseOutput, AnalyseScores
from app.core.audit_log import alle_eintraege, reset_fuer_tests
from app.domain.analysis_new.buy_pfad import bewerte_kandidat

_ZEITSTEMPEL = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

#: Gleichgewichtete Kategoriegewichte (je 20 %, Summe 100 %) — Details der
#: klassenspezifischen Gewichtung sind Nicht-Ziel dieser Story
#: (`[[anlageklassen-config]]`).
_GLEICHGEWICHTET = Kategoriegewichte(
    fundamental=20.0, technisch=20.0, qualitativ=20.0, makro=20.0, risiko=20.0
)

_FAKT = AnalyseFakt(
    kennzahl_typ="kgv",
    wert=Decimal("12.5"),
    quellen_id="sec-form4-123",
    timestamp=datetime(2026, 7, 1, tzinfo=UTC),
)


def _analyse(**score_overrides: float | str) -> AnalyseOutput:
    basis: dict[str, float | str] = {
        "fundamental": 8.0,
        "technisch": 8.0,
        "qualitativ": 8.0,
        "makro": 8.0,
        "risiko": 8.0,
    }
    basis.update(score_overrides)
    return AnalyseOutput(
        scores=AnalyseScores(**basis),
        fakten=(_FAKT,),
        begruendung="Solide Fundamentaldaten, moderates Risiko.",
    )


def _bewerte(analyse: AnalyseOutput) -> BuySignal | None:
    return bewerte_kandidat(
        titel_id="acme-corp",
        analyse=analyse,
        kategoriegewichte=_GLEICHGEWICHTET,
        zeitstempel=_ZEITSTEMPEL,
    )


def test_ac1_erzeugt_buy_signal_bei_gesamtscore_ab_acht() -> None:
    """@trace analyse-pipelines#AC1 — Gesamtscore 8.0 (5×8 gleichgewichtet)
    erzeugt ein Buy-Signal (KAUF-Schwelle inklusiv erreicht)."""
    signal = _bewerte(_analyse())

    assert signal is not None
    assert signal.gesamtscore == 8.0


def test_ac1_kein_buy_signal_unter_der_kauf_schwelle() -> None:
    """@trace analyse-pipelines#AC1 — Gesamtscore 5.0 (< 8) erzeugt KEIN
    Buy-Signal (deckt A2: BEOBACHTEN/HALTEN/REDUZIEREN/VERKAUF führen
    nicht zu Position-Sizing)."""
    analyse = _analyse(fundamental=5.0, technisch=5.0, qualitativ=5.0, makro=5.0, risiko=5.0)

    signal = _bewerte(analyse)

    assert signal is None


def test_ac1_sanity_cap_verhindert_buy_signal_trotz_hohem_score() -> None:
    """@trace analyse-pipelines#AC1 — Risiko-Score 2 (< 3, Sanity-Cap-
    Schwelle) deckelt ein rechnerisch hohes Gesamtsignal (8.4, roh KAUF)
    auf HALTEN — es entsteht KEIN Buy-Signal, obwohl der Gesamtscore
    rechnerisch über der KAUF-Schwelle läge (Edge-Case der Spec: "Sanity-
    Cap des Frameworks kann ein Buy-Signal verhindern")."""
    analyse = _analyse(fundamental=10.0, technisch=10.0, qualitativ=10.0, makro=10.0, risiko=2.0)

    signal = _bewerte(analyse)

    assert signal is None


def test_ac2_buy_signal_enthaelt_titel_und_gesamtscore() -> None:
    """@trace analyse-pipelines#AC2 — das erzeugte Buy-Signal enthält
    mindestens Titel + Gesamtscore, bereit zur Übergabe an das
    Position-Sizing."""
    signal = _bewerte(_analyse())

    assert signal is not None
    assert signal.titel_id == "acme-corp"
    assert signal.gesamtscore == 8.0


def test_ac2_buy_pfad_kennt_keinen_sell_signal_typ() -> None:
    """@trace analyse-pipelines#AC2 — die Pfad-Trennung ist strukturell:
    das Buy-Pfad-Modul definiert/importiert keinen "Sell"-benannten Typ
    und kann daher nie ein Sell-Signal erzeugen (Sell-Pfad ist S-034,
    eigenständiges `domain/analysis_existing/`-Paket)."""
    import app.domain.analysis_new.buy_pfad as modul

    assert not any("sell" in name.lower() for name in dir(modul))


def test_ac3_fakten_mit_quellen_werden_unveraendert_durchgereicht() -> None:
    """@trace analyse-pipelines#AC3 — die im Output referenzierten Fakten
    sind exakt die bereits geerdeten Fakten des Analyse-Outputs (Quellen-ID
    + Zeitstempel je Fakt, LLM-Grounding-Verträge) — kein erneuter
    LLM-Aufruf, keine Veränderung."""
    analyse = _analyse()

    signal = _bewerte(analyse)

    assert signal is not None
    assert signal.fakten_mit_quellen == analyse.fakten
    for fakt in signal.fakten_mit_quellen:
        assert fakt.quellen_id
        assert fakt.timestamp is not None


def test_ac3_zeitstempel_wird_explizit_uebernommen_nicht_aus_systemzeit() -> None:
    """@trace analyse-pipelines#AC3 — der Zeitstempel des Buy-Signals ist
    der explizit übergebene `as_of`-Zeitpunkt (deterministischer Order-Pfad,
    keine Systemzeit-Abhängigkeit)."""
    signal = _bewerte(_analyse())

    assert signal is not None
    assert signal.zeitstempel == _ZEITSTEMPEL


def test_ac4_ueberspringt_titel_bei_fehlender_kategorie() -> None:
    """@trace analyse-pipelines#AC4 — fehlt einer ganzen Analysekategorie
    die Datengrundlage (Score "fehlt"), wird der Titel übersprungen (kein
    Buy-Signal), statt die Kategorie durch eine LLM-Schätzung zu ersetzen
    (No-Evidence-No-Trade, deckt E1)."""
    reset_fuer_tests()
    analyse = _analyse(risiko="fehlt")

    signal = _bewerte(analyse)

    assert signal is None
    eintraege = alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "keine_evidenz"
    reset_fuer_tests()


def test_ac4_evidenzluecke_ueberspringt_auch_bei_sonst_hohen_scores() -> None:
    """@trace analyse-pipelines#AC4 — auch wenn alle ÜBRIGEN Kategorien
    einen sehr hohen Score tragen, wird der Titel bei einer fehlenden
    Kategorie übersprungen (kein 0-Ersatz, keine Schätzung, kein
    Gesamtscore)."""
    reset_fuer_tests()
    analyse = _analyse(
        fundamental=10.0, technisch=10.0, qualitativ=10.0, makro=10.0, risiko="fehlt"
    )

    signal = _bewerte(analyse)

    assert signal is None
    reset_fuer_tests()
