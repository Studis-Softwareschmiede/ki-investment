"""Tests für die interne Alert-Sammlung (Story S-025).

Covers (betriebssicherung): AC4, AC5

`app.core.alerts` ist die von `app.core.heartbeat` (AC4) und
`app.core.drawdown_monitor` (AC5) gemeinsam genutzte in-memory
Alert-Sammlung + Callback-Andockstelle für den künftigen
Benachrichtigungskanal (AC7, S-026, Nicht-Ziel dieser Story). Deckt: Alerts
landen in der Historie (`alle_alerts`), registrierte Callbacks werden
synchron aufgerufen, ein fehlschlagender Callback blockiert weder die
Historie noch andere Callbacks.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.contracts.betriebssicherung import Alert
from app.core import alerts

_ZEITSTEMPEL = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _alerts_isolieren():
    """Isoliert Alert-Historie und Callbacks zwischen Testfällen."""
    alerts.reset_fuer_tests()
    yield
    alerts.reset_fuer_tests()


def _alert(**overrides: object) -> Alert:
    kwargs: dict[str, object] = {
        "typ": "drawdown",
        "schwere": "warn",
        "nachricht": "Testfall",
        "zeitstempel": _ZEITSTEMPEL,
    }
    kwargs.update(overrides)
    return Alert(**kwargs)  # type: ignore[arg-type]


def test_melde_haengt_alert_an_die_historie_an() -> None:
    """@trace betriebssicherung#AC4,AC5 — `melde()` fügt den Alert der
    in-memory Historie hinzu; `alle_alerts()` liefert alle bisher
    gemeldeten Alerts in Reihenfolge."""
    alerts.melde(_alert(nachricht="Erster"))
    alerts.melde(_alert(nachricht="Zweiter"))

    ergebnis = alerts.alle_alerts()

    assert len(ergebnis) == 2
    assert ergebnis[0].nachricht == "Erster"
    assert ergebnis[1].nachricht == "Zweiter"


def test_alle_alerts_liefert_unveraenderliche_kopie() -> None:
    """@trace betriebssicherung#AC4,AC5 — `alle_alerts()` liefert ein Tupel,
    keine Referenz auf die interne Liste."""
    alerts.melde(_alert())

    assert isinstance(alerts.alle_alerts(), tuple)


def test_registrierter_callback_wird_synchron_mit_dem_alert_aufgerufen() -> None:
    """@trace betriebssicherung#AC4,AC5 — die Andockstelle für den künftigen
    Benachrichtigungskanal (S-026, AC7): ein registrierter Callback erhält
    genau den gemeldeten `Alert`."""
    empfangen: list[Alert] = []
    alerts.registriere_callback(empfangen.append)

    alert = _alert(nachricht="An Kanal")
    alerts.melde(alert)

    assert empfangen == [alert]


def test_fehlschlagender_callback_blockiert_weder_historie_noch_andere_callbacks() -> None:
    """@trace betriebssicherung#AC4,AC5 — NFR „Verfügbarkeit": ein
    fehlschlagender (künftiger) Benachrichtigungskanal darf die
    Überwachung selbst nicht blockieren."""
    empfangen: list[Alert] = []

    def _kaputter_callback(_: Alert) -> None:
        raise RuntimeError("Kanal nicht erreichbar")

    alerts.registriere_callback(_kaputter_callback)
    alerts.registriere_callback(empfangen.append)

    alerts.melde(_alert())

    assert len(alerts.alle_alerts()) == 1
    assert len(empfangen) == 1


def test_entferne_callback_stoppt_weitere_aufrufe() -> None:
    """@trace betriebssicherung#AC4,AC5 — `entferne_callback()` deregistriert
    einen zuvor registrierten Callback."""
    empfangen: list[Alert] = []
    alerts.registriere_callback(empfangen.append)
    alerts.entferne_callback(empfangen.append)

    alerts.melde(_alert())

    assert empfangen == []
