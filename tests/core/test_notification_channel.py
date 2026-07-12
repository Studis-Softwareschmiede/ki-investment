"""Tests für den Benachrichtigungskanal (Story S-026).

Covers (betriebssicherung): AC7, AC10

`app.core.notification_channel` realisiert AC7 (den bislang nur als
Callback-Andockstelle vorbereiteten Benachrichtigungskanal, S-025): jeder
über `app.core.alerts.melde()` gemeldete Alert wird an eine injizierbare
Versandfunktion weitergereicht (Default: strukturierte Logzeile, Paper-MVP
informativ). Deckt zusätzlich AC10: schlägt der Versand fehl (Kanal nicht
erreichbar), wird der Alert persistent vorgemerkt statt verworfen und
später über `sende_ausstehende()` erneut zugestellt — unabhängig davon
bleiben Kill-Switch/Heartbeat/Drawdown voll funktionsfähig.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contracts.betriebssicherung import Alert, KillSwitchAusloeser
from app.core import alerts, kill_switch, notification_channel

_ZEITSTEMPEL = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _kanal_isolieren():
    """Isoliert Alert-Historie/Callbacks UND den Kanal-Zustand (Versand,
    Registrierungs-Flag, Zustell-Warteschlange) zwischen Testfällen.
    Reihenfolge: erst `alerts` zurücksetzen (leert die Callback-Liste dort),
    dann `notification_channel` (setzt das eigene Registrierungs-Flag
    zurück) — jeder Test registriert sich danach explizit neu."""
    alerts.reset_fuer_tests()
    notification_channel.reset_fuer_tests()
    kill_switch.reset_fuer_tests()
    yield
    alerts.reset_fuer_tests()
    notification_channel.reset_fuer_tests()
    kill_switch.reset_fuer_tests()


def _alert(**overrides: object) -> Alert:
    kwargs: dict[str, object] = {
        "typ": "drawdown",
        "schwere": "warn",
        "nachricht": "Testfall",
        "zeitstempel": _ZEITSTEMPEL,
    }
    kwargs.update(overrides)
    return Alert(**kwargs)  # type: ignore[arg-type]


def test_registriere_leitet_gemeldete_alerts_an_die_versandfunktion_weiter() -> None:
    """@trace betriebssicherung#AC7 — nach `registriere()` erreicht jeder
    über `app.core.alerts.melde()` gemeldete Alert die Versandfunktion des
    Kanals."""
    versendet: list[Alert] = []
    notification_channel.registriere(versand=versendet.append)

    alert = _alert(nachricht="Erster Alarm")
    alerts.melde(alert)

    assert versendet == [alert]


def test_registriere_ohne_versand_verwendet_standard_logkanal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """@trace betriebssicherung#AC7 — ohne explizite Versandfunktion
    verwendet der Kanal den Paper-MVP-Default (informative Logzeile über
    den dedizierten Logger `notification.channel`) — kein externer Dienst
    nötig, kein Fehler."""
    notification_channel.registriere()

    with caplog.at_level("INFO", logger="notification.channel"):
        alerts.melde(_alert(nachricht="Standard-Kanal-Test"))

    assert any("Standard-Kanal-Test" in record.message for record in caplog.records)
    assert notification_channel.ausstehende_zustellungen() == ()


def test_registriere_registriert_callback_nicht_mehrfach() -> None:
    """@trace betriebssicherung#AC7 — ein wiederholter `registriere()`-
    Aufruf hängt den Callback NICHT ein zweites Mal ein (kein doppelter
    Versand desselben Alerts), aktualisiert aber die Versandfunktion."""
    erster_versand: list[Alert] = []
    zweiter_versand: list[Alert] = []
    notification_channel.registriere(versand=erster_versand.append)
    notification_channel.registriere(versand=zweiter_versand.append)

    alerts.melde(_alert())

    assert erster_versand == []
    assert zweiter_versand == [_alert()]


def test_fehlschlagender_versand_merkt_alert_persistent_zur_zustellung_vor() -> None:
    """@trace betriebssicherung#AC10 — ist der Kanal nicht erreichbar
    (Versandfunktion wirft), wird der Alert NICHT verworfen, sondern zur
    späteren Zustellung vorgemerkt."""

    def _nicht_erreichbar(_: Alert) -> None:
        raise RuntimeError("Kanal nicht erreichbar")

    notification_channel.registriere(versand=_nicht_erreichbar)

    alert = _alert(nachricht="Sollte nachgeliefert werden")
    alerts.melde(alert)

    assert notification_channel.ausstehende_zustellungen() == (alert,)
    # Der Alert bleibt trotzdem regulär in der Alert-Historie (S-025).
    assert alert in alerts.alle_alerts()


def test_kill_switch_bleibt_bei_nicht_erreichbarem_kanal_voll_funktionsfaehig() -> None:
    """@trace betriebssicherung#AC10 — „Kill-Switch und Schutzmechanismen
    bleiben davon unabhängig funktionsfähig": ein nicht erreichbarer Kanal
    verhindert weder die Kill-Switch-Auslösung noch deren eigenen
    (ebenfalls über den Kanal gemeldeten) Alert."""

    def _immer_kaputt(_: Alert) -> None:
        raise RuntimeError("Kanal nicht erreichbar")

    notification_channel.registriere(versand=_immer_kaputt)

    status = kill_switch.ausloesen(
        KillSwitchAusloeser(quelle="manuell", zeitstempel=_ZEITSTEMPEL, grund="Notaus")
    )

    assert status.zustand == "angehalten"
    assert kill_switch.ist_order_erzeugung_erlaubt() is False
    assert len(notification_channel.ausstehende_zustellungen()) == 1


def test_sende_ausstehende_stellt_bei_wieder_erreichbarem_kanal_zu() -> None:
    """@trace betriebssicherung#AC10 — „beim nächsten erreichbaren
    Zeitpunkt zugestellt": ein erneuter `sende_ausstehende()`-Aufruf mit
    einer nun funktionierenden Versandfunktion liefert den vorgemerkten
    Alert zu und leert die Warteschlange."""

    def _kaputt(_: Alert) -> None:
        raise RuntimeError("Kanal nicht erreichbar")

    notification_channel.registriere(versand=_kaputt)
    alert = _alert(nachricht="Wird nachgeliefert")
    alerts.melde(alert)
    assert notification_channel.ausstehende_zustellungen() == (alert,)

    zugestellt_versand: list[Alert] = []
    notification_channel.registriere(versand=zugestellt_versand.append)

    zugestellt = notification_channel.sende_ausstehende()

    assert zugestellt == (alert,)
    assert zugestellt_versand == [alert]
    assert notification_channel.ausstehende_zustellungen() == ()


def test_sende_ausstehende_ohne_erneuten_erfolg_belaesst_alert_in_der_warteschlange() -> None:
    """@trace betriebssicherung#AC10 — bleibt der Kanal weiterhin nicht
    erreichbar, bleibt der Alert in der Zustell-Warteschlange (kein
    stillschweigender Verlust)."""

    def _dauerhaft_kaputt(_: Alert) -> None:
        raise RuntimeError("Kanal nicht erreichbar")

    notification_channel.registriere(versand=_dauerhaft_kaputt)
    alert = _alert()
    alerts.melde(alert)

    zugestellt = notification_channel.sende_ausstehende()

    assert zugestellt == ()
    assert notification_channel.ausstehende_zustellungen() == (alert,)


def test_sende_ausstehende_ohne_vorgemerkte_alerts_ist_ein_no_op() -> None:
    """@trace betriebssicherung#AC10 — ohne ausstehende Alerts liefert
    `sende_ausstehende()` ein leeres Tupel, ohne Fehler."""
    notification_channel.registriere()

    assert notification_channel.sende_ausstehende() == ()
