"""Tests für die Halluzinations-KPI & den Kill der LLM-Kette (Story S-027).

Covers (llm-grounding): AC8, AC9

`app.core.hallucination_kpi` berechnet laufend die Quote „Analysen mit
Faktenabweichung" (verworfene / geprüfte Analysen) aus registrierten
`CrossCheckErgebnis`-Instanzen (AC4-Ergebnisse, S-013) und nimmt das LLM aus
der Entscheidungskette, sobald die Quote den konfigurierten Schwellwert
(Default 2 %, `app.config`) STRIKT überschreitet (AC9, BR-006). Deckt: die
reine Quotenberechnung inkl. Zeitfenster (AC8), den Grenzfall „genau am
Schwellwert → kein Alarm" (AC9-Edge-Case), den Kill-Latch (einmal
ausgelöst, bleibt die Kette deaktiviert bis zum manuellen Reset), die
Auditierung des Alarm-Übergangs (AC10-Geist) sowie die Konfigurierbarkeit
des Schwellwerts ohne Codeänderung (AC9).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.contracts.llm_grounding import CrossCheckErgebnis
from app.core import hallucination_kpi
from app.core.audit_log import alle_eintraege
from app.core.audit_log import reset_fuer_tests as audit_log_reset_fuer_tests


@pytest.fixture(autouse=True)
def _zustand_isolieren():
    """Isoliert Registrierungs-Historie, Kill-Status, Audit-Log und
    Settings-Cache zwischen Testfällen."""
    hallucination_kpi.reset_fuer_tests()
    audit_log_reset_fuer_tests()
    get_settings.cache_clear()
    yield
    hallucination_kpi.reset_fuer_tests()
    audit_log_reset_fuer_tests()
    get_settings.cache_clear()


def _ergebnis(status: str) -> CrossCheckErgebnis:
    return CrossCheckErgebnis(status=status)  # type: ignore[arg-type]


def _registriere(*, geerdet: int = 0, verworfen: int = 0) -> None:
    for _ in range(geerdet):
        hallucination_kpi.registriere_ergebnis(_ergebnis("geerdet"))
    for _ in range(verworfen):
        hallucination_kpi.registriere_ergebnis(_ergebnis("verworfen"))


def test_berechne_kpi_ohne_registrierungen_liefert_quote_null_kein_alarm() -> None:
    """@trace llm-grounding#AC8 — ohne registrierte Cross-Check-Ergebnisse
    ist die Quote 0.0 und es entsteht kein Alarm (eine leere Stichprobe
    belegt keine Faktenabweichung)."""
    ergebnis = hallucination_kpi.berechne_kpi()

    assert ergebnis.geprueft == 0
    assert ergebnis.verworfen == 0
    assert ergebnis.quote == 0.0
    assert ergebnis.alarm is False
    assert ergebnis.llm_status == "aktiv"
    assert hallucination_kpi.ist_llm_aktiv() is True


def test_registriere_ergebnis_zaehlt_geerdet_nicht_als_verworfen() -> None:
    """@trace llm-grounding#AC8 — `status == "geerdet"` zählt zu `geprueft`,
    aber NICHT zu `verworfen`; die Quote bleibt 0.0."""
    _registriere(geerdet=5)

    ergebnis = hallucination_kpi.berechne_kpi()

    assert ergebnis.geprueft == 5
    assert ergebnis.verworfen == 0
    assert ergebnis.quote == 0.0


def test_berechne_kpi_berechnet_quote_aus_registrierten_ergebnissen() -> None:
    """@trace llm-grounding#AC8 — die Quote „Analysen mit Faktenabweichung"
    wird laufend aus geprüften/verworfenen Analysen berechnet (hier 2 von
    200 = 1 %, unter dem Default-Schwellwert von 2 % → kein Alarm)."""
    _registriere(geerdet=198, verworfen=2)

    ergebnis = hallucination_kpi.berechne_kpi()

    assert ergebnis.geprueft == 200
    assert ergebnis.verworfen == 2
    assert ergebnis.quote == pytest.approx(0.01)
    assert ergebnis.alarm is False
    assert ergebnis.llm_status == "aktiv"


def test_berechne_kpi_grenzfall_exakt_am_schwellwert_kein_alarm() -> None:
    """@trace llm-grounding#AC9 — eine Quote GENAU auf dem Schwellwert
    (hier 2/100 = 2 %, Default-Schwellwert) löst KEINEN Alarm aus; erst eine
    STRIKTE Überschreitung (Edge-Case der Spec)."""
    _registriere(geerdet=98, verworfen=2)

    ergebnis = hallucination_kpi.berechne_kpi()

    assert ergebnis.quote == pytest.approx(0.02)
    assert ergebnis.alarm is False
    assert ergebnis.llm_status == "aktiv"
    assert hallucination_kpi.ist_llm_aktiv() is True


def test_berechne_kpi_ueberschreitung_loest_alarm_und_kill_aus() -> None:
    """@trace llm-grounding#AC9 — übersteigt die Quote den Schwellwert
    STRIKT (hier 3/100 = 3 % > 2 %), wird ein Alarm ausgelöst und das LLM
    aus der Entscheidungskette genommen; der Übergang wird auditiert
    (AC10-Geist)."""
    _registriere(geerdet=97, verworfen=3)

    ergebnis = hallucination_kpi.berechne_kpi()

    assert ergebnis.quote == pytest.approx(0.03)
    assert ergebnis.alarm is True
    assert ergebnis.llm_status == "deaktiviert"
    assert hallucination_kpi.ist_llm_aktiv() is False

    eintraege = alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "halluzinations_kpi_alarm"


def test_kill_ist_latch_bleibt_deaktiviert_auch_wenn_quote_wieder_sinkt() -> None:
    """@trace llm-grounding#AC9 — der Kill ist ein Klemmzustand (Latch):
    einmal ausgelöst, bleibt die LLM-Kette deaktiviert, auch wenn
    nachfolgend registrierte Analysen die (neu berechnete) Quote wieder
    unter den Schwellwert drücken — nur ein manueller Reset reaktiviert."""
    _registriere(geerdet=97, verworfen=3)
    erster_alarm = hallucination_kpi.berechne_kpi()
    assert erster_alarm.llm_status == "deaktiviert"

    _registriere(geerdet=10_000)  # drückt die kumulative Quote weit unter 2 %
    zweites_ergebnis = hallucination_kpi.berechne_kpi()

    assert zweites_ergebnis.alarm is False  # aktuelle Quote liegt wieder unter dem Schwellwert
    assert zweites_ergebnis.llm_status == "deaktiviert"  # Latch bleibt bestehen
    assert hallucination_kpi.ist_llm_aktiv() is False
    assert len(alle_eintraege()) == 1  # kein zweiter Alarm-Eintrag bei bereits deaktivierter Kette


def test_reaktiviere_llm_setzt_status_zurueck_und_startet_frisches_fenster() -> None:
    """@trace llm-grounding#AC9 — der manuelle Reset (BR-006) schaltet die
    LLM-Kette wieder auf `aktiv` und startet ein frisches
    Beobachtungsfenster (alte Registrierungen zählen nicht mehr)."""
    _registriere(geerdet=97, verworfen=3)
    hallucination_kpi.berechne_kpi()
    assert hallucination_kpi.ist_llm_aktiv() is False

    hallucination_kpi.reaktiviere_llm()

    assert hallucination_kpi.ist_llm_aktiv() is True
    ergebnis = hallucination_kpi.berechne_kpi()
    assert ergebnis.geprueft == 0
    assert ergebnis.quote == 0.0
    assert ergebnis.llm_status == "aktiv"


def test_schwellwert_konfigurierbar_ohne_codeaenderung(monkeypatch: pytest.MonkeyPatch) -> None:
    """@trace llm-grounding#AC9 — der Schwellwert ist über die
    Umgebungsvariable `HALLUZINATIONS_KPI_SCHWELLWERT` ohne Codeänderung
    überschreibbar: eine Quote, die unter dem Default (2 %) bliebe, löst
    bei einem strenger konfigurierten Schwellwert (0.5 %) einen Alarm aus."""
    monkeypatch.setenv("HALLUZINATIONS_KPI_SCHWELLWERT", "0.005")
    get_settings.cache_clear()
    _registriere(geerdet=99, verworfen=1)  # Quote 1 % — unter Default-2 %, über 0.5 %

    ergebnis = hallucination_kpi.berechne_kpi()

    assert ergebnis.schwellwert == pytest.approx(0.005)
    assert ergebnis.alarm is True
    assert ergebnis.llm_status == "deaktiviert"


def test_berechne_kpi_seit_parameter_filtert_aeltere_registrierungen() -> None:
    """@trace llm-grounding#AC8 — der Vertrag "über ein Zeitfenster" ist
    über den optionalen `seit`-Parameter erzwingbar: ältere Registrierungen
    fallen aus der Quotenberechnung heraus."""
    alt = datetime(2026, 1, 1, tzinfo=UTC)
    hallucination_kpi.registriere_ergebnis(_ergebnis("verworfen"), zeitpunkt=alt)
    hallucination_kpi.registriere_ergebnis(_ergebnis("verworfen"), zeitpunkt=alt)

    fenster_start = datetime(2026, 6, 1, tzinfo=UTC)
    hallucination_kpi.registriere_ergebnis(
        _ergebnis("geerdet"), zeitpunkt=fenster_start + timedelta(days=1)
    )

    ergebnis_ohne_fenster = hallucination_kpi.berechne_kpi()
    assert ergebnis_ohne_fenster.geprueft == 3
    assert ergebnis_ohne_fenster.verworfen == 2

    ergebnis_mit_fenster = hallucination_kpi.berechne_kpi(seit=fenster_start)
    assert ergebnis_mit_fenster.geprueft == 1
    assert ergebnis_mit_fenster.verworfen == 0
