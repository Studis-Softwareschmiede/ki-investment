"""Tests für den Quellenausfall-Konsum (Story S-026).

Covers (betriebssicherung): AC9

`app.core.quellenausfall` ist die betriebssicherungsseitige Konsumstelle
für Ausfall-/Veraltungs-Signale einer Datenquelle (deckt A3): meldet einen
`Alert(typ="quellenausfall")` über den Benachrichtigungskanal (AC7,
„der Ausfall wird gemeldet") und hält ein No-Evidence-No-Trade-Gate
(`ist_evidenz_verfuegbar()`), das ein künftiger Order-Pfad vor jeder
Order-Erzeugung abfragen wird — kein Trade auf fehlender Datengrundlage.
Deckt zusätzlich: kein automatischer Kill-Switch-Trigger (anders als
Heartbeat/Drawdown), die Wiederherstellung hebt das Gate ohne eigenen
Alert wieder auf, und mehrere Quellen werden unabhängig geführt.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core import alerts, kill_switch, quellenausfall

_T0 = datetime(2026, 7, 13, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolieren():
    """Isoliert Ausfall-Zustand, Alert-Historie und Kill-Switch-Zustand
    zwischen Testfällen."""
    quellenausfall.reset_fuer_tests()
    alerts.reset_fuer_tests()
    kill_switch.reset_fuer_tests()
    yield
    quellenausfall.reset_fuer_tests()
    alerts.reset_fuer_tests()
    kill_switch.reset_fuer_tests()


def test_ohne_gemeldeten_ausfall_ist_evidenz_verfuegbar() -> None:
    """@trace betriebssicherung#AC9 — ohne gemeldeten Ausfall gilt eine
    Quelle als verfügbar (Gate liefert `True`)."""
    assert quellenausfall.ist_evidenz_verfuegbar("fred") is True
    assert quellenausfall.alle_ausfaelle() == ()


def test_melde_ausfall_meldet_alert_und_sperrt_das_evidenz_gate() -> None:
    """@trace betriebssicherung#AC9 — ein gemeldeter Ausfall (deckt A3)
    meldet einen `Alert(typ="quellenausfall")` über den
    Benachrichtigungskanal UND sperrt das No-Evidence-No-Trade-Gate für
    diese Quelle (kein Trade auf fehlender Datengrundlage)."""
    alert = quellenausfall.melde_ausfall(
        "fred", "Timeout nach 3 Retries (Backoff erschöpft)", zeitstempel=_T0
    )

    assert alert.typ == "quellenausfall"
    assert "fred" in alert.nachricht
    assert quellenausfall.ist_evidenz_verfuegbar("fred") is False

    (gemeldeter_alert,) = alerts.alle_alerts()
    assert gemeldeter_alert == alert


def test_melde_ausfall_loest_keinen_kill_switch_aus() -> None:
    """@trace betriebssicherung#AC9 — anders als Heartbeat-Ausfall/Drawdown
    löst ein Quellenausfall laut Spec KEINEN automatischen Kill-Switch aus
    (Verträge nennen für `quellenausfall` nur Fallback/Alerting)."""
    quellenausfall.melde_ausfall("fred", "Ausfall", zeitstempel=_T0)

    assert kill_switch.status().zustand == "normal"
    assert kill_switch.ist_order_erzeugung_erlaubt() is True


def test_melde_wiederhergestellt_hebt_das_gate_ohne_eigenen_alert_auf() -> None:
    """@trace betriebssicherung#AC9 — eine gemeldete Wiederherstellung hebt
    die Gate-Sperre wieder auf, erzeugt aber KEINEN eigenen Alert (nur der
    Ausfall selbst ist meldenswert)."""
    quellenausfall.melde_ausfall("fred", "Ausfall", zeitstempel=_T0)
    assert quellenausfall.ist_evidenz_verfuegbar("fred") is False

    quellenausfall.melde_wiederhergestellt("fred")

    assert quellenausfall.ist_evidenz_verfuegbar("fred") is True
    assert quellenausfall.alle_ausfaelle() == ()
    assert len(alerts.alle_alerts()) == 1  # weiterhin nur der Ausfall-Alert


def test_melde_wiederhergestellt_fuer_unbekannte_quelle_ist_idempotent() -> None:
    """@trace betriebssicherung#AC9 — eine Wiederherstellungsmeldung für
    eine nie als ausgefallen gemeldete Quelle ist ein harmloses No-Op."""
    quellenausfall.melde_wiederhergestellt("unbekannte-quelle")

    assert quellenausfall.ist_evidenz_verfuegbar("unbekannte-quelle") is True


def test_mehrere_quellen_werden_unabhaengig_gefuehrt() -> None:
    """@trace betriebssicherung#AC9 — ein Ausfall EINER Quelle sperrt nicht
    das Gate anderer Quellen (unabhängige Führung je `quelle_id`)."""
    quellenausfall.melde_ausfall("fred", "Ausfall", zeitstempel=_T0)

    assert quellenausfall.ist_evidenz_verfuegbar("fred") is False
    assert quellenausfall.ist_evidenz_verfuegbar("sec-form-4") is True


def test_erneute_meldung_derselben_quelle_aktualisiert_grund_und_meldet_erneut() -> None:
    """@trace betriebssicherung#AC9 — eine erneute Ausfall-Meldung
    derselben Quelle aktualisiert den geführten Grund UND meldet einen
    weiteren Alert (jede Meldung ist ein eigenes Ereignis)."""
    quellenausfall.melde_ausfall("fred", "Erster Ausfall", zeitstempel=_T0)
    zweiter_zeitpunkt = datetime(2026, 7, 13, 10, 0, tzinfo=UTC)
    quellenausfall.melde_ausfall("fred", "Zweiter Ausfall", zeitstempel=zweiter_zeitpunkt)

    assert len(alerts.alle_alerts()) == 2
    (eintrag,) = quellenausfall.alle_ausfaelle()
    assert eintrag.grund == "Zweiter Ausfall"
    assert eintrag.gemeldet_am == zweiter_zeitpunkt
