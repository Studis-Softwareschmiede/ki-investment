"""Tests für die Depot-Übersicht-Query (`app.api.queries.depot`, Story
S-065, `docs/specs/frontend-cockpit.md` AC1/AC3/AC10).

Covers (frontend-cockpit): AC1, AC3, AC10

Deckt `hole_depot_uebersicht` unmittelbar (Fakes statt echter Session,
analog `tests/api/test_dashboard.py`): leeres Depot, mengen-gewichteter
Ø-Einstand über mehrere Lots, "nicht bewertbar" ohne Live-Kurs,
unrealisierter G/V mit Live-Kurs, Portfolio-Aggregate-Durchreichung und
der depotweite realisierte G/V (inkl. Mode-Isolation der `mode`-
Weiterleitung an beide Repository-Methoden). Die HTTP-/Router-Ebene
(coder/R06) deckt `tests/api/test_depot.py`."""

from __future__ import annotations

from decimal import Decimal

from app.api.queries.depot import hole_depot_uebersicht
from app.domain.portfolio.ports import ExitRegelnBestand, PositionsBestand


def _exit_regeln_leer() -> ExitRegelnBestand:
    return ExitRegelnBestand(
        stop_loss_pct=None,
        take_profit_pct=None,
        stop_typ=None,
        atr_multiplikator=None,
        thesis_invalidation=None,
        time_box=None,
    )


def _position(
    titel_id: str,
    *,
    menge: Decimal,
    einstand_preis: Decimal,
    asset_class_id: int = 1,
    gics_branche: str | None = "Technology",
    position_id: str = "lot-1",
) -> PositionsBestand:
    return PositionsBestand(
        position_id=position_id,
        titel_id=titel_id,
        asset_class_id=asset_class_id,
        gics_branche=gics_branche,
        menge=menge,
        einstand_preis=einstand_preis,
        strategie="Index",
        exit_regeln=_exit_regeln_leer(),
    )


class _FakePositionRepository:
    """Test-Double des `PositionRepository`-Ports — implementiert nur die
    von `hole_depot_uebersicht` tatsächlich aufgerufenen Methoden."""

    def __init__(self, positionen, realisierter_gv_gesamt: Decimal = Decimal("0")):
        self._positionen = positionen
        self._realisierter_gv_gesamt = realisierter_gv_gesamt
        self.abgefragte_modi: list[str] = []
        self.realisierter_gv_modi: list[str] = []

    def alle_offenen_positionen(self, *, mode):
        self.abgefragte_modi.append(mode)
        return self._positionen

    def realisierter_gv_gesamt(self, *, mode):
        self.realisierter_gv_modi.append(mode)
        return self._realisierter_gv_gesamt


class _FakeLivePriceProvider:
    def __init__(self, preise: dict[str, Decimal]):
        self._preise = preise

    def aktueller_preis(self, titel_id):
        return self._preise.get(titel_id)


def test_leeres_depot_liefert_leere_titel_liste_und_leere_aggregate():
    repository = _FakePositionRepository(positionen=[])
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    assert ergebnis.mode == "echt"
    assert ergebnis.titel == []
    assert ergebnis.portfolio_aggregat.branchen_gewichtung == {}
    assert ergebnis.portfolio_aggregat.klassen_gewichtung == {}
    assert ergebnis.portfolio_aggregat.cash_quote == Decimal("0")
    assert ergebnis.realisierter_gv_gesamt == Decimal("0")
    assert repository.abgefragte_modi == ["echt"]
    assert repository.realisierter_gv_modi == ["echt"]


def test_position_ohne_live_kurs_ist_nicht_bewertbar():
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    eintrag = ergebnis.titel[0]
    assert eintrag.aktueller_preis is None
    assert eintrag.unrealisierter_gv is None


def test_unrealisierter_gv_mit_live_kurs():
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({"titel-1": Decimal("120")})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    eintrag = ergebnis.titel[0]
    assert eintrag.aktueller_preis == Decimal("120")
    # (120 - 100) * 10 = 200
    assert eintrag.unrealisierter_gv == Decimal("200")


def test_mengen_gewichteter_einstand_ueber_mehrere_lots():
    positionen = [
        _position(
            "titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"), position_id="lot-1"
        ),
        _position("titel-1", menge=Decimal("5"), einstand_preis=Decimal("70"), position_id="lot-2"),
    ]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    assert len(ergebnis.titel) == 1
    eintrag = ergebnis.titel[0]
    assert eintrag.menge == Decimal("15")
    # (10*100 + 5*70) / 15 = 1350 / 15 = 90
    assert eintrag.einstand_preis == Decimal("90")


def test_portfolio_aggregat_wird_durchgereicht():
    positionen = [
        _position(
            "titel-1",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
            asset_class_id=1,
            gics_branche="Technology",
        ),
        _position(
            "titel-2",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
            asset_class_id=3,
            gics_branche=None,
            position_id="lot-2",
        ),
    ]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    # Beide Titel je 1000 Kostenbasis -> je 50% Gewichtung.
    assert ergebnis.portfolio_aggregat.klassen_gewichtung == {
        1: Decimal("50.000"),
        3: Decimal("50.000"),
    }
    # Anlageklasse 3 = Cash/Geldmarkt (CASH_ASSET_CLASS_ID).
    assert ergebnis.portfolio_aggregat.cash_quote == Decimal("50.000")


def test_realisierter_gv_gesamt_wird_durchgereicht():
    repository = _FakePositionRepository(positionen=[], realisierter_gv_gesamt=Decimal("250"))
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    assert ergebnis.realisierter_gv_gesamt == Decimal("250")


def test_mode_wird_an_beide_repository_methoden_durchgereicht():
    repository = _FakePositionRepository(positionen=[])
    live_price = _FakeLivePriceProvider({})

    hole_depot_uebersicht(mode="simuliert", repository=repository, live_price=live_price)

    assert repository.abgefragte_modi == ["simuliert"]
    assert repository.realisierter_gv_modi == ["simuliert"]
