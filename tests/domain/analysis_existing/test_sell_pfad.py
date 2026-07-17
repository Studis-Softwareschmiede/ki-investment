"""Tests für den Sell-Pfad "Analyse bestehende Titel" (Story S-034, S-052).

Covers (analyse-pipelines): AC5, AC6, AC7, AC8, AC9, AC10

`app.domain.analysis_existing.sell_pfad.bewerte_bestehenden_titel` bewertet
ein bereits schwellenwertetes `UeberwachungsEreignis` (S-033) ausschliesslich
gegen die fixierte Thesis-Bruch-Katastrophen-Enum (AC5, "kein moving the
goalposts", BR-011), erzeugt immer ein `SellSignal` (AC6) und klassifiziert
dessen Dringlichkeit als Hard-Exit bei fundamentalem Thesis-Bruch
(Hack/Betrug/Delisting/Insolvenz) oder sonst Soft-Exit (AC7).

S-052 (AC8-AC10) ergänzt die numerischen/zeitbasierten Stop-Trigger-Typen
über den optionalen `exit_kontext`-Parameter (`ExitTriggerKontext`):
Drawdown-Trigger ggü. Hoch/Einstand + Markt-Underperformance (AC8),
Stop-Typ je Strategie — ATR-Trailing/fix_pct/fundamental/keiner (AC9) —
und Time-Box-Ablauf (AC10). Fehlt `exit_kontext`, bleibt das S-034-
Verhalten unverändert (jedes Ereignis erzeugt ein Soft-Exit-Signal); ist
er gesetzt und trifft keiner der drei Trigger zu, liefert die Funktion
`None` (kein Exit möglich)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.contracts.analyse_pipelines import ExitTriggerKontext, SellSignal
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


def _exit_kontext(
    *,
    einstand: Decimal = Decimal("90"),
    hoch_seit_kauf: Decimal = Decimal("100"),
    aktueller_kurs: Decimal = Decimal("95"),
    titel_bewegung_pct: Decimal = Decimal("0"),
    markt_bewegung_pct: Decimal | None = Decimal("0"),
    position_alter: timedelta = timedelta(days=1),
    stop_typ: str | None = None,
    atr_wert: Decimal | None = None,
    atr_multiplikator: Decimal | None = None,
    stop_loss_pct: Decimal | None = None,
    time_box: timedelta | None = None,
) -> ExitTriggerKontext:
    return ExitTriggerKontext(
        einstand=einstand,
        hoch_seit_kauf=hoch_seit_kauf,
        aktueller_kurs=aktueller_kurs,
        titel_bewegung_pct=titel_bewegung_pct,
        markt_bewegung_pct=markt_bewegung_pct,
        position_alter=position_alter,
        stop_typ=stop_typ,
        atr_wert=atr_wert,
        atr_multiplikator=atr_multiplikator,
        stop_loss_pct=stop_loss_pct,
        time_box=time_box,
    )


def test_ac8_drawdown_vom_hoch_und_underperformance_loest_review_aus() -> None:
    """@trace analyse-pipelines#AC8 — 21% Fall vom Hoch (> 20%-Schwelle)
    UND Underperformance ggü. dem Markt löst einen Drawdown-Review
    (Soft-Exit, ausloeser="drawdown") aus."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("90"),
        aktueller_kurs=Decimal("79"),
        titel_bewegung_pct=Decimal("-0.05"),
        markt_bewegung_pct=Decimal("0.00"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("relativer_kurssturz"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.dringlichkeit == "soft"
    assert signal.ausloeser == "drawdown"


def test_ac8_fall_vom_einstand_allein_loest_ebenfalls_aus() -> None:
    """@trace analyse-pipelines#AC8 — 10%-Fall vom Einstand allein (ohne
    20%-Fall vom Hoch) löst den Drawdown-Trigger bereits aus ("oder")."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("100"),
        aktueller_kurs=Decimal("90"),
        titel_bewegung_pct=Decimal("-0.10"),
        markt_bewegung_pct=Decimal("-0.02"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("relativer_kurssturz"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.ausloeser == "drawdown"


def test_ac8_schwelle_exakt_erreicht_loest_aus() -> None:
    """@trace analyse-pipelines#AC8 — Grenzfall: Fall vom Hoch exakt 20%
    (nicht überschritten) löst bereits aus (`>=`, nicht `>`)."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("100"),
        aktueller_kurs=Decimal("80"),
        titel_bewegung_pct=Decimal("-0.20"),
        markt_bewegung_pct=Decimal("0.00"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("relativer_kurssturz"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.ausloeser == "drawdown"


def test_ac8_fall_ohne_underperformance_loest_keinen_drawdown_aus() -> None:
    """@trace analyse-pipelines#AC8 — Kurs fällt 21% vom Hoch, aber der
    Titel performt genauso wie der Markt (keine Underperformance) — kein
    Drawdown-Trigger; ohne weiteren Stop-/Time-Box-Trigger liefert die
    Funktion `None` (kein Exit, "aufpassen und prüfen")."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("100"),
        aktueller_kurs=Decimal("79"),
        titel_bewegung_pct=Decimal("-0.21"),
        markt_bewegung_pct=Decimal("-0.21"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("relativer_kurssturz"), exit_kontext=kontext
    )

    assert signal is None


def test_ac8_fall_unter_beiden_schwellen_loest_keinen_drawdown_aus() -> None:
    """@trace analyse-pipelines#AC8 — Fall unter beiden Schwellen (19% vom
    Hoch, 9% vom Einstand) löst trotz Underperformance keinen Drawdown-
    Trigger aus."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("89"),
        aktueller_kurs=Decimal("81"),
        titel_bewegung_pct=Decimal("-0.19"),
        markt_bewegung_pct=Decimal("0.00"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("relativer_kurssturz"), exit_kontext=kontext
    )

    assert signal is None


def test_ac9_atr_trailing_stop_genau_erreicht_loest_aus() -> None:
    """@trace analyse-pipelines#AC9 — Momentum-Strategie: ATR-Trailing-Stop
    (Hoch - ATR*Multiplikator) genau erreicht löst aus (`<=`)."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("95"),
        aktueller_kurs=Decimal("90"),
        stop_typ="atr_trailing",
        atr_wert=Decimal("4"),
        atr_multiplikator=Decimal("2.5"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("momentum_verlust"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.ausloeser == "stop_atr_trailing"


def test_ac9_atr_trailing_stop_ueberschritten_loest_aus() -> None:
    """@trace analyse-pipelines#AC9 — Kurs unterhalb des ATR-Trailing-
    Stop-Niveaus löst ebenfalls aus."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("95"),
        aktueller_kurs=Decimal("85"),
        stop_typ="atr_trailing",
        atr_wert=Decimal("4"),
        atr_multiplikator=Decimal("2.5"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("momentum_verlust"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.ausloeser == "stop_atr_trailing"


def test_ac9_atr_trailing_stop_nicht_erreicht_kein_trigger() -> None:
    """@trace analyse-pipelines#AC9 — Kurs oberhalb des ATR-Trailing-
    Stop-Niveaus löst keinen Stop-Trigger aus; ohne Drawdown/Time-Box
    liefert die Funktion `None`."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("95"),
        aktueller_kurs=Decimal("91"),
        stop_typ="atr_trailing",
        atr_wert=Decimal("4"),
        atr_multiplikator=Decimal("2.5"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("momentum_verlust"), exit_kontext=kontext
    )

    assert signal is None


def test_ac9_fix_pct_stop_buy_and_hold_genau_erreicht_loest_aus() -> None:
    """@trace analyse-pipelines#AC9 — Buy-and-Hold: fixer Prozent-Stop
    (hier 27.5%) genau erreicht löst aus."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("100"),
        aktueller_kurs=Decimal("72.5"),
        stop_typ="fix_pct",
        stop_loss_pct=Decimal("0.275"),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("momentum_verlust"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.ausloeser == "stop_fix_pct"


def test_ac9_fundamental_stop_typ_loest_nie_numerischen_stop_aus() -> None:
    """@trace analyse-pipelines#AC9 — Value-Strategie (`stop_typ=
    "fundamental"`, kein reiner Kurs-Stop) löst trotz starkem Kursverfall
    keinen numerischen Stop aus."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("100"),
        aktueller_kurs=Decimal("50"),
        titel_bewegung_pct=Decimal("0"),
        markt_bewegung_pct=Decimal("0"),
        stop_typ="fundamental",
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("momentum_verlust"), exit_kontext=kontext
    )

    assert signal is None


def test_ac9_keiner_stop_typ_loest_nie_aus() -> None:
    """@trace analyse-pipelines#AC9 — `stop_typ="keiner"` (expliziter
    Verzicht) löst nie einen numerischen Stop aus."""
    kontext = _exit_kontext(
        hoch_seit_kauf=Decimal("100"),
        einstand=Decimal("100"),
        aktueller_kurs=Decimal("70"),
        titel_bewegung_pct=Decimal("0"),
        markt_bewegung_pct=Decimal("0"),
        stop_typ="keiner",
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("momentum_verlust"), exit_kontext=kontext
    )

    assert signal is None


def test_ac10_time_box_genau_abgelaufen_loest_review_aus() -> None:
    """@trace analyse-pipelines#AC10 — die verstrichene Zeit erreicht die
    Time-Box-Frist exakt (`>=`) und löst eine Review aus."""
    kontext = _exit_kontext(
        time_box=timedelta(days=90),
        position_alter=timedelta(days=90),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("sentiment_kippen"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.ausloeser == "time_box"


def test_ac10_time_box_ueberschritten_loest_aus() -> None:
    """@trace analyse-pipelines#AC10 — die verstrichene Zeit überschreitet
    die Time-Box-Frist und löst ebenfalls aus."""
    kontext = _exit_kontext(
        time_box=timedelta(days=90),
        position_alter=timedelta(days=95),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("sentiment_kippen"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.ausloeser == "time_box"


def test_ac10_time_box_nicht_abgelaufen_kein_trigger() -> None:
    """@trace analyse-pipelines#AC10 — die verstrichene Zeit liegt unter
    der Time-Box-Frist; ohne Drawdown/Stop-Trigger liefert die Funktion
    `None`."""
    kontext = _exit_kontext(
        time_box=timedelta(days=90),
        position_alter=timedelta(days=89),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("sentiment_kippen"), exit_kontext=kontext
    )

    assert signal is None


def test_ac10_time_box_none_loest_nie_aus() -> None:
    """@trace analyse-pipelines#AC10 — `time_box=None` (A2, z.B. Index/
    Buy-and-Hold ohne Time-Box) löst nie aus, unabhängig vom
    Positionsalter."""
    kontext = _exit_kontext(
        time_box=None,
        position_alter=timedelta(days=3650),
    )

    signal = bewerte_bestehenden_titel(
        _numerisches_ereignis("sentiment_kippen"), exit_kontext=kontext
    )

    assert signal is None


def test_ac6_ac8_thesis_bruch_bleibt_hard_exit_trotz_exit_kontext_ohne_trigger() -> None:
    """@trace analyse-pipelines#AC6 — ein fundamentaler Thesis-Bruch (AC7)
    erzeugt immer ein Hard-Exit-Signal, unabhängig davon, ob der
    (numerische) `exit_kontext` selbst einen Trigger auslöst."""
    kontext = _exit_kontext(time_box=None)

    signal = bewerte_bestehenden_titel(
        _news_ereignis("acme-corp meldet Insolvenz"), exit_kontext=kontext
    )

    assert signal is not None
    assert signal.dringlichkeit == "hard"


def test_ac6_kein_exit_kontext_und_kein_thesis_bruch_erzeugt_weiterhin_soft_exit() -> None:
    """@trace analyse-pipelines#AC6 — fehlt `exit_kontext` (S-034-
    Cold-Start), bleibt das bisherige Verhalten unverändert: jedes
    Ereignis erzeugt weiterhin ein Soft-Exit-Signal (nie `None`)."""
    signal = bewerte_bestehenden_titel(_numerisches_ereignis("momentum_verlust"))

    assert signal is not None
    assert signal.dringlichkeit == "soft"
