"""Tests für die S-046-Order-Ausführungs-Verträge (`app.contracts
.ausfuehrung_paper.OrderAnfrage`/`OrderBestaetigung`/
`BrokerRoutingKonfiguration`) + die S-047-`ModusKonfiguration`.

Covers (ausfuehrung-paper): AC1, AC2, AC5, AC6

Reine DTO-Validierungstests (pydantic `frozen`/`extra="forbid"`/
Feld-Constraints) — das Verhalten der erzeugenden/konsumierenden Funktionen
liegt in `tests/domain/execution/test_order_ausfuehrung.py` (dort auch die
AC2/AC3-Auflösungslogik von `bestimme_wirksamen_modus`, S-047).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.ausfuehrung_paper import (
    DEFAULT_BROKERLOSE_ANLAGEKLASSEN_IDS,
    BrokerRoutingKonfiguration,
    ModusKonfiguration,
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


def test_ac2_modus_konfiguration_default_ist_global_simuliert_ohne_overrides() -> None:
    """@trace ausfuehrung-paper#AC2 — der Default ist `global_modus =
    "simuliert"` ohne Anlageklassen-Overrides (MVP-Default)."""
    konfiguration = ModusKonfiguration()
    assert konfiguration.global_modus == "simuliert"
    assert konfiguration.modus_je_anlageklasse == {}


def test_ac2_modus_konfiguration_akzeptiert_je_anlageklasse_override() -> None:
    """@trace ausfuehrung-paper#AC2 — je Anlageklasse ist der Modus
    strukturell überschreibbar (auch mit `"echt"`, forward-kompatibel —
    die MVP-Sperre erzwingt erst `bestimme_wirksamen_modus`, siehe
    `tests/domain/execution/test_order_ausfuehrung.py`)."""
    konfiguration = ModusKonfiguration(
        global_modus="simuliert", modus_je_anlageklasse={1: "echt", 7: "simuliert"}
    )
    assert konfiguration.modus_je_anlageklasse == {1: "echt", 7: "simuliert"}


def test_ac2_modus_konfiguration_ist_unveraenderlich_und_lehnt_unbekannte_felder_ab() -> None:
    """@trace ausfuehrung-paper#AC2 — `ModusKonfiguration` ist ebenfalls
    `frozen`/`extra="forbid"` (P2, Modul-Vertrag)."""
    konfiguration = ModusKonfiguration()

    with pytest.raises(ValidationError):
        konfiguration.global_modus = "echt"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        ModusKonfiguration(unbekanntes_feld="x")


def test_ac2_modus_konfiguration_lehnt_unbekannten_modus_wert_ab() -> None:
    """@trace ausfuehrung-paper#AC2 — `global_modus`/`modus_je_anlageklasse`
    akzeptieren ausschliesslich den `Modus`-Wertebereich (`echt`/
    `simuliert`)."""
    with pytest.raises(ValidationError):
        ModusKonfiguration(global_modus="paper")  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        ModusKonfiguration(modus_je_anlageklasse={1: "papier"})  # type: ignore[dict-item]
