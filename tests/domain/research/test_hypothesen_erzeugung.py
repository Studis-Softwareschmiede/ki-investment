"""Tests für `app.domain.research.hypothesen_erzeugung` (Story S-058).

Covers (lernschleife): AC1, AC2

- **AC1 (Mindest-Evidenz-Protokoll, "ändert die Suchkriterien niemals
  direkt"):** jede erzeugte `Hypothese` trägt ihr vollständiges
  `Evidenzprotokoll` unverändert; `Evidenzprotokoll` selbst erzwingt die
  vier Mindestangaben (Anzahl Fälle > 0, Zeitraum konsistent,
  Signalquelle, Anlageklasse) strukturell per Pydantic-Vertrag —
  belegt hier zusätzlich, dass `erzeuge_hypothesen` keine
  Suchkriteria-Referenz entgegennimmt/zurückgibt (Signatur-Test) und die
  Reihenfolge der Eingabe erhält.
- **AC2 (Marktlogik-Filter):** eine `Musterbeobachtung` ohne marktlogische
  Begründung (`marktlogik=None` oder nur Leerraum) wird NICHT als
  Hypothese weitergegeben (stilles Verwerfen); eine mit Begründung schon.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contracts.research import Evidenzprotokoll, Hypothese, Musterbeobachtung
from app.domain.research.hypothesen_erzeugung import erzeuge_hypothesen


def _evidenz(**overrides: object) -> Evidenzprotokoll:
    defaults: dict[str, object] = {
        "anzahl_faelle": 12,
        "zeitraum_von": datetime(2026, 1, 1, tzinfo=UTC),
        "zeitraum_bis": datetime(2026, 6, 30, tzinfo=UTC),
        "signalquelle": "news-sentiment-feed",
        "anlageklasse": 1,
    }
    defaults.update(overrides)
    return Evidenzprotokoll(**defaults)  # type: ignore[arg-type]


def test_erzeuge_hypothesen_baut_hypothese_mit_marktlogik() -> None:
    """@trace lernschleife#AC1,AC2 — eine Musterbeobachtung mit
    marktlogischer Begründung wird zu genau einer Hypothese mit
    unverändertem Evidenzprotokoll."""
    evidenz = _evidenz()
    beobachtung = Musterbeobachtung(
        beschreibung="Small-Cap-Gewinner mit ungewöhnlich hohem RVOL vor News",
        marktlogik="Erhöhtes Handelsvolumen vor Nachrichtenveröffentlichung deutet auf "
        "Informationsvorlauf hin (marktlogisch erklärbar).",
        evidenz=evidenz,
    )

    ergebnis = erzeuge_hypothesen([beobachtung])

    assert len(ergebnis) == 1
    hypothese = ergebnis[0]
    assert isinstance(hypothese, Hypothese)
    assert isinstance(hypothese.hypothese_id, uuid.UUID)
    assert hypothese.beschreibung == beobachtung.beschreibung
    assert hypothese.marktlogik == beobachtung.marktlogik
    assert hypothese.evidenz == evidenz


@pytest.mark.parametrize("marktlogik", [None, "", "   "])
def test_erzeuge_hypothesen_verwirft_muster_ohne_marktlogische_begruendung(
    marktlogik: str | None,
) -> None:
    """@trace lernschleife#AC2 — rein statistische Zufallsmuster ohne
    marktlogische Begründung (None/leer/nur Leerraum) werden nicht als
    Hypothese weitergegeben."""
    beobachtung = Musterbeobachtung(
        beschreibung="Auffälliges Muster ohne erkennbare Erklärung",
        marktlogik=marktlogik,
        evidenz=_evidenz(),
    )

    ergebnis = erzeuge_hypothesen([beobachtung])

    assert ergebnis == []


def test_erzeuge_hypothesen_filtert_gemischte_liste_und_erhaelt_reihenfolge() -> None:
    """@trace lernschleife#AC1,AC2 — bei einer Mischung aus begründeten und
    unbegründeten Mustern werden nur die begründeten (in Eingabereihenfolge)
    zu Hypothesen."""
    begruendet_1 = Musterbeobachtung(
        beschreibung="Muster A", marktlogik="Marktlogik A", evidenz=_evidenz()
    )
    unbegruendet = Musterbeobachtung(beschreibung="Muster B", marktlogik=None, evidenz=_evidenz())
    begruendet_2 = Musterbeobachtung(
        beschreibung="Muster C", marktlogik="Marktlogik C", evidenz=_evidenz(anlageklasse=7)
    )

    ergebnis = erzeuge_hypothesen([begruendet_1, unbegruendet, begruendet_2])

    assert [h.beschreibung for h in ergebnis] == ["Muster A", "Muster C"]


def test_erzeuge_hypothesen_vergibt_je_hypothese_eine_eindeutige_id() -> None:
    """@trace lernschleife#AC1 — jede Hypothese erhält eine eigene,
    eindeutige `hypothese_id` (Basis für die spätere Trial-Registry-
    Zuordnung, AC3, Folge-Story)."""
    beobachtungen = [
        Musterbeobachtung(beschreibung=f"Muster {i}", marktlogik="Begründung", evidenz=_evidenz())
        for i in range(3)
    ]

    ergebnis = erzeuge_hypothesen(beobachtungen)

    ids = [h.hypothese_id for h in ergebnis]
    assert len(ids) == len(set(ids)) == 3


def test_erzeuge_hypothesen_leere_liste_liefert_leere_liste() -> None:
    """@trace lernschleife#AC1,AC2 — kein Muster, keine Hypothese, kein
    Fehler."""
    assert erzeuge_hypothesen([]) == []


def test_erzeuge_hypothesen_nimmt_keine_suchkriteria_referenz_entgegen() -> None:
    """@trace lernschleife#AC1 — "ändert die Suchkriterien niemals direkt":
    die Signatur nimmt strukturell keine Suchkriteria-Referenz entgegen und
    liefert auch keine zurück — die Funktion kann Suchkriteria damit gar
    nicht mutieren."""
    parameter = inspect.signature(erzeuge_hypothesen).parameters
    assert list(parameter) == ["musterbeobachtungen"]
    rueckgabe = inspect.signature(erzeuge_hypothesen).return_annotation
    assert rueckgabe == "list[Hypothese]"


class TestEvidenzprotokollMindestangaben:
    """@trace lernschleife#AC1 — das Evidenzprotokoll erzwingt die vier
    Mindestangaben (Anzahl Fälle, Zeitraum, Signalquelle, Anlageklasse)
    strukturell; eine Hypothese kann ohne sie gar nicht gebildet werden."""

    def test_anzahl_faelle_muss_positiv_sein(self) -> None:
        with pytest.raises(ValidationError):
            _evidenz(anzahl_faelle=0)

    def test_zeitraum_bis_darf_nicht_vor_zeitraum_von_liegen(self) -> None:
        with pytest.raises(ValidationError):
            _evidenz(
                zeitraum_von=datetime(2026, 6, 1, tzinfo=UTC),
                zeitraum_bis=datetime(2026, 1, 1, tzinfo=UTC),
            )

    def test_signalquelle_darf_nicht_leer_sein(self) -> None:
        with pytest.raises(ValidationError):
            _evidenz(signalquelle="")

    def test_anlageklasse_muss_in_gueltigem_bereich_liegen(self) -> None:
        with pytest.raises(ValidationError):
            _evidenz(anlageklasse=12)
        with pytest.raises(ValidationError):
            _evidenz(anlageklasse=0)
