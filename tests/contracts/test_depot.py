"""Tests für den Depot-Fill-Vertrag (Story S-015 + S-016 DBA-Zweit-Review).

Covers (depot): AC1, AC10

`app.contracts.depot.FillInput` bildet den Fill-Input-Vertrag aus
`docs/specs/depot.md` ab. Diese Tests decken AC10 (universelle
Pflichtfelder — fehlt eines, verweigert pydantic die Instanziierung) und
AC1 (bei Kauf zusätzlich Strategie/Zeithorizont/Exit-Regeln/These Pflicht;
bei Verkauf bleiben sie zulässig `None`).

DBA-Zweit-Review von S-016 (Critical + Suggestion, ADR-011) ergänzt
`client_order_id` als neues universelles Pflichtfeld (Dedup-Schlüssel) in
der bestehenden AC10-Pflichtfeld-Parametrisierung sowie einen Ablehnungstest
für `menge <= 0` (Erst-Review-Suggestion, `gt=0`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.depot import ExitRegeln, FillInput

_ZEITSTEMPEL = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)

VALID_KAUF_KWARGS = {
    "client_order_id": "order-kauf-1",
    "titel_id": "11111111-1111-1111-1111-111111111111",
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
    "exit_regeln": ExitRegeln(stop_typ="atr_trailing", stop_parameter=2.5),
    "these": "Langfristiger Index-Halter.",
}

VALID_VERKAUF_KWARGS = {
    "client_order_id": "order-verkauf-1",
    "titel_id": "11111111-1111-1111-1111-111111111111",
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


def test_accepts_kauf_with_all_pflichtfelder() -> None:
    """@trace depot#AC1,AC10 — ein Kauf-Fill mit allen universellen
    Pflichtfeldern PLUS den Kauf-Pflichtattributen (Strategie, Zeithorizont,
    Exit-Regeln, These) wird gebaut."""
    fill = FillInput(**VALID_KAUF_KWARGS)
    assert fill.richtung == "kauf"
    assert fill.strategie == "Index"
    assert fill.exit_regeln is not None
    assert fill.exit_regeln.stop_typ == "atr_trailing"


def test_accepts_verkauf_without_kauf_only_attribute() -> None:
    """@trace depot#AC1 — ein Verkauf-Fill braucht Strategie/Zeithorizont/
    Exit-Regeln/These NICHT (bereits beim ursprünglichen Kauf fixiert,
    BR-010) — bleibt `None`, ohne die Instanziierung zu verweigern."""
    fill = FillInput(**VALID_VERKAUF_KWARGS)
    assert fill.richtung == "verkauf"
    assert fill.strategie is None
    assert fill.exit_regeln is None
    assert fill.these is None


@pytest.mark.parametrize(
    "missing_field",
    [
        "client_order_id",
        "titel_id",
        "anlageklasse",
        "gics_branche",
        "richtung",
        "menge",
        "fill_preis",
        "kosten",
        "arrival_price",
        "waehrung",
        "zeitstempel",
        "mode",
    ],
)
def test_rejects_missing_universelles_pflichtfeld(missing_field: str) -> None:
    """@trace depot#AC10 — fehlt eines der universellen Pflichtfelder
    (deckt E1: Menge, Fill-Preis, Kosten, Zeitstempel u.a.), verweigert
    pydantic die Instanziierung — unabhängig von Kauf/Verkauf."""
    kwargs = dict(VALID_VERKAUF_KWARGS)
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        FillInput(**kwargs)


@pytest.mark.parametrize("missing_field", ["strategie", "zeithorizont", "exit_regeln", "these"])
def test_rejects_kauf_missing_positions_attribut(missing_field: str) -> None:
    """@trace depot#AC1 — fehlt bei einem Kauf eines der Positions-
    Attribute (Strategie, Zeithorizont, Exit-Regeln, These), verweigert
    pydantic die Instanziierung — die Position wird nie mit einer
    stillschweigenden Lücke angelegt."""
    kwargs = dict(VALID_KAUF_KWARGS)
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        FillInput(**kwargs)


def test_rejects_kauf_with_blank_these() -> None:
    """@trace depot#AC1 — ein Leerstring zählt als fehlendes
    Pflichtattribut, nicht nur Schlüssel-Abwesenheit (Konvention analog zu
    `app.contracts.dateneingang.Datenpunkt`)."""
    kwargs = dict(VALID_KAUF_KWARGS, these="   ")
    with pytest.raises(ValidationError):
        FillInput(**kwargs)


def test_rejects_anlageklasse_outside_1_to_11() -> None:
    """@trace depot#AC10 — Anlageklasse ausserhalb 1..11 ist ungültig."""
    with pytest.raises(ValidationError):
        FillInput(**dict(VALID_VERKAUF_KWARGS, anlageklasse=12))


@pytest.mark.parametrize("ungueltige_menge", [Decimal("0"), Decimal("-1")])
def test_rejects_menge_kleiner_gleich_null(ungueltige_menge: Decimal) -> None:
    """@trace depot#AC10 — eine Menge <= 0 ist strukturell kein gültiger
    Fill (Erst-Review-Suggestion, `gt=0`) — verhindert insbesondere einen
    ZeroDivisionError bei der anteiligen Kostenverteilung
    (`app.domain.portfolio.position_booking`)."""
    with pytest.raises(ValidationError):
        FillInput(**dict(VALID_VERKAUF_KWARGS, menge=ungueltige_menge))


def test_rejects_empty_titel_id_and_gics_branche() -> None:
    """@trace depot#AC10 — leere Strings zählen als fehlendes
    Pflichtfeld (nicht nur `None`/Schlüssel-Abwesenheit)."""
    with pytest.raises(ValidationError):
        FillInput(**dict(VALID_VERKAUF_KWARGS, titel_id=""))
    with pytest.raises(ValidationError):
        FillInput(**dict(VALID_VERKAUF_KWARGS, gics_branche=""))


def test_fill_input_is_immutable() -> None:
    """@trace depot#AC1 — `FillInput` ist frozen (unveränderliches DTO,
    passend zum Modul-Vertrag P2)."""
    fill = FillInput(**VALID_VERKAUF_KWARGS)
    with pytest.raises(ValidationError):
        fill.menge = Decimal("999")
