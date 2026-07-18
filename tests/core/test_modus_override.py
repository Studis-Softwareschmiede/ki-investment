"""Tests für den Modus-Override-Store `app.core.modus_override` (Story
S-074, `docs/specs/frontend-cockpit.md` AC20/AC21).

Covers (frontend-cockpit): AC20, AC21

Deckt: globalen + je-Anlageklasse-Override setzen (BR-019 "global und je
Klasse überschreibbar"), die MVP-Live-Sperre (fail-closed, jeder Wert
ausser `"simuliert"` wirft `LiveModusGesperrtError`, OHNE den bisherigen
Zustand zu verändern) sowie den Cold-Start-Default (global `"simuliert"`,
keine Overrides)."""

from __future__ import annotations

import pytest

from app.core import modus_override
from app.domain.execution.order_ausfuehrung import LiveModusGesperrtError


@pytest.fixture(autouse=True)
def _store_isolieren():
    modus_override.reset_fuer_tests()
    yield
    modus_override.reset_fuer_tests()


def test_cold_start_ist_global_simuliert_ohne_overrides() -> None:
    """@trace frontend-cockpit#AC21 — ohne jeden Schreibzugriff: globaler
    Default `"simuliert"`, keine Anlageklassen-Overrides (deckt A2)."""
    konfiguration = modus_override.aktuelle_konfiguration()

    assert konfiguration.global_modus == "simuliert"
    assert dict(konfiguration.modus_je_anlageklasse) == {}


def test_setze_global_override_akzeptiert_simuliert() -> None:
    """@trace frontend-cockpit#AC20 — `"simuliert"` ist die einzig
    zulässige Ebene im MVP (BR-019) und wird deshalb durchgelassen."""
    konfiguration = modus_override.setze_global_override("simuliert")

    assert konfiguration.global_modus == "simuliert"
    assert modus_override.aktuelle_konfiguration().global_modus == "simuliert"


def test_setze_global_override_lehnt_echt_ab_und_aendert_nichts() -> None:
    """@trace frontend-cockpit#AC21 — ein Versuch, den globalen Modus auf
    `"echt"` zu setzen, wirft `LiveModusGesperrtError` (BR-019 MVP-Sperre,
    fail-closed) und lässt den bisherigen Zustand unverändert."""
    with pytest.raises(LiveModusGesperrtError):
        modus_override.setze_global_override("echt")

    assert modus_override.aktuelle_konfiguration().global_modus == "simuliert"


def test_setze_override_fuer_anlageklasse_akzeptiert_simuliert() -> None:
    """@trace frontend-cockpit#AC20 — BR-019 "je Klasse überschreibbar":
    ein Anlageklassen-spezifischer Override auf `"simuliert"` wird
    persistiert, ohne den globalen Modus zu berühren."""
    konfiguration = modus_override.setze_override_fuer_anlageklasse(7, "simuliert")

    assert konfiguration.modus_je_anlageklasse[7] == "simuliert"
    assert konfiguration.global_modus == "simuliert"


def test_setze_override_fuer_anlageklasse_lehnt_echt_ab_und_aendert_nichts() -> None:
    """@trace frontend-cockpit#AC21 — ein je-Anlageklasse-Override auf
    `"echt"` wirft `LiveModusGesperrtError` (BR-019) und hinterlässt
    KEINEN teilweise geschriebenen Override."""
    with pytest.raises(LiveModusGesperrtError):
        modus_override.setze_override_fuer_anlageklasse(7, "echt")

    assert 7 not in modus_override.aktuelle_konfiguration().modus_je_anlageklasse


def test_mehrere_anlageklassen_overrides_koexistieren() -> None:
    """@trace frontend-cockpit#AC20 — Overrides für verschiedene
    Anlageklassen akkumulieren, statt sich gegenseitig zu überschreiben."""
    modus_override.setze_override_fuer_anlageklasse(1, "simuliert")
    modus_override.setze_override_fuer_anlageklasse(7, "simuliert")

    konfiguration = modus_override.aktuelle_konfiguration()

    assert set(konfiguration.modus_je_anlageklasse.keys()) == {1, 7}


def test_reset_fuer_tests_stellt_mvp_default_wieder_her() -> None:
    """@trace frontend-cockpit#AC21 — `reset_fuer_tests()` stellt den
    MVP-Cold-Start-Zustand wieder her (Test-Isolation, analog
    `app.core.kill_switch.reset_fuer_tests`)."""
    modus_override.setze_override_fuer_anlageklasse(1, "simuliert")

    modus_override.reset_fuer_tests()

    konfiguration = modus_override.aktuelle_konfiguration()
    assert konfiguration.global_modus == "simuliert"
    assert dict(konfiguration.modus_je_anlageklasse) == {}
