"""Tests für die Ampel-Ableitung & Regel-Promotion
`app.domain.lernschleife.gate` (Story S-062).

Covers (lernschleife): AC10, AC11, AC12

- **AC10 (Ampel):** `leite_ampel_ab`-Tests belegen alle Fallunterscheidungen
  aus BR-119 (🟢 nur bei Stufe A UND B bestanden, 🟡 A bestanden/B läuft,
  🔴 durchgefallen) sowie den Sonderfall "kein Urteil" (AC4/A3, Stichprobe
  unter der Bewertungsuntergrenze — `None`, kein Ampel-Zustand); zusätzlich
  ein End-to-End-Test über den vollen `bewerte_stufe_a`/`bewerte_stufe_b`-
  Flow (S-060/S-061) bis zur Ampel.
- **AC11 (Promotion nur bei Grün):**
  `wende_gate_ergebnis_auf_suchkriteria_an`-Tests belegen, dass NUR eine
  grüne Ampel die `SuchprofilRegistry` aktualisiert (gelb/rot/kein Urteil
  lassen sie unverändert) und dass dies ausschliesslich über
  `app.domain.kandidatensuche.regel_governance.uebernehme_regelaenderung`
  (S-057) läuft — kein zweiter, hier neu erfundener Übernahmepfad.
- **AC12 (konfigurierbare Schwellen):** ein Test belegt, dass eine
  geänderte `StufeBKonfiguration.psr_schwelle` (bereits AC12-konform
  konfigurierbar, S-061) die aus identischen Trades abgeleitete Ampel von
  🔴 auf 🟢 kippt — die Ampel-Ableitung selbst führt keinen eigenen,
  hartkodierten Schwellenvergleich durch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.contracts.kandidatensuche import Regelvorschlag, Suchprofil
from app.contracts.lernschleife import StufeBKonfiguration
from app.domain.lernschleife.gate import leite_ampel_ab, wende_gate_ergebnis_auf_suchkriteria_an
from app.domain.lernschleife.stage_a import bewerte_stufe_a
from app.domain.lernschleife.stage_b import bewerte_stufe_b

_START = datetime(2024, 1, 1, tzinfo=UTC)


def _trade(tag_offset: int, rendite: str):
    from app.contracts.lernschleife import TradeErgebnis

    return TradeErgebnis(datum=_START + timedelta(days=tag_offset), rendite_pct=Decimal(rendite))


def _stabile_trades_mit_streuung(n: int, *, schritt_tage: int, basis: float, streuung: float = 4.0):
    return [
        _trade(i * schritt_tage, str(round(basis + (streuung if i % 2 == 0 else -streuung), 2)))
        for i in range(n)
    ]


def _stufe_a_report(*, ergebnis: str, n_trades: int = 150):
    from app.contracts.lernschleife import StufeAReport

    return StufeAReport(
        hypothesis_id=uuid.uuid4(),
        n_trades=n_trades,
        embargo_tage=30,
        walk_forward_effizienz=Decimal("0.9") if ergebnis != "nicht_bewertet" else None,
        dsr=Decimal("0.8") if ergebnis == "bestanden" else None,
        ergebnis=ergebnis,
        begruendung="Test-Begründung",
    )


def _stufe_b_report(*, psr_bestanden: bool):
    from app.contracts.lernschleife import StufeBReport

    return StufeBReport(
        hypothesis_id=uuid.uuid4(),
        n_trades=200,
        psr=Decimal("0.97") if psr_bestanden else Decimal("0.5"),
        psr_schwelle=Decimal("0.95"),
        psr_bestanden=psr_bestanden,
        begruendung="Test-Begründung",
    )


# --- AC10: Ampel-Ableitung -------------------------------------------------------


def test_leite_ampel_ab_liefert_none_bei_nicht_bewerteter_hypothese() -> None:
    """@trace lernschleife#AC10,AC4 — A3 „gar nicht bewertet" ist kein
    Ampel-Zustand; `leite_ampel_ab` liefert kein Urteil (`None`)."""
    stufe_a = _stufe_a_report(ergebnis="nicht_bewertet")

    assert leite_ampel_ab(stufe_a) is None


def test_leite_ampel_ab_liefert_rot_bei_durchgefallener_stufe_a() -> None:
    """@trace lernschleife#AC10 — Stufe A nicht bestanden -> 🔴 (deckt A2),
    unabhängig davon, ob Stufe B je gelaufen ist."""
    stufe_a = _stufe_a_report(ergebnis="durchgefallen")

    assert leite_ampel_ab(stufe_a) == "rot"


def test_leite_ampel_ab_liefert_gelb_wenn_stufe_a_bestanden_und_stufe_b_noch_nicht_gelaufen() -> (
    None
):
    """@trace lernschleife#AC10 — Stufe A bestanden, Stufe B läuft noch mit
    -> 🟡 (deckt A1: nur Paper-Modus, keine Übernahme)."""
    stufe_a = _stufe_a_report(ergebnis="bestanden")

    assert leite_ampel_ab(stufe_a, stufe_b=None) == "gelb"


def test_leite_ampel_ab_liefert_gruen_wenn_beide_stufen_bestanden() -> None:
    """@trace lernschleife#AC10,BR-119 — 🟢 NUR wenn Stufe A UND B
    bestanden."""
    stufe_a = _stufe_a_report(ergebnis="bestanden")
    stufe_b = _stufe_b_report(psr_bestanden=True)

    assert leite_ampel_ab(stufe_a, stufe_b) == "gruen"


def test_leite_ampel_ab_liefert_rot_wenn_stufe_a_bestanden_aber_stufe_b_durchfaellt() -> None:
    """@trace lernschleife#AC10 — Stufe A bestanden, Stufe B nicht bestanden
    (PSR < Schwelle) -> 🔴, nicht 🟡 (durchgefallen bleibt durchgefallen,
    auch nach abgeschlossener Stufe B)."""
    stufe_a = _stufe_a_report(ergebnis="bestanden")
    stufe_b = _stufe_b_report(psr_bestanden=False)

    assert leite_ampel_ab(stufe_a, stufe_b) == "rot"


def test_leite_ampel_ab_end_to_end_ueber_den_vollen_stufe_a_stufe_b_flow() -> None:
    """@trace lernschleife#AC10 — End-to-End: `bewerte_stufe_a` (S-060) +
    `bewerte_stufe_b` (S-061) liefern reale Reports, aus denen die Ampel
    korrekt 🟢 ableitet."""
    trades_a = _stabile_trades_mit_streuung(150, schritt_tage=5, basis=1.0)
    trades_b = _stabile_trades_mit_streuung(200, schritt_tage=1, basis=5.0, streuung=0.5)

    stufe_a_report = bewerte_stufe_a(trades_a, hypothesis_id=uuid.uuid4(), n_trials=1)
    stufe_b_report = bewerte_stufe_b(trades_b, hypothesis_id=uuid.uuid4())

    assert stufe_a_report.ergebnis == "bestanden"
    assert stufe_b_report.psr_bestanden is True
    assert leite_ampel_ab(stufe_a_report, stufe_b_report) == "gruen"


# --- AC12: konfigurierbare Schwellen wirken auf die Ampel -----------------------


def test_leite_ampel_ab_kippt_mit_konfigurierter_psr_schwelle_von_rot_auf_gruen() -> None:
    """@trace lernschleife#AC12 (i.V.m. AC10) — dieselben Trades bestehen
    Stufe B nur mit einer niedrigeren `psr_schwelle` (S-061, bereits
    konfigurierbar) — die Ampel-Ableitung liest nur `psr_bestanden`, führt
    selbst keinen eigenen Zahlenvergleich durch."""
    trades = _stabile_trades_mit_streuung(5, schritt_tage=1, basis=0.1, streuung=4.0)
    stufe_a = _stufe_a_report(ergebnis="bestanden")

    stufe_b_default = bewerte_stufe_b(trades, hypothesis_id=uuid.uuid4())
    stufe_b_niedrig = bewerte_stufe_b(
        trades,
        hypothesis_id=uuid.uuid4(),
        konfiguration=StufeBKonfiguration(psr_schwelle=Decimal("0.01")),
    )

    assert leite_ampel_ab(stufe_a, stufe_b_default) == "rot"
    assert leite_ampel_ab(stufe_a, stufe_b_niedrig) == "gruen"


# --- AC11: Regel-Promotion nur bei Grün ------------------------------------------

_PROFIL_ALT = Suchprofil(anlageklasse=1, schwellen={"rvol_faktor": Decimal("2")})
_PROFIL_NEU = Suchprofil(anlageklasse=1, schwellen={"rvol_faktor": Decimal("2.5")})


def test_wende_gate_ergebnis_an_uebernimmt_das_profil_nur_bei_gruener_ampel() -> None:
    """@trace lernschleife#AC11 — 🟢 übernimmt das vorgeschlagene Profil in
    die Suchkriteria."""
    registry = {1: _PROFIL_ALT}

    aktualisiert = wende_gate_ergebnis_auf_suchkriteria_an(
        registry, ampel="gruen", profil=_PROFIL_NEU
    )

    assert aktualisiert[1] == _PROFIL_NEU


def test_wende_gate_ergebnis_an_laesst_registry_bei_gelber_ampel_unveraendert() -> None:
    """@trace lernschleife#AC11,AC10 — 🟡 (Stufe A bestanden, Stufe B läuft)
    ändert die aktive Suche NICHT (deckt A1)."""
    registry = {1: _PROFIL_ALT}

    aktualisiert = wende_gate_ergebnis_auf_suchkriteria_an(
        registry, ampel="gelb", profil=_PROFIL_NEU
    )

    assert aktualisiert[1] == _PROFIL_ALT


def test_wende_gate_ergebnis_an_laesst_registry_bei_roter_ampel_unveraendert() -> None:
    """@trace lernschleife#AC11,AC10 — 🔴 ändert die aktive Suche NICHT
    (deckt A2)."""
    registry = {1: _PROFIL_ALT}

    aktualisiert = wende_gate_ergebnis_auf_suchkriteria_an(
        registry, ampel="rot", profil=_PROFIL_NEU
    )

    assert aktualisiert[1] == _PROFIL_ALT


def test_wende_gate_ergebnis_an_laesst_registry_ohne_urteil_unveraendert() -> None:
    """@trace lernschleife#AC11,AC4 — `ampel=None` (AC4/A3 "kein Urteil")
    darf nie promoted werden; die Registry bleibt unverändert."""
    registry = {1: _PROFIL_ALT}

    aktualisiert = wende_gate_ergebnis_auf_suchkriteria_an(registry, ampel=None, profil=_PROFIL_NEU)

    assert aktualisiert == {1: _PROFIL_ALT}


def test_wende_gate_ergebnis_an_mutiert_die_original_registry_nicht() -> None:
    """@trace lernschleife#AC11 — analog `uebernehme_regelaenderung` (S-057):
    kein In-Place-Mutieren des übergebenen Registry-Objekts."""
    registry = {1: _PROFIL_ALT}

    wende_gate_ergebnis_auf_suchkriteria_an(registry, ampel="gruen", profil=_PROFIL_NEU)

    assert registry == {1: _PROFIL_ALT}


def test_wende_gate_ergebnis_an_baut_denselben_regelvorschlag_wie_uebernehme_regelaenderung(
    monkeypatch,
) -> None:
    """@trace lernschleife#AC11 — es gibt keinen zweiten, hier neu
    erfundenen Übernahmepfad: die Funktion ruft ausschliesslich
    `app.domain.kandidatensuche.regel_governance.uebernehme_regelaenderung`
    auf (S-057, die einzige vorgesehene Andockstelle)."""
    aufrufe: list[Regelvorschlag] = []

    def _spion(registry, vorschlag):
        aufrufe.append(vorschlag)
        return registry

    monkeypatch.setattr(
        "app.domain.lernschleife.gate.uebernehme_regelaenderung",
        _spion,
    )

    wende_gate_ergebnis_auf_suchkriteria_an({}, ampel="gruen", profil=_PROFIL_NEU)

    assert len(aufrufe) == 1
    assert aufrufe[0] == Regelvorschlag(profil=_PROFIL_NEU, ampel="gruen")
