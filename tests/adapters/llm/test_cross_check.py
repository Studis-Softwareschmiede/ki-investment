"""Tests für den deterministischen Zahlen-Cross-Check (Story S-013).

Covers (llm-grounding): AC4, AC5, AC10

`app.adapters.llm.cross_check.pruefe_cross_check` vergleicht jede
referenzierte Zahl eines bereits grounding-geprüften Outputs ohne LLM
gegen ihre Originalquelle (AC4), mit konfigurierbaren Toleranzen je
Kennzahl-Typ (AC5, absolut/relativ inkl. Override + Default-Fallback) und
schreibt bei jeder Ablehnung einen Audit-Protokolleintrag (AC10, geprüft
über `app.core.audit_log.alle_eintraege`). Edge-Cases: Originalquelle
nicht verfügbar (inkl. `quellen_id` bekannt, aber falscher/fehlender
Kennzahl-Typ — Review-Fix Iteration 2) und Toleranz nicht konfiguriert
(beide → konservativ verwerfen).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.llm.cross_check import pruefe_cross_check
from app.contracts.llm_grounding import AnalyseFakt, Originalquelle, ToleranzKonfig
from app.core.audit_log import alle_eintraege, reset_fuer_tests


@pytest.fixture(autouse=True)
def _audit_log_isolieren():
    """Isoliert die in-memory Audit-Historie zwischen Testfällen."""
    reset_fuer_tests()
    yield
    reset_fuer_tests()


def _fakt(
    kennzahl_typ: str = "kgv", wert: float = 12.5, quellen_id: str = "sec-form4-123"
) -> AnalyseFakt:
    return AnalyseFakt(
        kennzahl_typ=kennzahl_typ,
        wert=wert,
        quellen_id=quellen_id,
        timestamp=datetime(2026, 7, 1, tzinfo=UTC),
    )


def _quellen(*eintraege: Originalquelle) -> dict[tuple[str, str], Originalquelle]:
    """Baut das `(quellen_id, kennzahl_typ)`-indizierte Originalquellen-
    Mapping, das `pruefe_cross_check` erwartet."""
    return {(quelle.quellen_id, quelle.kennzahl_typ): quelle for quelle in eintraege}


def test_pruefe_cross_check_akzeptiert_wert_innerhalb_toleranz() -> None:
    """@trace llm-grounding#AC4 — eine Zahl innerhalb der konfigurierten
    Toleranz gegenüber der Originalquelle gilt als geerdet."""
    fakt = _fakt(wert=12.5)
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=12.6)
    )
    toleranz_config = {"kgv": ToleranzKonfig(kennzahl_typ="kgv", typ="relativ", schwelle=0.05)}

    ergebnis = pruefe_cross_check((fakt,), originalquellen, toleranz_config)

    assert ergebnis.status == "geerdet"
    assert ergebnis.protokoll_eintrag is None
    assert len(ergebnis.abweichungen) == 1
    assert ergebnis.abweichungen[0].kennzahl_typ == "kgv"


def test_pruefe_cross_check_verwirft_abweichung_ueber_relativer_toleranz() -> None:
    """@trace llm-grounding#AC4,AC5 — überschreitet die relative Abweichung
    die konfigurierte Toleranz, wird die Analyse verworfen (deckt E2)."""
    fakt = _fakt(wert=100.0)
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=50.0)
    )
    toleranz_config = {"kgv": ToleranzKonfig(kennzahl_typ="kgv", typ="relativ", schwelle=0.05)}

    ergebnis = pruefe_cross_check((fakt,), originalquellen, toleranz_config)

    assert ergebnis.status == "verworfen"
    assert ergebnis.protokoll_eintrag is not None
    assert ergebnis.protokoll_eintrag.grund == "cross_check_abweichung"


def test_pruefe_cross_check_verwirft_abweichung_ueber_absoluter_toleranz() -> None:
    """@trace llm-grounding#AC5 — der Toleranz-Typ `absolut` vergleicht die
    reine Differenz statt einer relativen Abweichung."""
    fakt = _fakt(kennzahl_typ="kurs", wert=105.0)
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kurs", wert=100.0)
    )
    toleranz_config = {"kurs": ToleranzKonfig(kennzahl_typ="kurs", typ="absolut", schwelle=2.0)}

    ergebnis = pruefe_cross_check((fakt,), originalquellen, toleranz_config)

    assert ergebnis.status == "verworfen"
    assert ergebnis.abweichungen[0].abweichung == pytest.approx(5.0)


def test_pruefe_cross_check_akzeptiert_grenzwert_exakt_auf_toleranz() -> None:
    """@trace llm-grounding#AC5 — eine Abweichung exakt auf der Toleranz
    (nicht darüber) gilt noch als geerdet (nur Überschreitung verwirft,
    analog zur Halluzinations-KPI-Grenze in der Spec)."""
    fakt = _fakt(kennzahl_typ="kurs", wert=102.0)
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kurs", wert=100.0)
    )
    toleranz_config = {"kurs": ToleranzKonfig(kennzahl_typ="kurs", typ="absolut", schwelle=2.0)}

    ergebnis = pruefe_cross_check((fakt,), originalquellen, toleranz_config)

    assert ergebnis.status == "geerdet"


def test_pruefe_cross_check_nutzt_provisorische_defaults_ohne_override() -> None:
    """@trace llm-grounding#AC5 — ohne expliziten `toleranz_config`-Override
    greifen die provisorischen Defaults aus `app.config` (hier: `kgv`
    relativ 2 %) — die Toleranz ist ohne Codeänderung im Aufruf
    überschreibbar, aber auch ohne Override funktionsfähig."""
    fakt = _fakt(kennzahl_typ="kgv", wert=100.0)
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=100.5)
    )

    ergebnis = pruefe_cross_check((fakt,), originalquellen)

    assert ergebnis.status == "geerdet"


def test_pruefe_cross_check_verwirft_bei_fehlender_originalquelle() -> None:
    """@trace llm-grounding#AC4 — ist die Originalquelle für einen Fakt
    nicht verfügbar, wird konservativ verworfen (Edge-Case Spec)."""
    fakt = _fakt(quellen_id="unbekannte-quelle")

    ergebnis = pruefe_cross_check((fakt,), {})

    assert ergebnis.status == "verworfen"
    assert ergebnis.protokoll_eintrag is not None
    assert ergebnis.protokoll_eintrag.grund == "quelle_nicht_verfuegbar"


def test_pruefe_cross_check_verwirft_bei_quellen_id_mit_falschem_kennzahl_typ() -> None:
    """@trace llm-grounding#AC4 — Review-Fix Iteration 2: eine `quellen_id`
    mit MEHREREN berichteten Kennzahlen (z.B. ein Filing mit KGV, Kurs,
    Marktkapitalisierung) darf für einen Fakt niemals gegen die
    Originalquelle einer ANDEREN Kennzahl geprüft werden. Zwei Fakten
    teilen sich hier dieselbe `quellen_id`, tragen aber unterschiedliche
    Kennzahl-Typen — beide werden korrekt gegen ihren jeweils passenden
    Originalwert geprüft, nicht gegeneinander vertauscht."""
    fakt_kgv = _fakt(kennzahl_typ="kgv", wert=12.5, quellen_id="sec-form4-123")
    fakt_kurs = _fakt(kennzahl_typ="kurs", wert=101.0, quellen_id="sec-form4-123")
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=12.5),
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kurs", wert=100.0),
    )
    toleranz_config = {
        "kgv": ToleranzKonfig(kennzahl_typ="kgv", typ="absolut", schwelle=0.01),
        "kurs": ToleranzKonfig(kennzahl_typ="kurs", typ="absolut", schwelle=2.0),
    }

    ergebnis = pruefe_cross_check((fakt_kgv, fakt_kurs), originalquellen, toleranz_config)

    assert ergebnis.status == "geerdet"
    assert ergebnis.abweichungen[0].wert_quelle == 12.5
    assert ergebnis.abweichungen[1].wert_quelle == 100.0


def test_pruefe_cross_check_verwirft_wenn_quellen_id_bekannt_aber_kennzahl_typ_fehlt() -> None:
    """@trace llm-grounding#AC4 — Review-Fix Iteration 2: eine `quellen_id`
    ist bekannt, trägt aber keine Originalquelle für den konkret
    referenzierten Kennzahl-Typ des Fakts → konservativ verwerfen (kein
    stiller Vergleich gegen einen fachlich falschen Wert)."""
    fakt = _fakt(kennzahl_typ="marktkapitalisierung", wert=1_000_000.0, quellen_id="sec-form4-123")
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=12.5)
    )

    ergebnis = pruefe_cross_check((fakt,), originalquellen)

    assert ergebnis.status == "verworfen"
    assert ergebnis.protokoll_eintrag is not None
    assert ergebnis.protokoll_eintrag.grund == "quelle_nicht_verfuegbar"


def test_pruefe_cross_check_verwirft_bei_fehlender_toleranz_ohne_default() -> None:
    """@trace llm-grounding#AC5 — ein Kennzahl-Typ ohne Eintrag in
    `toleranz_config` UND ohne provisorischen Default wird konservativ
    verworfen statt durchgelassen (Edge-Case Spec)."""
    fakt = _fakt(kennzahl_typ="voellig-unbekannte-kennzahl", wert=1.0)
    originalquellen = _quellen(
        Originalquelle(
            quellen_id="sec-form4-123", kennzahl_typ="voellig-unbekannte-kennzahl", wert=1.0
        )
    )

    ergebnis = pruefe_cross_check((fakt,), originalquellen, toleranz_config={})

    assert ergebnis.status == "verworfen"
    assert ergebnis.protokoll_eintrag is not None
    assert ergebnis.protokoll_eintrag.grund == "toleranz_nicht_konfiguriert"


def test_pruefe_cross_check_ist_deterministisch() -> None:
    """@trace llm-grounding#AC4 — gleiche Eingaben liefern zweimal denselben
    Status/dieselben Abweichungen (kein LLM-Aufruf im Vergleich selbst;
    der Zeitpunkt des Protokolleintrags ist naturgemäß nicht Teil dieser
    Determinismus-Aussage — er markiert WANN protokolliert wurde, nicht
    WAS verglichen wurde)."""
    fakt = _fakt(wert=100.0)
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=50.0)
    )
    toleranz_config = {"kgv": ToleranzKonfig(kennzahl_typ="kgv", typ="relativ", schwelle=0.05)}

    erstes = pruefe_cross_check((fakt,), originalquellen, toleranz_config)
    zweites = pruefe_cross_check((fakt,), originalquellen, toleranz_config)

    assert erstes.status == zweites.status == "verworfen"
    assert erstes.abweichungen == zweites.abweichungen


def test_pruefe_cross_check_protokolliert_ablehnung_im_audit_log() -> None:
    """@trace llm-grounding#AC10 — eine verworfene Analyse landet als
    Protokolleintrag im Audit-Log (Grund, Zeitpunkt, Kennzahl-Typ,
    Quellen-ID), zusätzlich zum zurückgegebenen `protokoll_eintrag`."""
    fakt = _fakt(wert=100.0)
    originalquellen = _quellen(
        Originalquelle(quellen_id="sec-form4-123", kennzahl_typ="kgv", wert=50.0)
    )
    toleranz_config = {"kgv": ToleranzKonfig(kennzahl_typ="kgv", typ="relativ", schwelle=0.05)}

    pruefe_cross_check((fakt,), originalquellen, toleranz_config)

    eintraege = alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "cross_check_abweichung"
    assert eintraege[0].kennzahl_typ == "kgv"
    assert eintraege[0].quellen_id == "sec-form4-123"
