"""Tests für die Query-Funktion
`app.api.queries.entscheide.offene_entscheide_uebersicht` (Story S-080,
`docs/specs/frontend-cockpit.md` AC29/AC31).

Covers (frontend-cockpit): AC29, AC31

Isolierter Unit-Test der Query-Funktion selbst (Fake-
`HybridEntscheidungRepository`, kein HTTP) — Ergänzung zum
HTTP-Ebenen-Test `tests/api/test_entscheide.py` (coder/R06). Belegt AC29
(alle Felder verlustfrei) und AC31 (Feature-Gate: `feature_aktiv=False`
liefert IMMER eine leere Liste, OHNE das Repository zu befragen)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.api.queries.entscheide import offene_entscheide_uebersicht
from app.domain.hybrid_entscheidung.ports import OffenerEntscheidZeile


class _FakeHybridEntscheidungRepository:
    def __init__(self, eintraege: list[OffenerEntscheidZeile]):
        self._eintraege = eintraege
        self.aufrufe = 0

    def offene_entscheide(self) -> list[OffenerEntscheidZeile]:
        self.aufrufe += 1
        return self._eintraege


def _zeile(**overrides: object) -> OffenerEntscheidZeile:
    basis: dict[str, object] = {
        "entscheid_id": "e-1",
        "titel_id": "titel-1",
        "titel": "ROG",
        "name": "Roche Holding AG",
        "richtung": "kauf",
        "groesse": Decimal("5"),
        "vorgeschlagene_order": "Market-Buy 5 Stk. Roche Holding AG",
        "frist": datetime(2026, 7, 20, 16, 0, tzinfo=UTC),
        "begruendung": "Gesamtscore 8.5 (KAUF-Schwelle).",
        "erstellt_am": datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
    }
    basis.update(overrides)
    return OffenerEntscheidZeile(**basis)  # type: ignore[arg-type]


def test_feature_inaktiv_liefert_immer_leere_liste_ohne_repository_aufruf():
    """@trace frontend-cockpit#AC31 — `feature_aktiv=False` liefert eine
    leere Liste, das Repository wird NICHT befragt (Default-aus-
    Invariante gilt unabhängig vom DB-Inhalt)."""
    repository = _FakeHybridEntscheidungRepository([_zeile()])

    ergebnis = offene_entscheide_uebersicht(repository, feature_aktiv=False)

    assert ergebnis.feature_aktiv is False
    assert ergebnis.entscheide == []
    assert repository.aufrufe == 0


def test_feature_aktiv_liefert_alle_ac29_felder_verlustfrei():
    """@trace frontend-cockpit#AC29 — Titel, Richtung, Grösse,
    vorgeschlagene Order, Frist, Begründung landen unverändert im DTO."""
    repository = _FakeHybridEntscheidungRepository([_zeile()])

    ergebnis = offene_entscheide_uebersicht(repository, feature_aktiv=True)

    assert ergebnis.feature_aktiv is True
    assert len(ergebnis.entscheide) == 1
    eintrag = ergebnis.entscheide[0]
    assert eintrag.entscheid_id == "e-1"
    assert eintrag.titel_id == "titel-1"
    assert eintrag.titel == "ROG"
    assert eintrag.name == "Roche Holding AG"
    assert eintrag.richtung == "kauf"
    assert eintrag.groesse == Decimal("5")
    assert eintrag.vorgeschlagene_order == "Market-Buy 5 Stk. Roche Holding AG"
    assert eintrag.frist == datetime(2026, 7, 20, 16, 0, tzinfo=UTC)
    assert eintrag.begruendung == "Gesamtscore 8.5 (KAUF-Schwelle)."
    assert eintrag.erstellt_am == datetime(2026, 7, 18, 9, 0, tzinfo=UTC)


def test_feature_aktiv_ohne_offene_entscheide_liefert_leere_liste():
    """@trace frontend-cockpit#AC29,AC31 — solange der autonome
    Paper-Modus aktiv ist (bzw. kein offener Entscheid existiert), ist die
    Liste leer, auch bei aktivem Flag."""
    repository = _FakeHybridEntscheidungRepository([])

    ergebnis = offene_entscheide_uebersicht(repository, feature_aktiv=True)

    assert ergebnis.feature_aktiv is True
    assert ergebnis.entscheide == []
    assert repository.aufrufe == 1
