"""Tests für die portfolioweite Drawdown-Überwachung (Story S-025, S-068).

Covers (betriebssicherung): AC2, AC5
Covers (frontend-cockpit): AC8 — `status()` (S-068), die seiteneffektfreie
Zustandsabfrage für den System-Status-Endpunkt.

`app.core.drawdown_monitor` implementiert AC5 (laufende Überwachung,
unabhängig konfigurierbare Alert-/Kill-Schwellen) und AC2 (automatischer
Kill-Switch-Trigger bei Überschreiten der Kill-Schwelle, deckt A1). Deckt
zusätzlich den Edge-Case „fehlender Depot-Stand → Überwachungslücke,
nicht stillschweigend 'kein Drawdown'" inkl. Cold-Start ohne Baseline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.config import get_settings
from app.core import alerts, drawdown_monitor, kill_switch

_T0 = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolieren():
    """Isoliert Equity-Zustand, Alert-Historie und Kill-Switch-Zustand
    zwischen Testfällen; Settings-Cache bleibt unangetastet (Defaults
    werden in den Tests nicht überschrieben)."""
    drawdown_monitor.reset_fuer_tests()
    alerts.reset_fuer_tests()
    kill_switch.reset_fuer_tests()
    yield
    drawdown_monitor.reset_fuer_tests()
    alerts.reset_fuer_tests()
    kill_switch.reset_fuer_tests()


def test_ohne_jemals_gemeldeten_equity_stand_ist_es_eine_ueberwachungsluecke() -> None:
    """@trace betriebssicherung#AC5 — Cold-Start/Edge-Case: ohne jemals
    gemeldeten Depot-Stand wird KEIN Drawdown berechnet (kein
    stillschweigendes „kein Drawdown"), sondern eine Überwachungslücke
    gemeldet — und der Kill-Switch bleibt unangetastet (kein
    Drawdown-Fehlalarm bei leerer Equity-Kurve)."""
    status = drawdown_monitor.pruefe_drawdown(jetzt=_T0)

    assert status.ueberwachungsluecke is True
    assert status.aktueller_stand is None
    assert status.drawdown_pct is None
    assert status.kill_ausgeloest is False
    assert kill_switch.status().zustand == "normal"

    (alert,) = alerts.alle_alerts()
    assert alert.typ == "drawdown"
    assert alert.schwere == "warn"


def test_am_hoechststand_ist_der_drawdown_null_ohne_alert() -> None:
    """@trace betriebssicherung#AC5 — direkt nach der ersten
    Equity-Meldung entspricht der aktuelle Stand dem Höchststand
    (Drawdown 0 %); unterhalb beider Schwellen entsteht kein Alert."""
    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), _T0)

    status = drawdown_monitor.pruefe_drawdown(jetzt=_T0)

    assert status.ueberwachungsluecke is False
    assert status.drawdown_pct == Decimal("0")
    assert status.kill_ausgeloest is False
    assert alerts.alle_alerts() == ()


def test_drawdown_ueber_alert_schwelle_aber_unter_kill_schwelle_meldet_nur_alert() -> None:
    """@trace betriebssicherung#AC5 — überschreitet der Drawdown die
    Alert-Schwelle (Default 10 %), aber NICHT die Kill-Schwelle (Default
    20 %), wird ein Alert gemeldet, OHNE den Kill-Switch auszulösen —
    die beiden Schwellen sind unabhängig konfigurierbar."""
    settings = get_settings()
    assert settings.drawdown_alert_schwelle < settings.drawdown_kill_schwelle

    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), _T0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("85000"), _T0)  # -15 %

    status = drawdown_monitor.pruefe_drawdown(jetzt=_T0)

    assert status.drawdown_pct == Decimal("0.15")
    assert status.kill_ausgeloest is False
    assert kill_switch.status().zustand == "normal"

    (alert,) = alerts.alle_alerts()
    assert alert.typ == "drawdown"
    assert alert.schwere == "warn"


def test_drawdown_ueber_kill_schwelle_loest_bestehenden_kill_switch_aus() -> None:
    """@trace betriebssicherung#AC2 — überschreitet der Drawdown die
    Kill-Schwelle (Default 20 %), wird das BESTEHENDE
    `app.core.kill_switch.ausloesen()` automatisch mit Quelle `"drawdown"`
    aufgerufen (deckt A1) und die Order-Erzeugung sofort gestoppt."""
    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), _T0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("75000"), _T0)  # -25 %

    status = drawdown_monitor.pruefe_drawdown(jetzt=_T0)

    assert status.kill_ausgeloest is True
    kill_status = kill_switch.status()
    assert kill_status.zustand == "angehalten"
    assert kill_status.quelle == "drawdown"
    assert kill_switch.ist_order_erzeugung_erlaubt() is False

    # Zwei Alerts für dieses eine Ereignis: der Drawdown-Alert selbst
    # (dieses Modul) PLUS der Kill-Alert, den `kill_switch.ausloesen()`
    # bei JEDER Auslösung meldet (S-026, AC7).
    alle = alerts.alle_alerts()
    assert len(alle) == 2
    drawdown_alert = next(a for a in alle if a.typ == "drawdown")
    kill_alert = next(a for a in alle if a.typ == "kill")
    assert drawdown_alert.schwere == "critical"
    assert kill_alert.schwere == "critical"


def test_drawdown_genau_auf_der_schwelle_loest_keinen_alarm_aus() -> None:
    """@trace betriebssicherung#AC5 — Edge-Case (analog Halluzinations-KPI):
    ein Drawdown GENAU auf der Alert-Schwelle löst KEINEN Alarm aus
    (Vergleich ist STRIKT `>`)."""
    settings = get_settings()
    hoechststand = Decimal("100000")
    aktuell = hoechststand * (1 - Decimal(str(settings.drawdown_alert_schwelle)))

    drawdown_monitor.aktualisiere_equity_stand(hoechststand, _T0)
    drawdown_monitor.aktualisiere_equity_stand(aktuell, _T0)

    status = drawdown_monitor.pruefe_drawdown(jetzt=_T0)

    assert status.drawdown_pct == Decimal(str(settings.drawdown_alert_schwelle))
    assert alerts.alle_alerts() == ()
    assert status.kill_ausgeloest is False


def test_hoechststand_bleibt_ueber_nachfolgend_niedrigere_werte_erhalten() -> None:
    """@trace betriebssicherung#AC5 — der Drawdown wird gegen den laufenden
    Höchststand (High-Water-Mark) gemessen, nicht gegen den zuletzt
    gemeldeten Wert — ein Rückgang NACH dem Höchststand darf den
    Höchststand selbst nicht mehr senken."""
    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), _T0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("90000"), _T0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("95000"), _T0)

    status = drawdown_monitor.pruefe_drawdown(jetzt=_T0)

    assert status.hoechststand == Decimal("100000")
    assert status.aktueller_stand == Decimal("95000")
    assert status.drawdown_pct == Decimal("0.05")


def test_status_ohne_equity_stand_ist_ueberwachungsluecke_ohne_alert() -> None:
    """@trace frontend-cockpit#AC8 — `status()` meldet den Cold-Start-Fall
    genauso wie `pruefe_drawdown()` (`ueberwachungsluecke=True`), löst aber
    KEINEN Alert aus (reiner Read, keine Nebenwirkung)."""
    status = drawdown_monitor.status()

    assert status.ueberwachungsluecke is True
    assert status.aktueller_stand is None
    assert status.drawdown_pct is None
    assert status.kill_ausgeloest is False
    assert alerts.alle_alerts() == ()


def test_status_ueber_kill_schwelle_loest_weder_alert_noch_kill_switch_aus() -> None:
    """@trace frontend-cockpit#AC8 — `status()` berechnet denselben
    Drawdown-Prozentsatz wie `pruefe_drawdown()`, auch weit über der
    Kill-Schwelle, löst aber NIE einen Alert oder den Kill-Switch aus
    (ein Status-Read darf den Betriebszustand nicht verändern)."""
    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), _T0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("75000"), _T0)  # -25 %

    status = drawdown_monitor.status()

    assert status.drawdown_pct == Decimal("0.25")
    assert status.kill_ausgeloest is False
    assert kill_switch.status().zustand == "normal"
    assert alerts.alle_alerts() == ()


def test_status_liest_denselben_hoechststand_wie_pruefe_drawdown() -> None:
    """@trace frontend-cockpit#AC8 — `status()` spiegelt denselben
    internen Zustand wie `pruefe_drawdown()` (High-Water-Mark bleibt über
    einen nachfolgenden Rückgang erhalten)."""
    drawdown_monitor.aktualisiere_equity_stand(Decimal("100000"), _T0)
    drawdown_monitor.aktualisiere_equity_stand(Decimal("90000"), _T0)

    status = drawdown_monitor.status()

    assert status.hoechststand == Decimal("100000")
    assert status.aktueller_stand == Decimal("90000")
    assert status.drawdown_pct == Decimal("0.1")


@pytest.mark.parametrize(
    "equity_staende",
    [
        (),  # Cold-Start: nie ein Equity-Stand gemeldet
        (Decimal("100000"),),  # am Höchststand, Drawdown 0 %
        (Decimal("100000"), Decimal("75000")),  # weit über der Kill-Schwelle
    ],
)
def test_status_und_pruefe_drawdown_liefern_deckungsgleiche_kernwerte(
    equity_staende: tuple[Decimal, ...],
) -> None:
    """@trace frontend-cockpit#AC8 — `status()` und `pruefe_drawdown()`
    teilen sich denselben Kern (`_lese_drawdown_status_unlocked`, Review-
    Finding Iteration 1): für JEDEN Zustand (Cold-Start, am Höchststand,
    weit über der Kill-Schwelle) müssen `aktueller_stand`/`hoechststand`/
    `drawdown_pct`/`ueberwachungsluecke` zwischen beiden Funktionen
    übereinstimmen — nur `kill_ausgeloest` und die Alert-/Kill-Switch-
    Nebenwirkung dürfen sich unterscheiden."""
    for stand in equity_staende:
        drawdown_monitor.aktualisiere_equity_stand(stand, _T0)

    pruef_status = drawdown_monitor.pruefe_drawdown(jetzt=_T0)
    lese_status = drawdown_monitor.status()

    assert lese_status.aktueller_stand == pruef_status.aktueller_stand
    assert lese_status.hoechststand == pruef_status.hoechststand
    assert lese_status.drawdown_pct == pruef_status.drawdown_pct
    assert lese_status.ueberwachungsluecke == pruef_status.ueberwachungsluecke
