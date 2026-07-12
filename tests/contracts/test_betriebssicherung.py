"""Tests für die Kill-Switch- + Secret-Store- + Auto-Trigger-Verträge
(Story S-007, S-008, S-025).

Covers (betriebssicherung): AC1, AC2, AC3, AC4, AC5, AC6, AC11

`app.contracts.betriebssicherung` bildet die Verträge aus
`docs/specs/betriebssicherung.md` ab, soweit sie diese Stories betreffen:
den Kill-Switch-Auslöser-Input (`KillSwitchAusloeser`, AC1), den
Betriebszustand (`Betriebszustand`/`KillSwitchStatus`, AC3), den
unveränderlichen Protokolleintrag (`KillSwitchEreignis`, AC11), den
Secret-Store-Vertrag (`Umgebung`/`SecretStoreZugang`, AC6 — Story S-008)
sowie die Auto-Trigger-Verträge `Alert` (AC4/AC5 Output),
`HeartbeatEintrag` (AC4) und `DrawdownStatus` (AC2/AC5, Story S-025). Das
tatsächliche Zustandsmaschinen-/Protokollierungs-Verhalten liegt in
`tests/core/test_kill_switch.py`; die tatsächliche Secret-Store-Auflösung
(strikte Paper/Live-Trennung) liegt in `tests/core/test_secret_store.py`;
das tatsächliche Heartbeat-/Drawdown-Verhalten liegt in
`tests/core/test_heartbeat.py`/`tests/core/test_drawdown_monitor.py` —
hier wird nur die Vertrags-/Struktur-Ebene geprüft.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.betriebssicherung import (
    Alert,
    DrawdownStatus,
    HeartbeatEintrag,
    KillSwitchAusloeser,
    KillSwitchEreignis,
    KillSwitchStatus,
    SecretStoreZugang,
)

_ZEITSTEMPEL = datetime(2026, 7, 12, 12, 0, tzinfo=UTC)


def test_kill_switch_ausloeser_akzeptiert_alle_vier_vertrags_quellen() -> None:
    """@trace betriebssicherung#AC1 — der Auslöser-Vertrag akzeptiert alle
    vier von der Spec benannten Quellen (`manuell|drawdown|heartbeat|
    extern`), auch wenn diese Story nur `"manuell"` tatsächlich auslöst —
    das Feld muss für künftige automatische Trigger andocken können."""
    for quelle in ("manuell", "drawdown", "heartbeat", "extern"):
        ausloeser = KillSwitchAusloeser(quelle=quelle, zeitstempel=_ZEITSTEMPEL, grund="Testfall")
        assert ausloeser.quelle == quelle


def test_kill_switch_ausloeser_verweigert_unbekannte_quelle() -> None:
    """@trace betriebssicherung#AC1 — eine Quelle außerhalb des Vertrags-
    Literals wird von pydantic abgelehnt (strukturelle Validierung)."""
    with pytest.raises(ValidationError):
        KillSwitchAusloeser(quelle="unbekannt", zeitstempel=_ZEITSTEMPEL, grund="x")  # type: ignore[arg-type]


def test_kill_switch_ausloeser_verweigert_leeren_grund() -> None:
    """@trace betriebssicherung#AC11 — ein leerer Grund wird abgelehnt, weil
    das Protokoll (AC11) einen tatsächlichen Grund tragen muss."""
    with pytest.raises(ValidationError):
        KillSwitchAusloeser(quelle="manuell", zeitstempel=_ZEITSTEMPEL, grund="")


def test_kill_switch_ausloeser_kennwert_ist_optional() -> None:
    """@trace betriebssicherung#AC1 — `kennwert` ist laut Vertrag optional
    (`kennwert?`); ohne ihn bleibt die Instanziierung gültig."""
    ausloeser = KillSwitchAusloeser(quelle="manuell", zeitstempel=_ZEITSTEMPEL, grund="Testfall")
    assert ausloeser.kennwert is None

    mit_kennwert = KillSwitchAusloeser(
        quelle="drawdown", zeitstempel=_ZEITSTEMPEL, grund="Schwelle", kennwert=Decimal("12.5")
    )
    assert mit_kennwert.kennwert == Decimal("12.5")


def test_kill_switch_status_kennt_genau_die_zwei_spec_zustaende() -> None:
    """@trace betriebssicherung#AC3 — `KillSwitchStatus.zustand` akzeptiert
    genau die zwei von der Spec benannten Zustände (`normal`/`angehalten`);
    ein dritter Wert wird abgelehnt."""
    normal = KillSwitchStatus(zustand="normal")
    angehalten = KillSwitchStatus(
        zustand="angehalten", quelle="manuell", grund="Test", ausgeloest_am=_ZEITSTEMPEL
    )
    assert normal.zustand == "normal"
    assert angehalten.zustand == "angehalten"

    with pytest.raises(ValidationError):
        KillSwitchStatus(zustand="pausiert")  # type: ignore[arg-type]


def test_kill_switch_ereignis_traegt_ausloeser_zeitpunkt_und_grund() -> None:
    """@trace betriebssicherung#AC11 — der Protokolleintrag trägt genau die
    von AC11 geforderten Felder: Auslöser (`quelle`), Zeitpunkt
    (`zeitstempel`) und Grund (`grund`)."""
    eintrag = KillSwitchEreignis(
        quelle="manuell",
        zeitstempel=_ZEITSTEMPEL,
        grund="Owner hat Notaus gedrückt",
        wirkung="ausgeloest",
    )
    assert eintrag.quelle == "manuell"
    assert eintrag.zeitstempel == _ZEITSTEMPEL
    assert eintrag.grund == "Owner hat Notaus gedrückt"


def test_kill_switch_ereignis_ist_unveraenderlich() -> None:
    """@trace betriebssicherung#AC11 — `KillSwitchEreignis` ist `frozen`
    (Vertrags-Ebene der Unveränderlichkeit, analog `ProtokollEintrag`)."""
    eintrag = KillSwitchEreignis(
        quelle="manuell", zeitstempel=_ZEITSTEMPEL, grund="Test", wirkung="ausgeloest"
    )
    with pytest.raises(ValidationError):
        eintrag.grund = "geaendert"  # type: ignore[misc]


def test_secret_store_zugang_akzeptiert_nur_paper_oder_live() -> None:
    """@trace betriebssicherung#AC6 — `SecretStoreZugang.umgebung`
    akzeptiert ausschließlich `paper`/`live`; ein dritter Wert (z. B. ein
    gemeinsames "beide"/"sim") wird strukturell abgelehnt."""
    paper = SecretStoreZugang(
        dienst="ibkr", umgebung="paper", endpunkt="https://paper.example.test", api_key="k1"
    )
    live = SecretStoreZugang(
        dienst="ibkr", umgebung="live", endpunkt="https://live.example.test", api_key="k2"
    )
    assert paper.umgebung == "paper"
    assert live.umgebung == "live"

    with pytest.raises(ValidationError):
        SecretStoreZugang(dienst="ibkr", umgebung="sim", endpunkt="https://x", api_key="k")  # type: ignore[arg-type]


def test_secret_store_zugang_ist_unveraenderlich() -> None:
    """@trace betriebssicherung#AC6 — `SecretStoreZugang` ist `frozen`
    (Vertrags-Ebene, analog `KillSwitchEreignis`)."""
    zugang = SecretStoreZugang(
        dienst="ibkr", umgebung="paper", endpunkt="https://paper.example.test", api_key="k1"
    )
    with pytest.raises(ValidationError):
        zugang.umgebung = "live"  # type: ignore[misc]


def test_secret_store_zugang_verweigert_leeren_api_key() -> None:
    """@trace betriebssicherung#AC6 — ein leerer `api_key` wird strukturell
    abgelehnt (Vertragsebene der Validierung aus
    `app.core.secrets.resolve_secret_store_zugang`)."""
    with pytest.raises(ValidationError):
        SecretStoreZugang(
            dienst="ibkr", umgebung="paper", endpunkt="https://paper.example.test", api_key=""
        )


def test_secret_store_zugang_api_key_erscheint_nicht_im_repr() -> None:
    """@trace betriebssicherung#AC6 — `api_key`/`api_secret` sind
    `repr=False` (NFR "keine Secrets im Klartext in Logs oder Alerts") und
    erscheinen deshalb nicht in `repr()`/`str()` des Modells."""
    zugang = SecretStoreZugang(
        dienst="ibkr",
        umgebung="live",
        endpunkt="https://live.example.test",
        api_key="dummy-fixture-secret-42",  # gitleaks:allow
        api_secret="dummy-fixture-secret-99",  # gitleaks:allow
    )
    dargestellt = repr(zugang) + str(zugang)
    assert "dummy-fixture-secret-42" not in dargestellt
    assert "dummy-fixture-secret-99" not in dargestellt


def test_alert_akzeptiert_alle_fuenf_vertrags_typen() -> None:
    """@trace betriebssicherung#AC4,AC5 — der Alert-Vertrag akzeptiert alle
    fünf von der Spec benannten Typen (`kill|heartbeat|drawdown|
    quellenausfall|halluzination`), auch wenn diese Story (S-025) nur
    `heartbeat`/`drawdown` tatsächlich erzeugt."""
    for typ in ("kill", "heartbeat", "drawdown", "quellenausfall", "halluzination"):
        alert = Alert(typ=typ, schwere="warn", nachricht="Testfall", zeitstempel=_ZEITSTEMPEL)
        assert alert.typ == typ


def test_alert_verweigert_unbekannten_typ_und_leere_nachricht() -> None:
    """@trace betriebssicherung#AC4,AC5 — ein Typ außerhalb des
    Vertrags-Literals sowie eine leere Nachricht werden strukturell
    abgelehnt."""
    with pytest.raises(ValidationError):
        Alert(typ="unbekannt", schwere="warn", nachricht="x", zeitstempel=_ZEITSTEMPEL)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Alert(typ="drawdown", schwere="warn", nachricht="", zeitstempel=_ZEITSTEMPEL)


def test_alert_ist_unveraenderlich() -> None:
    """@trace betriebssicherung#AC4,AC5 — `Alert` ist `frozen` (analog
    `KillSwitchEreignis`)."""
    alert = Alert(typ="drawdown", schwere="critical", nachricht="Test", zeitstempel=_ZEITSTEMPEL)
    with pytest.raises(ValidationError):
        alert.schwere = "info"  # type: ignore[misc]


def test_heartbeat_eintrag_traegt_genau_die_drei_vertragsfelder() -> None:
    """@trace betriebssicherung#AC4 — der Heartbeat-Vertrag trägt genau
    `{modul_id, letzter_ping_zeitstempel, intervall_soll}` und lehnt
    unbekannte Zusatzfelder ab (`extra="forbid"`)."""
    eintrag = HeartbeatEintrag(
        modul_id="ingest-fred",
        letzter_ping_zeitstempel=_ZEITSTEMPEL,
        intervall_soll=timedelta(minutes=5),
    )
    assert eintrag.modul_id == "ingest-fred"
    assert eintrag.intervall_soll == timedelta(minutes=5)

    with pytest.raises(ValidationError):
        HeartbeatEintrag(
            modul_id="x",
            letzter_ping_zeitstempel=_ZEITSTEMPEL,
            intervall_soll=timedelta(minutes=5),
            kritisch=True,  # type: ignore[call-arg]
        )


def test_heartbeat_eintrag_verweigert_leere_modul_id() -> None:
    """@trace betriebssicherung#AC4 — eine leere `modul_id` wird
    strukturell abgelehnt."""
    with pytest.raises(ValidationError):
        HeartbeatEintrag(
            modul_id="", letzter_ping_zeitstempel=_ZEITSTEMPEL, intervall_soll=timedelta(minutes=5)
        )


def test_drawdown_status_ueberwachungsluecke_setzt_zahlfelder_auf_none() -> None:
    """@trace betriebssicherung#AC5 — im Überwachungslücke-Fall (Edge-Case:
    fehlender Depot-Stand) bleiben alle Zahlfelder `None` statt eines
    stillschweigenden `0`-Werts."""
    status = DrawdownStatus(
        aktueller_stand=None,
        hoechststand=None,
        drawdown_pct=None,
        ueberwachungsluecke=True,
        kill_ausgeloest=False,
    )
    assert status.aktueller_stand is None
    assert status.drawdown_pct is None
    assert status.ueberwachungsluecke is True
    assert status.kill_ausgeloest is False


def test_drawdown_status_traegt_berechnete_werte() -> None:
    """@trace betriebssicherung#AC2,AC5 — bei vorhandenem Depot-Stand trägt
    der Status Höchststand, aktuellen Stand und den daraus abgeleiteten
    Drawdown-Prozentsatz."""
    status = DrawdownStatus(
        aktueller_stand=Decimal("80000"),
        hoechststand=Decimal("100000"),
        drawdown_pct=Decimal("0.20"),
        ueberwachungsluecke=False,
        kill_ausgeloest=True,
    )
    assert status.drawdown_pct == Decimal("0.20")
    assert status.kill_ausgeloest is True


def test_drawdown_status_ist_unveraenderlich() -> None:
    """@trace betriebssicherung#AC5 — `DrawdownStatus` ist `frozen` (analog
    `KillSwitchStatus`)."""
    status = DrawdownStatus(ueberwachungsluecke=True, kill_ausgeloest=False)
    with pytest.raises(ValidationError):
        status.kill_ausgeloest = True  # type: ignore[misc]
