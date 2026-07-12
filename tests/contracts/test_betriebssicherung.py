"""Tests für die Kill-Switch-Verträge (Story S-007).

Covers (betriebssicherung): AC1, AC3, AC11

`app.contracts.betriebssicherung` bildet die Verträge aus
`docs/specs/betriebssicherung.md` ab, soweit sie diese Story betreffen: den
Kill-Switch-Auslöser-Input (`KillSwitchAusloeser`, AC1), den Betriebszustand
(`Betriebszustand`/`KillSwitchStatus`, AC3) und den unveränderlichen
Protokolleintrag (`KillSwitchEreignis`, AC11). Das tatsächliche
Zustandsmaschinen-/Protokollierungs-Verhalten liegt in
`tests/core/test_kill_switch.py`.
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
