"""Tests für die Ereignis-Erzeugung (Story S-033).

Covers (depot-ueberwachung): AC5, AC6

`app.domain.depot_ueberwachung.ereignis_erzeugung
.erzeuge_ueberwachungsereignisse` erzeugt bei Schwellenüberschreitung ein
Überwachungs-Ereignis mit Titel, Ereignistyp, auslösenden Rohwerten und
Zeitstempel (AC6) — kein Ereignis ohne Schwellenüberschreitung (A2), keine
Doppel-Weitergabe bei mehreren relevanten News desselben Titels
(Bündelungs-Edge-Case), und die Funktion trifft strukturell keinen
Kauf-/Verkaufs-Entscheid (reine DTO-Rückgabe, kein Order-/Positions-
Aufruf, kein `Session`-Parameter)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.contracts.depot_ueberwachung import RohNewsEreignis, TitelSignalRohdaten
from app.domain.depot_ueberwachung.ereignis_erzeugung import erzeuge_ueberwachungsereignisse

_JETZT = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _news(titel_id: str, text: str) -> RohNewsEreignis:
    return RohNewsEreignis(titel_id=titel_id, text=text, quelle="NewsAPI", beobachtet_am=_JETZT)


def test_relevante_news_erzeugt_news_katalysator_ereignis() -> None:
    """@trace depot-ueberwachung#AC6 — eine (AC4-)relevante News erzeugt
    ein Ereignis mit Titel, Ereignistyp, Rohwerten und Zeitstempel."""
    rohdaten = TitelSignalRohdaten(
        titel_id="AAPL", news=(_news("AAPL", "AAPL meldet Insolvenz einer Tochtergesellschaft"),)
    )
    [ereignis] = erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT)
    assert ereignis.titel_id == "AAPL"
    assert ereignis.ereignistyp == "news_katalysator"
    assert ereignis.zeitstempel == _JETZT
    assert ereignis.rohwerte["anzahl_treffer"] == "1"
    assert ereignis.quellen_id == "NewsAPI"


def test_mehrere_relevante_news_desselben_titels_werden_zu_einem_ereignis_gebuendelt() -> None:
    """@trace depot-ueberwachung#AC6 — Edge-Case: mehrere Signale
    desselben Titels im selben Zyklus werden zu EINEM Ereignis je
    Ereignistyp gebündelt (keine Doppel-Weitergabe)."""
    rohdaten = TitelSignalRohdaten(
        titel_id="AAPL",
        news=(
            _news("AAPL", "AAPL meldet Insolvenz einer Tochtergesellschaft"),
            _news("AAPL", "Hack bei AAPL-Zulieferer entdeckt"),
        ),
    )
    ereignisse = erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT)
    assert len(ereignisse) == 1
    assert ereignisse[0].rohwerte["anzahl_treffer"] == "2"


def test_irrelevante_news_erzeugt_kein_ereignis() -> None:
    """@trace depot-ueberwachung#AC6 — deckt A2: kein Signal über der
    Schwelle -> kein Ereignis, keine Weitergabe."""
    rohdaten = TitelSignalRohdaten(
        titel_id="AAPL", news=(_news("AAPL", "Quartalszahlen im Rahmen der Erwartungen"),)
    )
    assert erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT) == ()


def test_kurssturz_ueber_der_schwelle_erzeugt_ereignis_marktkontext_normiert() -> None:
    """@trace depot-ueberwachung#AC6 — AC5-Normierung fliesst in die
    Schwellenprüfung ein: -10 % an einem -8 %-Markttag (normiert -2 %,
    unter der 5 %-Default-Schwelle) erzeugt KEIN Ereignis, -10 % an einem
    flachen Tag (normiert -10 %, über der Schwelle) SCHON."""
    an_starkem_markttag = TitelSignalRohdaten(
        titel_id="AAPL", kursbewegung=Decimal("-0.10"), marktbewegung=Decimal("-0.08")
    )
    an_flachem_markttag = TitelSignalRohdaten(
        titel_id="MSFT", kursbewegung=Decimal("-0.10"), marktbewegung=Decimal("0")
    )
    ereignisse = erzeuge_ueberwachungsereignisse(
        [an_starkem_markttag, an_flachem_markttag], jetzt=_JETZT
    )
    assert [e.titel_id for e in ereignisse] == ["MSFT"]
    assert ereignisse[0].ereignistyp == "relativer_kurssturz"


def test_kurssturz_ohne_marktreferenz_faellt_auf_absolutwert_zurueck() -> None:
    """@trace depot-ueberwachung#AC5/AC6 — fehlt der Marktreferenz-Wert,
    wird konservativ der Absolutwert gegen die Schwelle geprüft."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL", kursbewegung=Decimal("-0.10"))
    [ereignis] = erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT)
    assert ereignis.ereignistyp == "relativer_kurssturz"


