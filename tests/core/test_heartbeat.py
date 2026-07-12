"""Tests für die Heartbeat-Überwachung je Pipeline-Modul (Story S-025).

Covers (betriebssicherung): AC4

`app.core.heartbeat` implementiert AC4: Registrierung/Ping je Modul,
Ausfallerkennung (`now − letzter_ping > intervall_soll`, STRIKT), Alert-
Erzeugung über `app.core.alerts` bei jedem erkannten Ausfall sowie den
Auto-Trigger des BESTEHENDEN `app.core.kill_switch.ausloesen()` mit Quelle
`"heartbeat"` für `kritisch=True`-Module (Deckt A2).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core import alerts, heartbeat, kill_switch

_T0 = datetime(2026, 7, 12, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolieren():
    """Isoliert Heartbeat-Registrierungen, Alert-Historie und
    Kill-Switch-Zustand zwischen Testfällen."""
    heartbeat.reset_fuer_tests()
    alerts.reset_fuer_tests()
    kill_switch.reset_fuer_tests()
    yield
    heartbeat.reset_fuer_tests()
    alerts.reset_fuer_tests()
    kill_switch.reset_fuer_tests()


def test_registriere_modul_legt_heartbeat_mit_initialem_ping_an() -> None:
    """@trace betriebssicherung#AC4 — `registriere_modul()` legt den
    Heartbeat-Vertrag `{modul_id, letzter_ping_zeitstempel, intervall_soll}`
    mit `letzter_ping_zeitstempel = jetzt` an."""
    eintrag = heartbeat.registriere_modul("ingest-fred", timedelta(minutes=5), jetzt=_T0)

    assert eintrag.modul_id == "ingest-fred"
    assert eintrag.letzter_ping_zeitstempel == _T0
    assert eintrag.intervall_soll == timedelta(minutes=5)
    assert heartbeat.status("ingest-fred") == eintrag


def test_ping_aktualisiert_letzten_ping_zeitstempel() -> None:
    """@trace betriebssicherung#AC4 — `ping()` aktualisiert den zuletzt
    gesehenen Zeitstempel eines registrierten Moduls."""
    heartbeat.registriere_modul("ingest-fred", timedelta(minutes=5), jetzt=_T0)

    neuer_ping = _T0 + timedelta(minutes=2)
    eintrag = heartbeat.ping("ingest-fred", zeitpunkt=neuer_ping)

    assert eintrag.letzter_ping_zeitstempel == neuer_ping
    assert heartbeat.status("ingest-fred").letzter_ping_zeitstempel == neuer_ping


def test_ping_auf_unregistriertem_modul_wirft_heartbeat_fehler() -> None:
    """@trace betriebssicherung#AC4 — `ping()`/`status()` auf einer nicht
    registrierten `modul_id` ist ein Aufrufer-Fehler (kein stilles
    Auto-Registrieren, keine stillschweigend erfundene Modul-Identität)."""
    with pytest.raises(heartbeat.HeartbeatFehler):
        heartbeat.ping("unbekanntes-modul")
    with pytest.raises(heartbeat.HeartbeatFehler):
        heartbeat.status("unbekanntes-modul")


def test_pruefe_ausfaelle_erkennt_keinen_ausfall_innerhalb_des_intervalls() -> None:
    """@trace betriebssicherung#AC4 — solange `now − letzter_ping <=
    intervall_soll`, wird KEIN Ausfall erkannt (kein Alert, kein
    Kill-Switch-Trigger)."""
    heartbeat.registriere_modul("ingest-fred", timedelta(minutes=5), jetzt=_T0)

    ergebnis = heartbeat.pruefe_ausfaelle(jetzt=_T0 + timedelta(minutes=5))

    assert ergebnis == ()
    assert alerts.alle_alerts() == ()
    assert kill_switch.status().zustand == "normal"


def test_pruefe_ausfaelle_erkennt_ausfall_strikt_ueber_dem_intervall() -> None:
    """@trace betriebssicherung#AC4 — überschreitet die Lücke das Intervall
    STRIKT (`>`), wird ein Ausfall erkannt und ein Alert erzeugt."""
    heartbeat.registriere_modul("ingest-fred", timedelta(minutes=5), jetzt=_T0)

    ergebnis = heartbeat.pruefe_ausfaelle(jetzt=_T0 + timedelta(minutes=5, seconds=1))

    assert len(ergebnis) == 1
    assert ergebnis[0].typ == "heartbeat"
    assert "ingest-fred" in ergebnis[0].nachricht
    assert len(alerts.alle_alerts()) == 1


def test_pruefe_ausfaelle_kritisches_modul_loest_kill_switch_aus() -> None:
    """@trace betriebssicherung#AC4 — ein Ausfall eines `kritisch=True`-
    Moduls (Default) ruft das BESTEHENDE `app.core.kill_switch.ausloesen()`
    mit Quelle `"heartbeat"` auf (deckt A2/BR-022 „... und kann den
    Kill-Switch triggern")."""
    heartbeat.registriere_modul("ingest-fred", timedelta(minutes=5), kritisch=True, jetzt=_T0)

    heartbeat.pruefe_ausfaelle(jetzt=_T0 + timedelta(minutes=10))

    status = kill_switch.status()
    assert status.zustand == "angehalten"
    assert status.quelle == "heartbeat"
    assert kill_switch.ist_order_erzeugung_erlaubt() is False


def test_pruefe_ausfaelle_unkritisches_modul_meldet_nur_alert_ohne_kill() -> None:
    """@trace betriebssicherung#AC4 — ein Ausfall eines `kritisch=False`-
    konfigurierten Moduls erzeugt einen Alert, löst aber den Kill-Switch
    NICHT aus ("je nach Kritikalität/Konfiguration")."""
    heartbeat.registriere_modul("research-scraper", timedelta(minutes=5), kritisch=False, jetzt=_T0)

    ergebnis = heartbeat.pruefe_ausfaelle(jetzt=_T0 + timedelta(minutes=10))

    assert len(ergebnis) == 1
    assert ergebnis[0].schwere == "warn"
    assert kill_switch.status().zustand == "normal"


def test_pruefe_ausfaelle_prueft_mehrere_module_unabhaengig() -> None:
    """@trace betriebssicherung#AC4 — ein gesundes Modul erzeugt keinen
    Alert, während ein zeitgleich geprüftes ausgefallenes Modul erkannt
    wird — die Prüfung ist je Modul unabhängig."""
    heartbeat.registriere_modul("gesund", timedelta(minutes=10), jetzt=_T0)
    heartbeat.registriere_modul("ausgefallen", timedelta(minutes=1), jetzt=_T0)

    ergebnis = heartbeat.pruefe_ausfaelle(jetzt=_T0 + timedelta(minutes=5))

    assert len(ergebnis) == 1
    assert "ausgefallen" in ergebnis[0].nachricht


def test_alle_heartbeats_liefert_zustand_aller_registrierten_module() -> None:
    """@trace betriebssicherung#AC4 — `alle_heartbeats()` liefert den
    aktuellen Zustand aller registrierten Module (Inspektion)."""
    heartbeat.registriere_modul("a", timedelta(minutes=5), jetzt=_T0)
    heartbeat.registriere_modul("b", timedelta(minutes=5), jetzt=_T0)

    modul_ids = {eintrag.modul_id for eintrag in heartbeat.alle_heartbeats()}

    assert modul_ids == {"a", "b"}
