"""Tests für die Kill-Switch- + Secret-Store-Verträge (Story S-007, S-008).

Covers (betriebssicherung): AC1, AC3, AC6, AC11

`app.contracts.betriebssicherung` bildet die Verträge aus
`docs/specs/betriebssicherung.md` ab, soweit sie diese Stories betreffen:
den Kill-Switch-Auslöser-Input (`KillSwitchAusloeser`, AC1), den
Betriebszustand (`Betriebszustand`/`KillSwitchStatus`, AC3), den
unveränderlichen Protokolleintrag (`KillSwitchEreignis`, AC11) sowie den
Secret-Store-Vertrag (`Umgebung`/`SecretStoreZugang`, AC6 — Story S-008).
Das tatsächliche Zustandsmaschinen-/Protokollierungs-Verhalten liegt in
`tests/core/test_kill_switch.py`; die tatsächliche Secret-Store-Auflösung
(strikte Paper/Live-Trennung) liegt in `tests/core/test_secret_store.py` —
hier wird nur die Vertrags-/Struktur-Ebene geprüft.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.betriebssicherung import (
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
