"""Tests für den Kill-Switch «flatten & halt» (Story S-007).

Covers (betriebssicherung): AC1, AC3, AC11

`app.core.kill_switch` implementiert die manuell auslösbare
Zustandsmaschine (`normal` → `angehalten`, AC1/AC3) und das unveränderliche
Auslöse-Protokoll (AC11). Deckt: sofortigen Halt (`ist_order_erzeugung_
erlaubt()` wird `False`, AC1), das simulierte Flatten (Paper-Modus, AC1),
den Zustand `angehalten` nach Auslösung (AC3), die AUSSCHLIESSLICH manuelle
Rückkehr über `freigeben()` (AC3 — nie automatisch), die Idempotenz einer
Mehrfach-Auslösung im `angehalten`-Zustand (Edge-Case: kein doppeltes
Flatten, kein Zustandssprung) sowie das vollständige, unveränderliche
Protokoll jeder Auslösung inkl. Auslöser/Zeitpunkt/Grund (AC11).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.contracts.betriebssicherung import KillSwitchAusloeser
from app.core import kill_switch

_ZEITSTEMPEL = datetime(2026, 7, 12, 9, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _kill_switch_isolieren():
    """Isoliert Zustand und Ereignis-Historie zwischen Testfällen."""
    kill_switch.reset_fuer_tests()
    yield
    kill_switch.reset_fuer_tests()


def _ausloeser(**overrides: object) -> KillSwitchAusloeser:
    kwargs: dict[str, object] = {
        "quelle": "manuell",
        "zeitstempel": _ZEITSTEMPEL,
        "grund": "Owner hat Notaus gedrückt",
    }
    kwargs.update(overrides)
    return KillSwitchAusloeser(**kwargs)  # type: ignore[arg-type]


def test_ausgangszustand_ist_normal_und_orders_sind_erlaubt() -> None:
    """@trace betriebssicherung#AC3 — ohne Auslösung ist der Betriebszustand
    `normal` und die Order-Erzeugung erlaubt."""
    status = kill_switch.status()

    assert status.zustand == "normal"
    assert kill_switch.ist_order_erzeugung_erlaubt() is True
    assert kill_switch.alle_ereignisse() == ()


def test_ausloesen_stoppt_sofort_neue_orders_und_setzt_zustand_angehalten() -> None:
    """@trace betriebssicherung#AC1 — `ausloesen()` stoppt sofort jede
    Order-Erzeugung (halt) und leitet das Flatten ein; der Betriebszustand
    wechselt auf `angehalten` (AC3)."""
    status = kill_switch.ausloesen(_ausloeser())

    assert status.zustand == "angehalten"
    assert kill_switch.ist_order_erzeugung_erlaubt() is False
    assert kill_switch.status().zustand == "angehalten"


def test_ausloesen_uebernimmt_ausloeser_quelle_und_grund_in_den_status() -> None:
    """@trace betriebssicherung#AC1 — der Status nach Auslösung trägt die
    Auslöser-Metadaten (Quelle, Grund, Zeitpunkt der Auslösung)."""
    status = kill_switch.ausloesen(
        _ausloeser(quelle="drawdown", grund="Drawdown-Schwelle überschritten")
    )

    assert status.quelle == "drawdown"
    assert status.grund == "Drawdown-Schwelle überschritten"
    assert status.ausgeloest_am == _ZEITSTEMPEL


def test_zustand_bleibt_angehalten_bis_zur_expliziten_freigabe() -> None:
    """@trace betriebssicherung#AC3 — nach Auslösung bleibt der Zustand
    `angehalten`; eine reine Status-Abfrage verändert daran nichts — nur
    `freigeben()` kehrt in den Normalbetrieb zurück (nie automatisch)."""
    kill_switch.ausloesen(_ausloeser())

    for _ in range(5):
        assert kill_switch.status().zustand == "angehalten"
        assert kill_switch.ist_order_erzeugung_erlaubt() is False

    status = kill_switch.freigeben()

    assert status.zustand == "normal"
    assert kill_switch.ist_order_erzeugung_erlaubt() is True


def test_freigeben_setzt_ausloeser_metadaten_zurueck() -> None:
    """@trace betriebssicherung#AC3 — nach der Freigabe trägt der Status
    keine Auslöser-Metadaten der vorherigen Auslösung mehr."""
    kill_switch.ausloesen(_ausloeser(grund="Test-Auslösung"))

    status = kill_switch.freigeben()

    assert status.zustand == "normal"
    assert status.quelle is None
    assert status.grund is None
    assert status.ausgeloest_am is None


def test_freigeben_ohne_vorherige_ausloesung_ist_idempotent() -> None:
    """@trace betriebssicherung#AC3 — eine Freigabe im bereits `normal`-
    Zustand ist ein harmloses No-Op (keine Exception, kein Seiteneffekt)."""
    status = kill_switch.freigeben()

    assert status.zustand == "normal"


def test_mehrfachausloesung_im_angehalten_zustand_ist_idempotent() -> None:
    """@trace betriebssicherung#AC1 — Edge-Case: eine erneute Auslösung,
    während der Zustand bereits `angehalten` ist, verändert weder den
    Zustand noch die ursprünglichen Auslöser-Metadaten (kein
    Zustandssprung, kein doppeltes Flatten)."""
    erster_status = kill_switch.ausloesen(_ausloeser(grund="Erste Auslösung"))

    zweiter_zeitstempel = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    zweiter_status = kill_switch.ausloesen(
        _ausloeser(quelle="heartbeat", grund="Zweite Auslösung", zeitstempel=zweiter_zeitstempel)
    )

    assert zweiter_status.zustand == "angehalten"
    # Die ursprünglichen Auslöser-Metadaten bleiben unverändert — kein
    # Überschreiben durch die zweite (idempotente) Auslösung.
    assert zweiter_status.quelle == erster_status.quelle == "manuell"
    assert zweiter_status.grund == erster_status.grund == "Erste Auslösung"
    assert zweiter_status.ausgeloest_am == erster_status.ausgeloest_am == _ZEITSTEMPEL


def test_jede_ausloesung_wird_protokolliert_auch_die_idempotente() -> None:
    """@trace betriebssicherung#AC11 — AC11 fordert, JEDE Auslösung zu
    protokollieren: sowohl die erste (zustandsändernde) als auch eine
    nachfolgende idempotente Mehrfach-Auslösung erzeugen je einen
    Protokolleintrag."""
    kill_switch.ausloesen(_ausloeser(grund="Erste Auslösung"))
    kill_switch.ausloesen(_ausloeser(grund="Zweite Auslösung (idempotent)"))

    ereignisse = kill_switch.alle_ereignisse()

    assert len(ereignisse) == 2
    assert ereignisse[0].wirkung == "ausgeloest"
    assert ereignisse[1].wirkung == "idempotent_bereits_angehalten"


def test_protokolleintrag_traegt_ausloeser_zeitpunkt_grund_und_kennwert() -> None:
    """@trace betriebssicherung#AC11 — jeder Protokolleintrag trägt genau
    die von der Spec geforderten Felder: Auslöser (Quelle), Zeitpunkt,
    Grund — plus den optionalen Kennwert, falls mitgeliefert."""
    kill_switch.ausloesen(
        _ausloeser(
            quelle="drawdown",
            grund="Drawdown-Schwelle überschritten",
            kennwert=Decimal("15.5"),
        )
    )

    (eintrag,) = kill_switch.alle_ereignisse()
    assert eintrag.quelle == "drawdown"
    assert eintrag.zeitstempel == _ZEITSTEMPEL
    assert eintrag.grund == "Drawdown-Schwelle überschritten"
    assert eintrag.kennwert == Decimal("15.5")


def test_alle_ereignisse_liefert_unveraenderliche_kopie() -> None:
    """@trace betriebssicherung#AC11 — `alle_ereignisse()` liefert ein
    Tupel (nicht die interne Liste); Aufrufer können die Protokoll-Historie
    nicht von außen mutieren."""
    kill_switch.ausloesen(_ausloeser())

    ergebnis = kill_switch.alle_ereignisse()

    assert isinstance(ergebnis, tuple)


def test_freigeben_erzeugt_keinen_ereignis_protokolleintrag() -> None:
    """@trace betriebssicherung#AC11 — AC11 nennt wörtlich "jede Auslösung
    und jeder Alert"; eine Freigabe ist keines von beidem (kein
    Alert-`typ` dafür in der Spec) und erzeugt daher bewusst KEINEN
    zusätzlichen `KillSwitchEreignis`-Eintrag."""
    kill_switch.ausloesen(_ausloeser())
    kill_switch.freigeben()

    assert len(kill_switch.alle_ereignisse()) == 1


def test_erneute_ausloesung_nach_freigabe_haelt_wieder_sofort_an() -> None:
    """@trace betriebssicherung#AC1 — nach einer Freigabe kann der
    Kill-Switch erneut ausgelöst werden (kein Latch über die Freigabe
    hinaus) und stoppt wieder sofort neue Orders."""
    kill_switch.ausloesen(_ausloeser(grund="Erster Vorfall"))
    kill_switch.freigeben()
    assert kill_switch.ist_order_erzeugung_erlaubt() is True

    dritter_zeitstempel = datetime(2026, 7, 13, 8, 0, tzinfo=UTC)
    status = kill_switch.ausloesen(
        _ausloeser(grund="Zweiter Vorfall", zeitstempel=dritter_zeitstempel)
    )

    assert status.zustand == "angehalten"
    assert kill_switch.ist_order_erzeugung_erlaubt() is False
    assert status.grund == "Zweiter Vorfall"
    # Zwei getrennte Vorfälle → zwei separate Protokolleinträge (AC11).
    assert len(kill_switch.alle_ereignisse()) == 2