def test_relative_kursrally_erzeugt_keinen_kurssturz() -> None:
    """@trace depot-ueberwachung#AC5,AC6 — steigt der Titel STÄRKER als der
    Markt (positive normierte Bewegung), ist das KEIN Kurssturz: ein
    `relativer_kurssturz`-Ereignis entsteht nur bei Abwärtsbewegung, nicht
    aus dem Betrag der Übertreibung nach oben."""
    rally = TitelSignalRohdaten(
        titel_id="NVDA", kursbewegung=Decimal("0.15"), marktbewegung=Decimal("0")
    )
    assert erzeuge_ueberwachungsereignisse([rally], jetzt=_JETZT) == ()


def test_partieller_schwellen_override_mergt_mit_defaults() -> None:
    """@trace depot-ueberwachung#AC6 — ein partieller `schwellen`-Override
    setzt NUR die genannten Ereignistypen; alle übrigen behalten ihren
    Default-Schwellwert (Merge mit `DEFAULT_EREIGNIS_SCHWELLEN`, kein
    Ersetzen des ganzen Mappings). Der Override senkt hier nur die
    Kurssturz-Schwelle; `momentum_verlust` bleibt auf dem Default 0.5 und
    löst bei 0.6 weiterhin aus (bei Ersetzen wäre seine Schwelle weg → kein
    Ereignis)."""
    titel = TitelSignalRohdaten(titel_id="AAPL", momentum_wert=Decimal("0.6"))
    ereignisse = erzeuge_ueberwachungsereignisse(
        [titel], schwellen={"relativer_kurssturz": Decimal("0.01")}, jetzt=_JETZT
    )
    assert [e.ereignistyp for e in ereignisse] == ["momentum_verlust"]


def test_sentiment_kippen_ueber_schwelle_erzeugt_ereignis() -> None:
    """@trace depot-ueberwachung#AC6 — ein Sentiment-Wert über der
    konfigurierten Schwelle erzeugt ein `sentiment_kippen`-Ereignis."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL", sentiment_wert=Decimal("0.9"))
    [ereignis] = erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT)
    assert ereignis.ereignistyp == "sentiment_kippen"
    assert ereignis.rohwerte == {"wert": "0.9", "schwelle": "0.5"}


def test_wert_genau_an_der_schwelle_erzeugt_kein_ereignis() -> None:
    """@trace depot-ueberwachung#AC6 — Grenzfall: ein Wert GENAU an der
    Schwelle löst kein Ereignis aus (STRIKT `>`)."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL", momentum_wert=Decimal("0.5"))
    assert erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT) == ()


def test_on_chain_abfluss_ueber_schwelle_erzeugt_ereignis() -> None:
    """@trace depot-ueberwachung#AC6 — AC3-Zusatzgrösse für Krypto
    (`on_chain_abfluesse`) erzeugt bei Schwellenüberschreitung ein
    `on_chain_abfluss`-Ereignis."""
    rohdaten = TitelSignalRohdaten(titel_id="BTC", on_chain_abfluss_wert=Decimal("1.5"))
    [ereignis] = erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT)
    assert ereignis.ereignistyp == "on_chain_abfluss"


def test_konfigurierbare_schwelle_ersetzt_default_fuer_diesen_ereignistyp() -> None:
    """@trace depot-ueberwachung#AC6 — Ereignistyp-Schwellen sind
    konfigurierbar: eine engere Schwelle lässt einen zuvor
    unterschwelligen Wert ein Ereignis auslösen."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL", momentum_wert=Decimal("0.3"))
    assert erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT) == ()
    ereignisse = erzeuge_ueberwachungsereignisse(
        [rohdaten], schwellen={"momentum_verlust": Decimal("0.2")}, jetzt=_JETZT
    )
    assert len(ereignisse) == 1


def test_ohne_jegliches_signal_ueber_der_schwelle_bleibt_titel_ereignislos() -> None:
    """@trace depot-ueberwachung#AC6 — deckt A2: ein Titel ganz ohne
    Rohdaten (alle Felder `None`/leer) erzeugt kein Ereignis."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL")
    assert erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT) == ()


def test_erzeugung_trifft_strukturell_keinen_kauf_verkaufs_entscheid() -> None:
    """@trace depot-ueberwachung#AC6 — "Das Modul trifft dabei selbst
    keinen Kauf-/Verkaufs-Entscheid": die Funktion hat keinen Zugriff auf
    eine DB-Session/Order-/Positions-Schnittstelle — strukturell
    unmöglich, einen Trade auszulösen; sie liefert ausschliesslich
    `UeberwachungsEreignis`-DTOs zurück."""
    import inspect

    signatur = inspect.signature(erzeuge_ueberwachungsereignisse)
    assert "session" not in signatur.parameters
    rohdaten = TitelSignalRohdaten(titel_id="AAPL", momentum_wert=Decimal("0.9"))
    ereignisse = erzeuge_ueberwachungsereignisse([rohdaten], jetzt=_JETZT)
    assert all(hasattr(e, "titel_id") for e in ereignisse)
