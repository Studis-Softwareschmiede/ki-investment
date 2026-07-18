"""Tests für die S-046-Order-Ausführungs-Verträge (`app.contracts
.ausfuehrung_paper.OrderAnfrage`/`OrderBestaetigung`/
`BrokerRoutingKonfiguration`) + die S-047-`ModusKonfiguration` + die
S-048-Fill-Handling-Verträge (`BrokerFillMeldung`/`Ausfuehrungsergebnis`).

Covers (ausfuehrung-paper): AC1, AC2, AC5, AC6, AC7, AC8

Reine DTO-Validierungstests (pydantic `frozen`/`extra="forbid"`/
Feld-Constraints) — das Verhalten der erzeugenden/konsumierenden Funktionen
liegt in `tests/domain/execution/test_order_ausfuehrung.py` (AC1-AC6, S-046/
S-047) bzw. `tests/domain/execution/test_order_ausfuehrung_fill.py` (AC7/AC8,
S-048).

- AC2 (Review-Fix, Sicherheit): `ModusKonfiguration.modus_je_anlageklasse`
  ist trotz `frozen=True` NICHT nur top-level unveränderlich — das
  `dict`-Feld selbst wird per `field_validator` in ein echtes
  `types.MappingProxyType` gewandelt, eine nachträgliche Mutation des
  Mappings wird dadurch verhindert (siehe
  `test_ac2_modus_je_anlageklasse_mapping_ist_wirklich_unveraenderlich`).
- AC7/AC8 (S-048): `BrokerFillMeldung`/`Ausfuehrungsergebnis` sind ebenfalls
  `frozen`/`extra="forbid"` (P2, Modul-Vertrag)."""

from __future__ import annotations

from decimal import Decimal
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from app.contracts.ausfuehrung_paper import (
    DEFAULT_BROKERLOSE_ANLAGEKLASSEN_IDS,
    Ausfuehrungsergebnis,
    BrokerFillMeldung,
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


def test_ac2_modus_je_anlageklasse_mapping_ist_wirklich_unveraenderlich() -> None:
    """@trace ausfuehrung-paper#AC2 — Review-Fix (Sicherheit):
    `frozen=True` friert nur die Top-Level-Attribute des Modells ein; ohne
    weitere Massnahme bliebe das `dict`-Feld `modus_je_anlageklasse`
    inhaltlich mutabel (`konfiguration.modus_je_anlageklasse[1] = "echt"`
    würde durchgehen). Der `field_validator` wandelt das Feld in ein
    echtes `types.MappingProxyType` — eine Item-Zuweisung MUSS mit
    `TypeError` scheitern, sowohl bei explizit übergebenem Mapping als
    auch beim Default (`validate_default=True`, sonst würde nur der
    explizite Konstruktions-Pfad geschützt)."""
    konfiguration = ModusKonfiguration(modus_je_anlageklasse={1: "echt", 7: "simuliert"})
    assert isinstance(konfiguration.modus_je_anlageklasse, MappingProxyType)
    with pytest.raises(TypeError):
        konfiguration.modus_je_anlageklasse[1] = "simuliert"  # type: ignore[index]

    default_konfiguration = ModusKonfiguration()
    assert isinstance(default_konfiguration.modus_je_anlageklasse, MappingProxyType)
    with pytest.raises(TypeError):
        default_konfiguration.modus_je_anlageklasse[1] = "echt"  # type: ignore[index]


# ---------------------------------------------------------------------------
# AC7/AC8 (S-048) — Fill-Handling-Verträge
# ---------------------------------------------------------------------------


def test_ac7_ac8_broker_fill_meldung_ist_unveraenderlich_und_lehnt_unbekannte_felder_ab() -> None:
    """@trace ausfuehrung-paper#AC7,AC8 — `BrokerFillMeldung` ist `frozen`/
    `extra="forbid"` (P2, Modul-Vertrag)."""
    meldung = BrokerFillMeldung(status="filled", ausgefuehrte_menge=Decimal("10"))

    with pytest.raises(ValidationError):
        meldung.status = "rejected"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        BrokerFillMeldung(status="filled", unbekanntes_feld="x")


def test_ac8_broker_fill_meldung_defaults_passen_zu_keinem_fill() -> None:
    """@trace ausfuehrung-paper#AC8 — ohne weitere Angabe (z.B. bei einem
    Reject/Timeout) sind `ausgefuehrte_menge=0`, `fill_preis=None`,
    `tatsaechliche_kosten=0`."""
    meldung = BrokerFillMeldung(status="rejected", ablehnungsgrund="Test")
    assert meldung.ausgefuehrte_menge == Decimal("0")
    assert meldung.fill_preis is None
    assert meldung.tatsaechliche_kosten == Decimal("0")


def _ausfuehrungsergebnis_kwargs(**overrides: object) -> dict[str, object]:
    basis: dict[str, object] = dict(
        order_id="order-1",
        titel_id="AAPL",
        richtung="kauf",
        status="filled",
        angefragte_menge=Decimal("10"),
        ausgefuehrte_menge=Decimal("10"),
        fill_preis=Decimal("151"),
        tatsaechliche_kosten=Decimal("2"),
        arrival_price=Decimal("150"),
        slippage=Decimal("1"),
        restmenge=Decimal("0"),
        restmenge_verhalten=None,
        ablehnungsgrund=None,
    )
    basis.update(overrides)
    return basis


def test_ac7_ac8_ausfuehrungsergebnis_ist_unveraenderlich_und_lehnt_unbekannte_felder_ab() -> None:
    """@trace ausfuehrung-paper#AC7,AC8 — `Ausfuehrungsergebnis` ist ebenfalls
    `frozen`/`extra="forbid"` (P2, Modul-Vertrag)."""
    ergebnis = Ausfuehrungsergebnis(**_ausfuehrungsergebnis_kwargs())

    with pytest.raises(ValidationError):
        ergebnis.status = "rejected"  # type: ignore[misc]

    with pytest.raises(ValidationError):
        Ausfuehrungsergebnis(**_ausfuehrungsergebnis_kwargs(unbekanntes_feld="x"))


def test_ac8_ausfuehrungsergebnis_akzeptiert_reject_ohne_fill_preis() -> None:
    """@trace ausfuehrung-paper#AC8 — E2/E3: `fill_preis`/`slippage`/
    `restmenge_verhalten` sind strukturell optional (`None` bei Reject/
    Timeout, kein Fill)."""
    ergebnis = Ausfuehrungsergebnis(
        **_ausfuehrungsergebnis_kwargs(
            status="rejected",
            ausgefuehrte_menge=Decimal("0"),
            fill_preis=None,
            tatsaechliche_kosten=Decimal("0"),
            slippage=None,
            restmenge=Decimal("10"),
            restmenge_verhalten=None,
            ablehnungsgrund="Kontingent erschöpft",
        )
    )
    assert ergebnis.fill_preis is None
    assert ergebnis.slippage is None
    assert ergebnis.ablehnungsgrund == "Kontingent erschöpft"
