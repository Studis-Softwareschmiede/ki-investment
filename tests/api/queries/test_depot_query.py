"""Tests für die Depot-Übersicht-Query (`app.api.queries.depot`, Story
S-065/S-071, `docs/specs/frontend-cockpit.md` AC1/AC3/AC10/AC14).

Covers (frontend-cockpit): AC1, AC3, AC10, AC14

Deckt `hole_depot_uebersicht` unmittelbar (Fakes statt echter Session,
analog `tests/api/test_dashboard.py`): leeres Depot, mengen-gewichteter
Ø-Einstand über mehrere Lots, "nicht bewertbar" ohne Live-Kurs,
unrealisierter G/V mit Live-Kurs, Portfolio-Aggregate-Durchreichung, der
depotweite realisierte G/V (inkl. Mode-Isolation der `mode`-Weiterleitung
an beide Repository-Methoden) sowie (Story S-071, AC14) die
Titel-Anlageklasse/-Gewichtung und die depotweite Kostenbasis/den
aggregierten unrealisierten G/V. Die HTTP-/Router-Ebene (coder/R06) deckt
`tests/api/test_depot.py`."""

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
    symbol: str | None = None,
    name: str | None = None,
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
        symbol=symbol,
        name=name,
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
    assert ergebnis.portfolio_wert_kostenbasis == Decimal("0")
    assert ergebnis.unrealisierter_gv_gesamt == Decimal("0")
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
    # Mindestens ein Titel nicht bewertbar -> depotweites Total "nicht
    # bewertbar" statt eines irreführenden Teil-Totals (AC14).
    assert ergebnis.unrealisierter_gv_gesamt is None


def test_unrealisierter_gv_mit_live_kurs():
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({"titel-1": Decimal("120")})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    eintrag = ergebnis.titel[0]
    assert eintrag.aktueller_preis == Decimal("120")
    # (120 - 100) * 10 = 200
    assert eintrag.unrealisierter_gv == Decimal("200")
    assert ergebnis.unrealisierter_gv_gesamt == Decimal("200")


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
    # Einziger Titel im Depot -> 100% Gewichtung (AC14).
    assert eintrag.gewichtung == Decimal("100.000")
    assert eintrag.anlageklasse == 1


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
    # AC14: Titel-Gewichtung/-Anlageklasse + depotweite Kostenbasis folgen
    # derselben Bewertungsgrundlage.
    assert ergebnis.portfolio_wert_kostenbasis == Decimal("2000")
    by_titel = {eintrag.titel_id: eintrag for eintrag in ergebnis.titel}
    assert by_titel["titel-1"].gewichtung == Decimal("50.000")
    assert by_titel["titel-1"].anlageklasse == 1
    assert by_titel["titel-2"].gewichtung == Decimal("50.000")
    assert by_titel["titel-2"].anlageklasse == 3


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


def test_anlageklasse_stammt_vom_aeltesten_lot():
    """AC14: bei mehreren Lots desselben Titels repräsentiert das
    **erste** (laut Repository-Vertrag älteste, `opened_at` aufsteigend)
    Lot die Anlageklasse — analog `ermittle_titel_strategie_exit_regeln`."""
    positionen = [
        _position(
            "titel-1",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
            asset_class_id=1,
            position_id="lot-alt",
        ),
        _position(
            "titel-1",
            menge=Decimal("5"),
            einstand_preis=Decimal("100"),
            asset_class_id=2,
            position_id="lot-neu",
        ),
    ]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    assert ergebnis.titel[0].anlageklasse == 1


def test_unrealisierter_gv_gesamt_ist_null_bei_leerem_depot():
    repository = _FakePositionRepository(positionen=[])
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    assert ergebnis.unrealisierter_gv_gesamt == Decimal("0")


def test_symbol_und_name_stammen_vom_aeltesten_lot():
    """Review-Finding Iteration 1: `symbol`/`name` werden vom ältesten Lot
    durchgereicht (analog `anlageklasse`) — lesbarer Titel-Bezeichner statt
    der rohen `titel_id`-UUID in der Depot-Tabelle."""
    positionen = [
        _position(
            "titel-1",
            menge=Decimal("10"),
            einstand_preis=Decimal("100"),
            symbol="ALT",
            name="Alt AG",
            position_id="lot-alt",
        ),
        _position(
            "titel-1",
            menge=Decimal("5"),
            einstand_preis=Decimal("100"),
            symbol="NEU",
            name="Neu AG",
            position_id="lot-neu",
        ),
    ]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    assert ergebnis.titel[0].symbol == "ALT"
    assert ergebnis.titel[0].name == "Alt AG"


def test_symbol_und_name_sind_none_ohne_repository_daten():
    """Fallback-Fall: liefert das Repository (Test-Fake) kein `symbol`/
    `name`, bleibt das Feld `None` — das Template fällt dann auf
    `titel_id` zurück (kein Query-seitiger Zwang zu einem Wert)."""
    positionen = [_position("titel-1", menge=Decimal("10"), einstand_preis=Decimal("100"))]
    repository = _FakePositionRepository(positionen=positionen)
    live_price = _FakeLivePriceProvider({})

    ergebnis = hole_depot_uebersicht(mode="echt", repository=repository, live_price=live_price)

    assert ergebnis.titel[0].symbol is None
    assert ergebnis.titel[0].name is None
