"""Tests für die Frische-Fenster-Prüfung (Story S-032).

Covers (depot-ueberwachung): AC9

`app.domain.depot_ueberwachung.frische.ist_titel_bewertbar` deckt E1:
fehlt das Signal-Bündel eines Titels oder ist es älter als das
konfigurierte Frische-Fenster, gilt der Titel als nicht bewertbar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.contracts.dateneingang import Signal, SignalBuendel
from app.domain.depot_ueberwachung.frische import ist_titel_bewertbar

_JETZT = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
_FENSTER = timedelta(hours=24)


def _signal(beobachtet_am: datetime) -> Signal:
    return Signal(
        quelle="IBKR", wert=Decimal("100"), qualitaetsindikator="hoch", beobachtet_am=beobachtet_am
    )


def _buendel(*signale: Signal) -> SignalBuendel:
    return SignalBuendel(
        titel="AAPL",
        anlageklasse=1,
        signale=list(signale),
        liquiditaet=Decimal(len(signale)) if signale else None,
        volatilitaet=Decimal("1") if signale else None,
        quellen_metadaten=[],
    )


def test_kein_signal_buendel_ist_nicht_bewertbar() -> None:
    """@trace depot-ueberwachung#AC9 — deckt E1: `None` (Bündel fehlt
    ganz) → nicht bewertbar."""
    assert ist_titel_bewertbar(None, jetzt=_JETZT, frische_fenster=_FENSTER) is False


def test_strukturell_leeres_signal_buendel_ist_nicht_bewertbar() -> None:
    """@trace depot-ueberwachung#AC9 — deckt E1: ein Bündel ohne Signale
    (`signale=[]`) → nicht bewertbar."""
    assert ist_titel_bewertbar(_buendel(), jetzt=_JETZT, frische_fenster=_FENSTER) is False


def test_signal_innerhalb_des_frische_fensters_ist_bewertbar() -> None:
    """@trace depot-ueberwachung#AC9 — ein Signal innerhalb des
    Frische-Fensters (hier: 1h alt, Fenster 24h) → bewertbar."""
    buendel = _buendel(_signal(_JETZT - timedelta(hours=1)))
    assert ist_titel_bewertbar(buendel, jetzt=_JETZT, frische_fenster=_FENSTER) is True


def test_signal_genau_am_fensterrand_ist_noch_bewertbar() -> None:
    """@trace depot-ueberwachung#AC9 — Grenzfall: exakt am Fensterrand
    (`<=`) zählt noch als bewertbar."""
    buendel = _buendel(_signal(_JETZT - _FENSTER))
    assert ist_titel_bewertbar(buendel, jetzt=_JETZT, frische_fenster=_FENSTER) is True


def test_veraltetes_signal_ist_nicht_bewertbar() -> None:
    """@trace depot-ueberwachung#AC9 — deckt E1: ein Signal älter als das
    Frische-Fenster (hier: 25h alt, Fenster 24h) → nicht bewertbar."""
    buendel = _buendel(_signal(_JETZT - timedelta(hours=25)))
    assert ist_titel_bewertbar(buendel, jetzt=_JETZT, frische_fenster=_FENSTER) is False


def test_neuestes_von_mehreren_signalen_entscheidet() -> None:
    """@trace depot-ueberwachung#AC9 — bei mehreren Signalen zählt das
    ZEITLICH NEUESTE: ein aktuelles Signal macht den Titel bewertbar, auch
    wenn eine andere Quelle veraltet ist."""
    buendel = _buendel(
        _signal(_JETZT - timedelta(hours=48)),
        _signal(_JETZT - timedelta(hours=2)),
    )
    assert ist_titel_bewertbar(buendel, jetzt=_JETZT, frische_fenster=_FENSTER) is True
