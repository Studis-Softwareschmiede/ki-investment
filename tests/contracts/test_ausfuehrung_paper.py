"""Tests für die S-046-Order-Ausführungs-Verträge (`app.contracts
.ausfuehrung_paper.OrderAnfrage`/`OrderBestaetigung`/
`BrokerRoutingKonfiguration`).

Covers (ausfuehrung-paper): AC1, AC5, AC6

Reine DTO-Validierungstests (pydantic `frozen`/`extra="forbid"`/
Feld-Constraints) — das Verhalten der erzeugenden/konsumierenden Funktionen
liegt in `tests/domain/execution/test_order_ausfuehrung.py`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.ausfuehrung_paper import (
    DEFAULT_BROKERLOSE_ANLAGEKLASSEN_IDS,
    BrokerRoutingKonfiguration,
    OrderAnfrage,
    OrderBestaetigung,
)


def _order_anfrage_kwargs(**overrides: object) -> dict[str, object]:
    basis: dict[str, object] = dict(
        titel_id="AAPL",
        asset_class_id=1,
        richtung="kauf",
        groesse=Decimal("500"),
        order_typ="limit",
        preis=Decimal("150"),
    )
    basis.update(overrides)
    return basis


def test_ac1_order_anfrage_ist_unveraenderlich_und_lehnt_unbekannte_felder_ab() -> None:
    """@trace ausfuehrung-paper#AC1 — `OrderAnfrage` ist `frozen`/
    `extra="forbid"` (P2, Modul-Vertrag)."""
    anfrage = OrderAnfrage(**_order_anfrage_kwargs())

    with pytest.raises(ValidationError):
        anfrage.groesse = Decimal("999")  # type: ignore[misc]

    with pytest.raises(ValidationError):
        OrderAnfrage(**_order_anfrage_kwargs(unbekanntes_feld="x"))


def test_ac1_order_anfrage_lehnt_nicht_positive_groesse_ab() -> None:
    """@trace ausfuehrung-paper#AC1 — eine Order ohne positive Grösse ist
    kein gültiger Vertrag (`groesse: Decimal = Field(gt=0)`)."""
    with pytest.raises(ValidationError):
        OrderAnfrage(**_order_anfrage_kwargs(groesse=Decimal("0")))


@pytest.mark.parametrize("order_typ", ["market", "limit", "stop", "stop_limit", "trailing", "twap"])
def test_ac6_order_anfrage_akzeptiert_alle_execution_order_typen(order_typ: str) -> None:
    """@trace ausfuehrung-paper#AC6 — `OrderAnfrage.order_typ` akzeptiert
    alle 6 AC6-Order-Typen."""
    anfrage = OrderAnfrage(**_order_anfrage_kwargs(order_typ=order_typ))
    assert anfrage.order_typ == order_typ


def test_ac6_order_anfrage_lehnt_unbekannten_order_typ_ab() -> None:
    """@trace ausfuehrung-paper#AC6 — ein Order-Typ ausserhalb des
    AC6-Wertebereichs wird abgelehnt."""
    with pytest.raises(ValidationError):
        OrderAnfrage(**_order_anfrage_kwargs(order_typ="iceberg"))


def test_ac1_order_bestaetigung_ist_unveraenderlich() -> None:
    """@trace ausfuehrung-paper#AC1 — `OrderBestaetigung` ist ebenfalls
    `frozen`/`extra="forbid"`."""
    bestaetigung = OrderBestaetigung(
        order_id="abc-123",
        broker_endpunkt_typ="ibkr_paper",
        titel_id="AAPL",
        richtung="kauf",
        order_typ="market",
        groesse=Decimal("500"),
    )

    with pytest.raises(ValidationError):
        bestaetigung.order_id = "anders"  # type: ignore[misc]


def test_ac5_broker_routing_konfiguration_default_ist_nur_krypto() -> None:
    """@trace ausfuehrung-paper#AC5 — der Default der brokerlosen
    Anlageklassen enthält ausschliesslich Krypto (7)."""
    konfiguration = BrokerRoutingKonfiguration()
    assert konfiguration.brokerlose_anlageklassen_ids == DEFAULT_BROKERLOSE_ANLAGEKLASSEN_IDS
    assert konfiguration.brokerlose_anlageklassen_ids == frozenset({7})
