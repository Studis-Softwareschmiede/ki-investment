"""Tests für die Ereignis-Auswertung `app.orchestration.depot_ueberwachung
.werte_monitoring_ereignisse_aus` (Story S-033).

Covers (depot-ueberwachung): AC4, AC5, AC6, AC7

Verdrahtet den Keyword-/Ereignis-Filter (AC4), die Marktkontext-
Normierung (AC5) und die Ereignis-Erzeugung (AC6,
`app.domain.depot_ueberwachung.ereignis_erzeugung`) mit der Alert-
Fatigue-Tageskennzahl (AC7, `app.core.monitoring_kennzahlen`) zu einem
End-to-End-Ergebnis (`MonitoringEreignisAuswertung`)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.config import get_settings
from app.contracts.depot_ueberwachung import RohNewsEreignis, TitelSignalRohdaten
from app.core import monitoring_kennzahlen
from app.orchestration.depot_ueberwachung import werte_monitoring_ereignisse_aus

_JETZT = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolieren():
    monitoring_kennzahlen.reset_fuer_tests()
    get_settings.cache_clear()
    yield
    monitoring_kennzahlen.reset_fuer_tests()
    get_settings.cache_clear()


def test_relevante_news_erzeugt_ereignis_und_zaehlt_in_der_tageskennzahl() -> None:
    """@trace depot-ueberwachung#AC4,AC6,AC7 — eine relevante News erzeugt
    ein Ereignis UND erhöht die Alert-Fatigue-Tageskennzahl um 1."""
    rohdaten = TitelSignalRohdaten(
        titel_id="AAPL",
        news=(
            RohNewsEreignis(
                titel_id="AAPL",
                text="AAPL meldet Insolvenz einer Tochtergesellschaft",
                quelle="NewsAPI",
                beobachtet_am=_JETZT,
            ),
        ),
    )

    auswertung = werte_monitoring_ereignisse_aus([rohdaten], jetzt=_JETZT)

    assert len(auswertung.ereignisse) == 1
    assert auswertung.ereignisse[0].ereignistyp == "news_katalysator"
    assert auswertung.kennzahl.ereignisse_pro_tag == 1
    assert auswertung.kennzahl.zu_sensibel is False


def test_kein_signal_ueber_der_schwelle_erzeugt_keine_ereignisse_und_kennzahl_bleibt_null() -> None:
    """@trace depot-ueberwachung#AC6,AC7 — deckt A2: kein relevantes
    Signal -> keine Ereignisse, Tageskennzahl bleibt 0."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL")

    auswertung = werte_monitoring_ereignisse_aus([rohdaten], jetzt=_JETZT)

    assert auswertung.ereignisse == ()
    assert auswertung.kennzahl.ereignisse_pro_tag == 0


def test_marktkontext_normierte_kursbewegung_fliesst_in_die_ereignis_erzeugung_ein() -> None:
    """@trace depot-ueberwachung#AC5,AC6 — die marktkontext-normierte
    Bewertung entscheidet über die Ereignis-Erzeugung: -10 % an einem
    -8 %-Markttag (normiert -2 %) bleibt unter der Default-Schwelle."""
    rohdaten = TitelSignalRohdaten(
        titel_id="AAPL", kursbewegung=Decimal("-0.10"), marktbewegung=Decimal("-0.08")
    )

    auswertung = werte_monitoring_ereignisse_aus([rohdaten], jetzt=_JETZT)

    assert auswertung.ereignisse == ()


def test_elf_ereignisse_am_selben_tag_signalisieren_zu_sensibel() -> None:
    """@trace depot-ueberwachung#AC7 — mehrere Titel mit je einem
    schwellenüberschreitenden Signal am selben Tag summieren sich in der
    Tageskennzahl; überschreitet die Summe den Default-Schwellwert (10),
    wird `zu_sensibel=True` signalisiert."""
    rohdaten = [
        TitelSignalRohdaten(titel_id=f"TITEL-{i}", momentum_wert=Decimal("0.9")) for i in range(11)
    ]

    auswertung = werte_monitoring_ereignisse_aus(rohdaten, jetzt=_JETZT)

    assert len(auswertung.ereignisse) == 11
    assert auswertung.kennzahl.ereignisse_pro_tag == 11
    assert auswertung.kennzahl.zu_sensibel is True


def test_ohne_jetzt_wird_die_aktuelle_zeit_verwendet() -> None:
    """@trace depot-ueberwachung#AC6 — `jetzt=None` (Default) verwendet
    die aktuelle Zeit für den Ereignis-Zeitstempel."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL", momentum_wert=Decimal("0.9"))

    auswertung = werte_monitoring_ereignisse_aus([rohdaten])

    [ereignis] = auswertung.ereignisse
    assert (datetime.now(UTC) - ereignis.zeitstempel).total_seconds() < 5


def test_fehlende_marktreferenz_wird_als_marktkontext_fallback_protokolliert() -> None:
    """@trace depot-ueberwachung#AC5 — fehlt zu einer Kursbewegung der
    Marktreferenz-Wert, fällt die Normierung auf die Absolut-Bewegung zurück;
    dies wird protokolliert (Spec AC5 Edge-Case "und dies protokolliert"),
    statt still zu bleiben."""
    rohdaten = TitelSignalRohdaten(titel_id="AAPL", kursbewegung=Decimal("-0.10"))

    auswertung = werte_monitoring_ereignisse_aus([rohdaten], jetzt=_JETZT)

    assert [(e.titel_id, e.grund) for e in auswertung.protokoll] == [
        ("AAPL", "marktkontext_fallback")
    ]


def test_vorhandene_marktreferenz_erzeugt_keinen_fallback_eintrag() -> None:
    """@trace depot-ueberwachung#AC5 — mit vorhandenem Marktreferenz-Wert
    bleibt das Fallback-Protokoll leer."""
    rohdaten = TitelSignalRohdaten(
        titel_id="MSFT", kursbewegung=Decimal("-0.10"), marktbewegung=Decimal("-0.02")
    )

    auswertung = werte_monitoring_ereignisse_aus([rohdaten], jetzt=_JETZT)

    assert auswertung.protokoll == ()
