"""Tests für den Sell-Pfad "Analyse bestehende Titel" (Story S-034).

Covers (analyse-pipelines): AC5, AC6, AC7

`app.domain.analysis_existing.sell_pfad.bewerte_bestehenden_titel` bewertet
ein bereits schwellenwertetes `UeberwachungsEreignis` (S-033) ausschliesslich
gegen die fixierte Thesis-Bruch-Katastrophen-Enum (AC5, "kein moving the
goalposts", BR-011), erzeugt immer ein `SellSignal` (AC6) und klassifiziert
dessen Dringlichkeit als Hard-Exit bei fundamentalem Thesis-Bruch
(Hack/Betrug/Delisting/Insolvenz) oder sonst Soft-Exit (AC7)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.contracts.analyse_pipelines import SellSignal
from app.contracts.depot_ueberwachung import UeberwachungsEreignis
from app.domain.analysis_existing.sell_pfad import bewerte_bestehenden_titel

_ZEITSTEMPEL = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _news_ereignis(text: str, *, anzahl_treffer: str = "1") -> UeberwachungsEreignis:
    return UeberwachungsEreignis(
        titel_id="acme-corp",
        ereignistyp="news_katalysator",
        rohwerte={"anzahl_treffer": anzahl_treffer, "texte": text},
        zeitstempel=_ZEITSTEMPEL,
        quellen_id="NewsAPI",
    )


def _numerisches_ereignis(ereignistyp: str) -> UeberwachungsEreignis:
    return UeberwachungsEreignis(
        titel_id="acme-corp",
        ereignistyp=ereignistyp,  # type: ignore[arg-type]
        rohwerte={"wert": "0.6", "schwelle": "0.5"},
        zeitstempel=_ZEITSTEMPEL,
        quellen_id="signal_buendel",
    )


def test_ac6_jedes_ereignis_erzeugt_ein_sell_signal() -> None:
    """@trace analyse-pipelines#AC6 — ein bereits schwellenwertetes
    Überwachungs-Ereignis erzeugt immer ein Sell-Signal (die
    Schwellenprüfung ist bereits bei der Ereignis-Erzeugung, S-033,
    erfolgt — diese Funktion liefert nie `None`)."""
    signal = bewerte_bestehenden_titel(_numerisches_ereignis("momentum_verlust"))

    assert isinstance(signal, SellSignal)
    assert signal.titel_id == "acme-corp"


def test_ac6_sell_signal_uebernimmt_titel_rohwerte_und_zeitstempel_des_ereignisses() -> None:
    """@trace analyse-pipelines#AC6 — Titel, Rohwerte und Zeitstempel des
    Sell-Signals stammen unverändert aus dem auslösenden Ereignis
    (Audit-Trail, deterministisch, keine Systemzeit-Abhängigkeit)."""
    ereignis = _numerisches_ereignis("relativer_kurssturz")

    signal = bewerte_bestehenden_titel(ereignis)

    assert signal.titel_id == ereignis.titel_id
    assert signal.rohwerte == ereignis.rohwerte
    assert signal.zeitstempel == ereignis.zeitstempel
    assert signal.ausloeser == "relativer_kurssturz"


def test_ac7_katastrophen_news_erzeugt_hard_exit() -> None:
    """@trace analyse-pipelines#AC7 — eine News, die eines der
    Katastrophen-Stichworte (hier: Insolvenz) enthält, markiert die These
    als fundamental gebrochen → Hard-Exit ("sofort")."""
    ereignis = _news_ereignis("acme-corp meldet Insolvenz einer Tochtergesellschaft")

    signal = bewerte_bestehenden_titel(ereignis)

    assert signal.dringlichkeit == "hard"


def test_ac7_katastrophen_news_erkennung_ist_case_insensitiv() -> None:
    """@trace analyse-pipelines#AC7 — die Stichwort-Prüfung ist wie beim
    Keyword-/Ereignis-Filter (S-033) case-insensitiv (Teilstring)."""
    ereignis = _news_ereignis("Hack bei acme-corp-Zulieferer entdeckt")

    signal = bewerte_bestehenden_titel(ereignis)

    assert signal.dringlichkeit == "hard"


def test_ac7_nicht_katastrophale_news_erzeugt_soft_exit() -> None:
    """@trace analyse-pipelines#AC7 — eine material relevante, aber nicht
    katastrophale News (hier: Downgrade, aus `DEFAULT_EREIGNIS_KEYWORDS`
    von S-033, aber NICHT in der Katastrophen-Enum) erzeugt Soft-Exit
    ("Verschlechterung ohne Katastrophe", "gestaffelt möglich")."""
    ereignis = _news_ereignis("Analysten stufen acme-corp auf Downgrade herunter")

    signal = bewerte_bestehenden_titel(ereignis)

    assert signal.dringlichkeit == "soft"


def test_ac7_numerische_ereignistypen_erzeugen_immer_soft_exit() -> None:
    """@trace analyse-pipelines#AC7 — nicht-textuelle Ereignistypen
    (relativer Kurssturz, Sentiment-Kippen, Momentum-Verlust, On-Chain-
    Abfluss) tragen keine qualitative Katastrophen-Information und gelten
    daher einheitlich als Verschlechterung ohne Katastrophe (Soft-Exit) —
    die numerischen/zeitbasierten Stop-Trigger-Typen (Drawdown, ATR,
    Time-Box) sind AC8-AC10, Scope von S-052."""
    for ereignistyp in (
        "relativer_kurssturz",
        "sentiment_kippen",
        "momentum_verlust",
        "on_chain_abfluss",
    ):
        signal = bewerte_bestehenden_titel(_numerisches_ereignis(ereignistyp))
        assert signal.dringlichkeit == "soft", ereignistyp


def test_ac7_katastrophen_stichwortliste_ist_konfigurierbar() -> None:
    """@trace analyse-pipelines#AC7 — die Katastrophen-Enum ist laut
    Spec-Edge-Case "Thesis-Bruch-Operationalisierung (offen)" ein
    provisorischer, konfigurierbarer Default (Parameter
    `katastrophen_keywords`), analog `DEFAULT_EREIGNIS_KEYWORDS`."""
    ereignis = _news_ereignis("acme-corp meldet Skandal")

    default_signal = bewerte_bestehenden_titel(ereignis)
    konfiguriert_signal = bewerte_bestehenden_titel(ereignis, katastrophen_keywords=("Skandal",))

    assert default_signal.dringlichkeit == "soft"
    assert konfiguriert_signal.dringlichkeit == "hard"


def test_ac5_bewertet_ausschliesslich_gegen_fixierte_exit_regeln_keine_kaufschwelle() -> None:
    """@trace analyse-pipelines#AC5 — strukturell abgesichert ("kein
    moving the goalposts", BR-011): die Funktion nimmt weder
    Kategoriegewichte noch eine Score-Schwelle entgegen und kennt keinen
    Buy-Signal-Typ — sie kann daher nie eine Kaufschwelle neu verhandeln
    (analog zum Buy-Pfad-Pendant `test_ac2_buy_pfad_kennt_keinen_sell_
    signal_typ`)."""
    import inspect

    signatur = inspect.signature(bewerte_bestehenden_titel)

    assert "kategoriegewichte" not in signatur.parameters
    assert "schwellen" not in signatur.parameters

    import app.domain.analysis_existing.sell_pfad as modul

    assert not any("buy" in name.lower() for name in dir(modul))


def test_ac5_leitfrage_als_entscheidungsregel_hard_bei_thesis_bruch_sonst_soft() -> None:
    """@trace analyse-pipelines#AC5 — die Leitfrage "Würden wir die
    Position heute kaufen, wenn wir sie nicht hielten?" ist als
    Entscheidungsregel abgebildet: ein fundamentaler Thesis-Bruch
    beantwortet sie eindeutig mit "nein" (Hard-Exit), jede sonstige
    (bereits schwellenwertete) Verschlechterung bleibt uneindeutig
    (Soft-Exit) — kein drittes "kein Signal"-Ergebnis."""
    hard = bewerte_bestehenden_titel(_news_ereignis("acme-corp meldet Betrug im Management"))
    soft = bewerte_bestehenden_titel(_numerisches_ereignis("sentiment_kippen"))

    assert {hard.dringlichkeit, soft.dringlichkeit} == {"hard", "soft"}
