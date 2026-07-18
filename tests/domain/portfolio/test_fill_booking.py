"""Tests für das Fill-Buchungs-Gate (Story S-015).

Covers (depot): AC1, AC10

`app.domain.portfolio.fill_booking.pruefe_fill` ist der Buchungs-
Eintrittspunkt (AC1/AC10) — bucht selbst nichts (kein DB-Write), sondern
entscheidet "gebucht" vs. "abgelehnt". Diese Tests decken:
- AC10 (universelle Pflichtfelder fehlen → abgelehnt, protokolliert,
  Bestand unverändert; deckt E1),
- AC1 (bei Kauf fehlendes Positions-Attribut → abgelehnt, protokolliert),
- AC10 (resultierende negative Menge bei Verkauf über Bestand hinaus →
  abgelehnt, protokolliert),
- den Erfolgsfall (vollständiger Fill → gebucht, korrekte resultierende
  Menge, kein Protokolleintrag).

DBA-Zweit-Review von S-016 (ADR-011/P8) ergänzt `client_order_id` als
neues universelles Pflichtfeld in den Rohdaten-Factories sowie in der
AC10-Pflichtfeld-Parametrisierung (`test_lehnt_fill_mit_fehlendem_...`).

DBA-Re-Review S-016 (Iteration 3, Important — Mode-Isolation, BR-113/
BR-130) zieht denselben Fix hier nach: `_FakeRepository.aktuelle_menge`
nimmt jetzt `mode` entgegen (Protokoll-Kompatibilität mit
`app.domain.portfolio.ports.PositionRepository.aktuelle_menge`), auf das
`pruefe_fill` mit `fill.mode` aufruft.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.core import depot_audit_log
from app.domain.portfolio.fill_booking import pruefe_fill

_ZEITSTEMPEL = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
_TITEL_ID = "11111111-1111-1111-1111-111111111111"


class _FakeRepository:
    """Test-Double für `PositionRepository` — fester, injizierbarer
    aktueller Bestand je Titel."""

    def __init__(self, bestand: Decimal = Decimal("0")) -> None:
        self._bestand = bestand

    def aktuelle_menge(self, titel_id: str, *, mode: str) -> Decimal:
        return self._bestand


@pytest.fixture(autouse=True)
def _reset_audit_log() -> None:
    depot_audit_log.reset_fuer_tests()
    yield
    depot_audit_log.reset_fuer_tests()


def _kauf_rohdaten(**overrides: object) -> dict:
    rohdaten = {
        "client_order_id": "order-kauf-1",
        "titel_id": _TITEL_ID,
        "anlageklasse": 1,
        "gics_branche": "Technology",
        "richtung": "kauf",
        "menge": Decimal("10"),
        "fill_preis": Decimal("100.50"),
        "kosten": Decimal("2.50"),
        "arrival_price": Decimal("100.00"),
        "waehrung": "CHF",
        "zeitstempel": _ZEITSTEMPEL,
        "mode": "simuliert",
        "strategie": "Index",
        "zeithorizont": 8,
        "exit_regeln": {
            "stop_typ": "atr_trailing",
            "stop_parameter": 2.5,
            "thesis_invalidierung": "Wachstum < 5%.",
        },
        "these": "Langfristiger Index-Halter.",
    }
    rohdaten.update(overrides)
    return rohdaten


def _verkauf_rohdaten(**overrides: object) -> dict:
    rohdaten = {
        "client_order_id": "order-verkauf-1",
        "titel_id": _TITEL_ID,
        "anlageklasse": 1,
        "gics_branche": "Technology",
        "richtung": "verkauf",
        "menge": Decimal("5"),
        "fill_preis": Decimal("110.00"),
        "kosten": Decimal("1.50"),
        "arrival_price": Decimal("109.50"),
        "waehrung": "CHF",
        "zeitstempel": _ZEITSTEMPEL,
        "mode": "simuliert",
    }
    rohdaten.update(overrides)
    return rohdaten


def test_bucht_vollstaendigen_kauf_und_berechnet_resultierende_menge() -> None:
    """@trace depot#AC1,AC10 — ein vollständiger Kauf-Fill wird gebucht;
    die resultierende Menge ist Bestand + Fill-Menge, kein
    Protokolleintrag entsteht."""
    ergebnis = pruefe_fill(_kauf_rohdaten(), repository=_FakeRepository(Decimal("0")))
    assert ergebnis.status == "gebucht"
    assert ergebnis.resultierende_menge == Decimal("10")
    assert ergebnis.fill is not None
    assert ergebnis.protokoll_eintrag is None
    assert depot_audit_log.alle_eintraege() == ()


def test_bucht_verkauf_der_bestand_exakt_auf_null_reduziert() -> None:
    """@trace depot#AC10 — Verkauf, der den Bestand exakt auf 0 reduziert,
    ist erlaubt (0 ist NICHT negativ)."""
    ergebnis = pruefe_fill(
        _verkauf_rohdaten(menge=Decimal("5")), repository=_FakeRepository(Decimal("5"))
    )
    assert ergebnis.status == "gebucht"
    assert ergebnis.resultierende_menge == Decimal("0")


@pytest.mark.parametrize(
    "missing_field",
    ["client_order_id", "titel_id", "menge", "fill_preis", "kosten", "zeitstempel", "mode"],
)
def test_lehnt_fill_mit_fehlendem_pflichtfeld_ab_und_protokolliert(missing_field: str) -> None:
    """@trace depot#AC10 — fehlt ein universelles Pflichtfeld (deckt E1:
    Menge, Fill-Preis, Kosten, Zeitstempel), wird der Fill NICHT gebucht,
    sondern als fehlerhaft protokolliert; der Bestand bleibt unverändert
    (hier: Repository wird gar nicht erst nach dem Bestand gefragt)."""
    rohdaten = _verkauf_rohdaten()
    del rohdaten[missing_field]

    ergebnis = pruefe_fill(rohdaten, repository=_FakeRepository(Decimal("100")))

    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "unvollstaendig"
    assert ergebnis.fill is None
    assert ergebnis.resultierende_menge is None
    assert ergebnis.protokoll_eintrag is not None
    assert ergebnis.protokoll_eintrag.grund == "unvollstaendig"
    eintraege = depot_audit_log.alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "unvollstaendig"


@pytest.mark.parametrize("missing_field", ["strategie", "zeithorizont", "exit_regeln", "these"])
def test_lehnt_kauf_mit_fehlendem_positions_attribut_ab_und_protokolliert(
    missing_field: str,
) -> None:
    """@trace depot#AC1 — fehlt bei einem Kauf eines der Positions-
    Attribute (Strategie, Zeithorizont, Exit-Regeln, These), wird die
    Position nicht stillschweigend akzeptiert: der Fill wird abgelehnt und
    protokolliert."""
    rohdaten = _kauf_rohdaten()
    del rohdaten[missing_field]

    ergebnis = pruefe_fill(rohdaten, repository=_FakeRepository(Decimal("0")))

    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "unvollstaendig"
    assert depot_audit_log.alle_eintraege()[0].grund == "unvollstaendig"


def test_lehnt_verkauf_ueber_bestand_hinaus_ab_und_protokolliert() -> None:
    """@trace depot#AC10 — ein Verkauf, dessen Menge den vorhandenen
    Bestand übersteigt (resultierende negative Menge), wird nicht gebucht,
    sondern protokolliert; der Bestand bleibt unverändert (Fake-Repository
    wird nicht mutiert)."""
    ergebnis = pruefe_fill(
        _verkauf_rohdaten(menge=Decimal("10")), repository=_FakeRepository(Decimal("5"))
    )

    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "negative_menge"
    assert ergebnis.fill is None
    eintraege = depot_audit_log.alle_eintraege()
    assert len(eintraege) == 1
    assert eintraege[0].grund == "negative_menge"
    assert eintraege[0].titel_id == _TITEL_ID
    assert eintraege[0].richtung == "verkauf"


def test_lehnt_verkauf_ohne_jede_offene_position_ab() -> None:
    """@trace depot#AC10 — ein Verkauf ohne jede offene Position (Bestand
    0) ergibt zwingend eine negative resultierende Menge und wird
    abgelehnt."""
    ergebnis = pruefe_fill(
        _verkauf_rohdaten(menge=Decimal("1")), repository=_FakeRepository(Decimal("0"))
    )
    assert ergebnis.status == "abgelehnt"
    assert ergebnis.grund == "negative_menge"
