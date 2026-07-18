"""Tests für die Positions-Fortschreibung (Story S-016 + DBA-Zweit-Review
+ S-053).

Covers (depot): AC2, AC3, AC5, AC4, AC7, AC6

`app.domain.portfolio.position_booking` verbucht einen bereits über
`pruefe_fill` (S-015) als "gebucht" geprüften Fill gegen den Positions-
Bestand. Diese Tests decken:
- AC2 (unrealisierter/realisierter G/V je Position + aggregiert, reine
  Formel-Bausteine `berechne_unrealisierten_gv`/`berechne_realisierten_gv`/
  `aggregiere_gv`),
- AC3 (Gebühren-Netting: erhöhen die Kostenbasis beim Kauf, mindern den
  Erlös beim Verkauf — in beiden Richtungen über die G/V-Formeln geprüft;
  DBA-Zweit-Review: Restbetrag-Buchführung bei FIFO-Multi-Lot-Verkäufen
  summiert exakt auf `fill.kosten`, keine Rundungsdrift),
- AC5 (Einstand-Methode konfigurierbar: gleitender Durchschnitt lässt den
  Ø-Einstandspreis der Restposition nach Teilverkauf unverändert, A1; FIFO
  entnimmt beim Teilverkauf die ältesten Anteile zuerst, A2, und kann dabei
  die Restposition über mehrere unterschiedlich bepreiste Lots verteilen;
  DBA-Zweit-Review: ein Verkauf über den verfügbaren Bestand hinaus wird
  verweigert statt den nicht deckbaren Rest still fallen zu lassen).

DBA-Zweit-Review (Iteration 2, Critical + Important) ergänzt ausserdem
einen Idempotenz-Test (ADR-011/P8: derselbe `client_order_id`-Fill wird
kein zweites Mal verbucht).

Ein `_FakeRepository` (in-memory, kein SQLAlchemy) implementiert
`PositionRepository` strukturell — deterministisch testbar ohne DB
(Estimate-Vorgabe "Teilverkauf-Logik für beide Methoden deterministisch
testbar"). Jeder `_kauf()`/`_verkauf()`-Aufruf erhält standardmässig eine
fortlaufend eindeutige `client_order_id` (`_next_client_order_id()`) —
sonst würde der Fake-Dedup-Check mehrere gewollt unterschiedliche Fills
innerhalb desselben Tests fälschlich als Duplikate behandeln.

DBA-Re-Review (Iteration 3, Important — Mode-Isolation, BR-113/BR-130)
ergänzt: `_Lot` trägt jetzt `mode`, `_FakeRepository.aktuelle_menge`/
`offene_positionen` filtern zusätzlich darauf, und zwei neue Tests
(`test_verbuche_kauf_mittelt_nicht_in_lot_des_anderen_modus`,
`test_verbuche_verkauf_verbraucht_nicht_lot_des_anderen_modus`) decken
ab, dass ein "echt"-Fill niemals gegen einen "simuliert"-Lot desselben
Titels gemittelt oder verbraucht wird (und umgekehrt).

S-035 (AC4/AC7) ergänzt `_FakeRepository.schreibe_transaktion`/
`historie_je_titel` (in-memory Liste statt DB) und Tests, die belegen,
dass `verbuche_fill` NACH jeder erfolgreichen Buchung (Kauf/Verkauf) genau
einen Transaktionshistorie-Eintrag schreibt — aber NICHT bei
`bereits_verbucht=True` (Dedup-Kurzschluss, ADR-011).

S-053 (AC6, FX-Attribution) ergänzt `_Lot.einstand_fx_rate` +
`_FakeRepository.lege_position_an`/`aktualisiere_kauf`/`schreibe_transaktion`
(nehmen/reichen den FX-Kurs bzw. den aggregierten FX-Split durch) sowie
Tests, die belegen: (a) ein Fremdwährungs-Erstkauf setzt den Lot-FX-Kurs,
(b) ein Nachkauf mittelt ihn mengen-gewichtet, (c) FIFO legt ihn je Lot
unabhängig fest, (d) ein Fremdwährungs-Verkauf berechnet
`fx_split_gesamt` (aggregiert über alle verbrauchten Lots) und übergibt
ihn an `schreibe_transaktion`, (e) ein CHF-Fill bleibt ohne jede
FX-Attribution (`None`).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.contracts.depot import ExitRegeln, FillInput
from app.domain.portfolio.fx_attribution import FxSplit
from app.domain.portfolio.ports import OffenePosition, TransaktionsEintrag
from app.domain.portfolio.position_booking import (
    UnzureichenderBestandFehler,
    aggregiere_gv,
    berechne_erloes_bei_verkauf,
    berechne_neuen_einstand_bei_kauf,
    berechne_realisierten_gv,
    berechne_unrealisierten_gv,
    verbuche_fill,
)
from app.domain.portfolio.transaction_historie import berechne_slippage

_TITEL_ID = "11111111-1111-1111-1111-111111111111"
_ZEITSTEMPEL = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
_CLIENT_ORDER_ID_COUNTER = itertools.count(1)


def _next_client_order_id() -> str:
    return f"order-{next(_CLIENT_ORDER_ID_COUNTER)}"


@dataclass
class _Lot:
    menge: Decimal
    einstand_preis: Decimal
    einstand_methode: str
    opened_at: datetime
    mode: str = "simuliert"
    status: str = "offen"
    realisierter_gv: Decimal = Decimal("0")
    einstand_fx_rate: Decimal | None = None


@dataclass
class _FakeRepository:
    """Test-Double für `PositionRepository` (S-016) — hält Lots rein
    in-memory, um die Buchungslogik ohne SQLAlchemy deterministisch zu
    prüfen."""

    lots: dict[str, _Lot] = field(default_factory=dict)
    verbuchte_client_order_ids: set[str] = field(default_factory=set)
    transaktionen: list[tuple[FillInput, str | None]] = field(default_factory=list)
    fx_splits: list[FxSplit | None] = field(default_factory=list)
    _naechste_id: int = 0
    _naechster_zeitpunkt: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=UTC))

    def aktuelle_menge(self, titel_id: str, *, mode: str) -> Decimal:
        return sum(
            (lot.menge for lot in self.lots.values() if lot.status == "offen" and lot.mode == mode),
            Decimal("0"),
        )

    def offene_positionen(self, titel_id: str, *, mode: str) -> list[OffenePosition]:
        eintraege = [
            OffenePosition(
                position_id=pid,
                menge=lot.menge,
                einstand_preis=lot.einstand_preis,
                einstand_methode=lot.einstand_methode,
                opened_at=lot.opened_at,
                einstand_fx_rate=lot.einstand_fx_rate,
            )
            for pid, lot in self.lots.items()
            if lot.status == "offen" and lot.mode == mode
        ]
        return sorted(eintraege, key=lambda e: e.opened_at)

    def lege_position_an(
        self,
        fill: FillInput,
        *,
        einstand_preis: Decimal,
        einstand_methode: str,
        einstand_fx_rate: Decimal | None = None,
    ) -> str:
        self._naechste_id += 1
        pid = f"lot-{self._naechste_id}"
        opened_at = self._naechster_zeitpunkt
        self._naechster_zeitpunkt += timedelta(days=1)
        self.lots[pid] = _Lot(
            menge=fill.menge,
            einstand_preis=einstand_preis,
            einstand_methode=einstand_methode,
            opened_at=opened_at,
            mode=fill.mode,
            einstand_fx_rate=einstand_fx_rate,
        )
        return pid

    def aktualisiere_kauf(
        self,
        position_id: str,
        *,
        neue_menge: Decimal,
        neuer_einstand_preis: Decimal,
        einstand_fx_rate: Decimal | None = None,
    ) -> None:
        lot = self.lots[position_id]
        lot.menge = neue_menge
        lot.einstand_preis = neuer_einstand_preis
        lot.einstand_fx_rate = einstand_fx_rate

    def verbuche_verkauf_lot(
        self, position_id: str, *, neue_menge: Decimal, realisierter_gv_delta: Decimal
    ) -> None:
        lot = self.lots[position_id]
        lot.menge = neue_menge
        lot.realisierter_gv += realisierter_gv_delta
        if neue_menge == 0:
            lot.status = "geschlossen"

    def markiere_fill_verbucht(self, client_order_id: str, *, titel_id: str, richtung: str) -> bool:
        if client_order_id in self.verbuchte_client_order_ids:
            return False
        self.verbuchte_client_order_ids.add(client_order_id)
        return True

    def schreibe_transaktion(
        self, fill: FillInput, *, position_id: str | None, fx_split: FxSplit | None = None
    ) -> None:
        self.transaktionen.append((fill, position_id))
        self.fx_splits.append(fx_split)

    def historie_je_titel(self, titel_id: str, *, mode: str) -> list[TransaktionsEintrag]:
        return [
            TransaktionsEintrag(
                trade_id=str(index),
                titel_id=fill.titel_id,
                richtung=fill.richtung,
                menge=fill.menge,
                fill_preis=fill.fill_preis,
                arrival_price=fill.arrival_price,
                slippage=berechne_slippage(fill.fill_preis, fill.arrival_price),
                kosten=fill.kosten,
                waehrung=fill.waehrung,
                zeitstempel=fill.zeitstempel,
            )
            for index, (fill, _position_id) in enumerate(self.transaktionen)
            if fill.titel_id == titel_id and fill.mode == mode
        ]


def _kauf(**overrides: object) -> FillInput:
    kwargs = {
        "client_order_id": _next_client_order_id(),
        "titel_id": _TITEL_ID,
        "anlageklasse": 1,
        "gics_branche": "Technology",
        "richtung": "kauf",
        "menge": Decimal("10"),
        "fill_preis": Decimal("100"),
        "kosten": Decimal("10"),
        "arrival_price": Decimal("100"),
        "waehrung": "CHF",
        "zeitstempel": _ZEITSTEMPEL,
        "mode": "simuliert",
        "strategie": "Index",
        "zeithorizont": 8,
        "exit_regeln": ExitRegeln(
            stop_typ="atr_trailing", stop_parameter=2.5, thesis_invalidierung="Wachstum < 5%."
        ),
        "these": "Langfristiger Index-Halter.",
    }
    kwargs.update(overrides)
    return FillInput(**kwargs)


def _verkauf(**overrides: object) -> FillInput:
    kwargs = {
        "client_order_id": _next_client_order_id(),
        "titel_id": _TITEL_ID,
        "anlageklasse": 1,
        "gics_branche": "Technology",
        "richtung": "verkauf",
        "menge": Decimal("5"),
        "fill_preis": Decimal("120"),
        "kosten": Decimal("5"),
        "arrival_price": Decimal("119"),
        "waehrung": "CHF",
        "zeitstempel": _ZEITSTEMPEL,
        "mode": "simuliert",
    }
    kwargs.update(overrides)
    return FillInput(**kwargs)


# --- AC2: reine G/V-Formeln (je Position + aggregiert) -----------------


def test_berechne_unrealisierten_gv() -> None:
    """@trace depot#AC2 — unrealisierter G/V = (aktueller Preis −
    Ø-Einstandspreis) × gehaltene Menge."""
    ergebnis = berechne_unrealisierten_gv(Decimal("120"), Decimal("100"), Decimal("10"))
    assert ergebnis == Decimal("200")


def test_berechne_unrealisierten_gv_negativ_bei_kursverlust() -> None:
    """@trace depot#AC2 — ein aktueller Preis unter dem Einstand ergibt
    einen negativen unrealisierten G/V (Verlust), keine Untergrenze."""
    ergebnis = berechne_unrealisierten_gv(Decimal("90"), Decimal("100"), Decimal("10"))
    assert ergebnis == Decimal("-100")


def test_berechne_realisierten_gv() -> None:
    """@trace depot#AC2 — realisierter G/V = Erlös (netto) −
    Ø-Einstandspreis × verkaufte Menge."""
    erloes_netto = Decimal("595")  # 5 * 120 - 5 Kosten
    ergebnis = berechne_realisierten_gv(erloes_netto, Decimal("100"), Decimal("5"))
    assert ergebnis == Decimal("95")


def test_aggregiere_gv_summiert_je_position_ermittelte_werte() -> None:
    """@trace depot#AC2 — mehrere je Position ermittelte G/V-Werte sind
    aggregiert (Summe) abrufbar."""
    werte = [Decimal("200"), Decimal("-50"), Decimal("10")]
    assert aggregiere_gv(werte) == Decimal("160")


# --- AC3: Gebühren-Netting -----------------------------------------------


def test_berechne_neuen_einstand_bei_kauf_nettet_kosten_beim_erstkauf() -> None:
    """@trace depot#AC3 — die Kosten des allerersten Kaufs erhöhen die
    Kostenbasis (Ø-Einstandspreis > reiner Fill-Preis)."""
    einstand = berechne_neuen_einstand_bei_kauf(
        bisherige_menge=Decimal("0"),
        bisheriger_einstand_preis=Decimal("0"),
        kauf_menge=Decimal("10"),
        kauf_preis=Decimal("100"),
        kosten=Decimal("10"),
    )
    # (10*100 + 10) / 10 = 101
    assert einstand == Decimal("101")


def test_berechne_neuen_einstand_bei_kauf_gewichteter_durchschnitt_bei_nachkauf() -> None:
    """@trace depot#AC3,AC5 — ein Nachkauf mittelt die (bereits
    gebühren-genettete) neue Kostenbasis mit der bisherigen."""
    einstand = berechne_neuen_einstand_bei_kauf(
        bisherige_menge=Decimal("10"),
        bisheriger_einstand_preis=Decimal("100"),
        kauf_menge=Decimal("10"),
        kauf_preis=Decimal("120"),
        kosten=Decimal("10"),
    )
    # (10*100 + 10*120 + 10) / 20 = 110.5
    assert einstand == Decimal("110.5")


def test_berechne_erloes_bei_verkauf_nettet_kosten_vom_bruttoerloes() -> None:
    """@trace depot#AC3 — die Kosten mindern den Erlös eines Verkaufs."""
    erloes = berechne_erloes_bei_verkauf(Decimal("5"), Decimal("120"), Decimal("5"))
    assert erloes == Decimal("595")


def test_realisierter_gv_ueber_verbuche_fill_enthaelt_kauf_und_verkaufskosten() -> None:
    """@trace depot#AC3 — der über `verbuche_fill` ermittelte realisierte
    G/V enthält die Kosten aus BEIDEN Seiten (Kauf erhöht Kostenbasis,
    Verkauf mindert Erlös), nicht nur den reinen Kursspread."""
    repository = _FakeRepository()
    verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    ergebnis = verbuche_fill(
        _verkauf(menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("20")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    # Einstand 101 (Kauf-Kosten genettet); Erlös 10*120 - 20 = 1180;
    # G/V = 1180 - 10*101 = 170 (ohne Netting waere es 190).
    assert ergebnis.realisierter_gv_gesamt == Decimal("170")


# --- AC5: Einstand-Methode (gleitender Durchschnitt Default, FIFO optional) --


def test_gleitender_durchschnitt_ist_default_und_bleibt_bei_teilverkauf_unveraendert() -> None:
    """@trace depot#AC5 — A1: bei gleitendem Durchschnitt bleibt der
    Ø-Einstandspreis der Restposition nach einem Teilverkauf unverändert;
    nur Menge sinkt und realisierter G/V wächst."""
    repository = _FakeRepository()
    kauf_ergebnis = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    lot = repository.lots[kauf_ergebnis.position_id]
    assert lot.einstand_methode == "gleitender_durchschnitt"
    einstand_vor_verkauf = lot.einstand_preis

    verbuche_fill(
        _verkauf(menge=Decimal("4"), fill_preis=Decimal("150"), kosten=Decimal("4")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )

    assert lot.einstand_preis == einstand_vor_verkauf
    assert lot.menge == Decimal("6")
    assert lot.realisierter_gv != Decimal("0")


def test_gleitender_durchschnitt_nachkauf_mittelt_in_denselben_lot() -> None:
    """@trace depot#AC5 — ein Nachkauf desselben Titels bei gleitendem
    Durchschnitt erzeugt KEINEN zweiten Lot, sondern mittelt in den
    bestehenden hinein (genau ein offener Lot bleibt)."""
    repository = _FakeRepository()
    erster = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    zweiter = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )

    assert zweiter.position_id == erster.position_id
    offene = [lot for lot in repository.lots.values() if lot.status == "offen"]
    assert len(offene) == 1
    assert offene[0].menge == Decimal("20")


def test_fifo_legt_je_kauf_einen_neuen_lot_an() -> None:
    """@trace depot#AC5 — bei FIFO erzeugt jeder Kauf einen eigenen Lot
    (keine Mittelung über bestehende Lots hinweg)."""
    repository = _FakeRepository()
    erster = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )
    zweiter = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )

    assert erster.position_id != zweiter.position_id
    offene = [lot for lot in repository.lots.values() if lot.status == "offen"]
    assert len(offene) == 2


def test_fifo_verkauf_entnimmt_aeltesten_lot_zuerst() -> None:
    """@trace depot#AC5 — A2: bei FIFO wird beim Teilverkauf zuerst der
    älteste Lot (niedrigster `opened_at`) verbraucht."""
    repository = _FakeRepository()
    aelterer = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )
    juengerer = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )

    verbuche_fill(
        _verkauf(menge=Decimal("6"), fill_preis=Decimal("150"), kosten=Decimal("6")),
        repository=repository,
        einstand_methode_default="fifo",
    )

    assert repository.lots[aelterer.position_id].menge == Decimal("4")
    assert repository.lots[aelterer.position_id].status == "offen"
    assert repository.lots[juengerer.position_id].menge == Decimal("10")
    assert repository.lots[juengerer.position_id].status == "offen"


def test_fifo_verkauf_ueber_einen_lot_hinaus_verteilt_sich_auf_mehrere_lots() -> None:
    """@trace depot#AC5 — A2: übersteigt der Verkauf die Menge des
    ältesten Lots, wird der Rest aus dem nächstälteren Lot entnommen; der
    ältere Lot wird dabei vollständig geschlossen (Restposition besteht nun
    nur noch aus dem jüngeren, ANDERS bepreisten Lot — der Ø-Einstandspreis
    der Restposition ändert sich dadurch effektiv, anders als beim
    gleitenden Durchschnitt)."""
    repository = _FakeRepository()
    aelterer = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )
    juengerer = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )

    ergebnis = verbuche_fill(
        _verkauf(menge=Decimal("15"), fill_preis=Decimal("150"), kosten=Decimal("15")),
        repository=repository,
        einstand_methode_default="fifo",
    )

    assert repository.lots[aelterer.position_id].menge == Decimal("0")
    assert repository.lots[aelterer.position_id].status == "geschlossen"
    assert repository.lots[juengerer.position_id].menge == Decimal("5")
    assert repository.lots[juengerer.position_id].status == "offen"
    assert repository.lots[juengerer.position_id].einstand_preis == Decimal("121")

    assert len(ergebnis.lot_buchungen) == 2
    assert ergebnis.lot_buchungen[0].position_id == aelterer.position_id
    assert ergebnis.lot_buchungen[0].verbrauchte_menge == Decimal("10")
    assert ergebnis.lot_buchungen[1].position_id == juengerer.position_id
    assert ergebnis.lot_buchungen[1].verbrauchte_menge == Decimal("5")
    assert ergebnis.realisierter_gv_gesamt == aggregiere_gv(
        b.realisierter_gv for b in ergebnis.lot_buchungen
    )


# --- DBA-Zweit-Review (Iteration 2): Idempotenz, Lost-Update-Guard, ------
# --- Rundungsdrift --------------------------------------------------------


def test_verbuche_fill_mit_bereits_verbuchter_client_order_id_ist_no_op() -> None:
    """@trace depot#AC2,AC3 — ADR-011/P8 (DBA-Zweit-Review S-016, Critical):
    ein Fill mit einer bereits verbuchten `client_order_id` (At-least-once-
    Zustellung dupliziert den Fill) wird KEIN zweites Mal gegen den Bestand
    fortgeschrieben — Menge/Einstand bleiben unverändert, das Ergebnis
    meldet `bereits_verbucht=True`."""
    repository = _FakeRepository()
    fill = _kauf(
        client_order_id="order-idempotenz-1",
        menge=Decimal("10"),
        fill_preis=Decimal("100"),
        kosten=Decimal("10"),
    )

    erstes_ergebnis = verbuche_fill(
        fill, repository=repository, einstand_methode_default="gleitender_durchschnitt"
    )
    lot = repository.lots[erstes_ergebnis.position_id]
    menge_nach_erstem = lot.menge
    einstand_nach_erstem = lot.einstand_preis

    zweites_ergebnis = verbuche_fill(
        fill, repository=repository, einstand_methode_default="gleitender_durchschnitt"
    )

    assert erstes_ergebnis.bereits_verbucht is False
    assert zweites_ergebnis.bereits_verbucht is True
    assert zweites_ergebnis.position_id is None
    assert lot.menge == menge_nach_erstem
    assert lot.einstand_preis == einstand_nach_erstem
    assert len([lot for lot in repository.lots.values() if lot.status == "offen"]) == 1


def test_verbuche_verkauf_ueber_gesamten_bestand_hinaus_wird_verweigert() -> None:
    """@trace depot#AC5 — DBA-Zweit-Review S-016 (Important, Lost-Update/
    TOCTOU-Guard): übersteigt die Verkaufsmenge die Summe der verfügbaren
    Lot-Mengen (z. B. weil zwischen Gate und Buchung Bestand entzogen
    wurde), wird NICHT gebucht (`UnzureichenderBestandFehler`) — der
    Bestand bleibt unverändert, statt den nicht deckbaren Rest still
    fallen zu lassen (AC10)."""
    repository = _FakeRepository()
    kauf_ergebnis = verbuche_fill(
        _kauf(menge=Decimal("5"), fill_preis=Decimal("100"), kosten=Decimal("5")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    lot = repository.lots[kauf_ergebnis.position_id]
    menge_vor_verkauf = lot.menge
    einstand_vor_verkauf = lot.einstand_preis

    with pytest.raises(UnzureichenderBestandFehler):
        verbuche_fill(
            _verkauf(menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("10")),
            repository=repository,
            einstand_methode_default="gleitender_durchschnitt",
        )

    assert lot.menge == menge_vor_verkauf
    assert lot.einstand_preis == einstand_vor_verkauf
    assert lot.status == "offen"


def test_fifo_verkauf_ueber_mehrere_lots_verteilt_kosten_exakt_ohne_rundungsdrift() -> None:
    """@trace depot#AC3 — DBA-Zweit-Review S-016 (Important): bei einer
    nicht glatt teilbaren Verkaufsmenge über mehrere (drei) Lots summiert
    die verteilte Kostenverteilung exakt auf `fill.kosten` — reine
    Anteilsrechnung (`verbrauch / fill.menge`, z. B. 3/7) driftet bei
    solchen „krummen" Stückzahlen; die Restbetrag-Buchführung (der zuletzt
    verbrauchte Lot erhält den Rest) nicht."""
    repository = _FakeRepository()
    verbuche_fill(
        _kauf(menge=Decimal("3"), fill_preis=Decimal("100"), kosten=Decimal("3")),
        repository=repository,
        einstand_methode_default="fifo",
    )
    verbuche_fill(
        _kauf(menge=Decimal("3"), fill_preis=Decimal("110"), kosten=Decimal("3")),
        repository=repository,
        einstand_methode_default="fifo",
    )
    verbuche_fill(
        _kauf(menge=Decimal("4"), fill_preis=Decimal("120"), kosten=Decimal("4")),
        repository=repository,
        einstand_methode_default="fifo",
    )

    verkauf_fill = _verkauf(menge=Decimal("7"), fill_preis=Decimal("150"), kosten=Decimal("10"))
    ergebnis = verbuche_fill(verkauf_fill, repository=repository, einstand_methode_default="fifo")

    # 3 (ältester Lot voll) + 3 (mittlerer Lot voll) + 1 (jüngster Lot
    # angebrochen) = 7 — drei Lot-Buchungen, keine davon glatt 1/3.
    assert len(ergebnis.lot_buchungen) == 3
    assert [b.verbrauchte_menge for b in ergebnis.lot_buchungen] == [
        Decimal("3"),
        Decimal("3"),
        Decimal("1"),
    ]

    kosten_summe = Decimal("0")
    for buchung in ergebnis.lot_buchungen:
        einstand = repository.lots[buchung.position_id].einstand_preis
        erloes_anteil = buchung.realisierter_gv + einstand * buchung.verbrauchte_menge
        kosten_anteil = buchung.verbrauchte_menge * verkauf_fill.fill_preis - erloes_anteil
        kosten_summe += kosten_anteil

    assert kosten_summe == verkauf_fill.kosten


# --- DBA-Re-Review (Iteration 3): Mode-Isolation (BR-113/BR-130) ---------


def test_verbuche_kauf_mittelt_nicht_in_lot_des_anderen_modus() -> None:
    """@trace depot#AC5 — DBA-Re-Review S-016 (Iteration 3, Important,
    BR-113/BR-130): ein Titel mit einem bereits offenen "simuliert"-Lot
    (gleitender Durchschnitt) darf durch einen "echt"-Kauf-Fill NICHT in
    diesen Lot gemittelt werden — der "echt"-Fill legt stattdessen einen
    eigenen, neuen ("echt"-)Lot an; der "simuliert"-Lot bleibt exakt
    unverändert."""
    repository = _FakeRepository()
    simuliert_ergebnis = verbuche_fill(
        _kauf(
            mode="simuliert", menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    simuliert_lot = repository.lots[simuliert_ergebnis.position_id]
    menge_vor_echt_kauf = simuliert_lot.menge
    einstand_vor_echt_kauf = simuliert_lot.einstand_preis

    echt_ergebnis = verbuche_fill(
        _kauf(mode="echt", menge=Decimal("5"), fill_preis=Decimal("200"), kosten=Decimal("5")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )

    assert echt_ergebnis.position_id != simuliert_ergebnis.position_id
    assert simuliert_lot.menge == menge_vor_echt_kauf
    assert simuliert_lot.einstand_preis == einstand_vor_echt_kauf

    echt_lot = repository.lots[echt_ergebnis.position_id]
    assert echt_lot.mode == "echt"
    assert echt_lot.menge == Decimal("5")
    # (5*200 + 5) / 5 = 201 — genettet aus dem "echt"-Fill allein, keine
    # Mittelung mit dem "simuliert"-Lot (der wäre 101 gewesen).
    assert echt_lot.einstand_preis == Decimal("201")

    offene_lots_je_modus = {lot.mode for lot in repository.lots.values() if lot.status == "offen"}
    assert offene_lots_je_modus == {"echt", "simuliert"}


def test_verbuche_verkauf_verbraucht_nicht_lot_des_anderen_modus() -> None:
    """@trace depot#AC5 — DBA-Re-Review S-016 (Iteration 3, Important,
    BR-113/BR-130): ein "echt"-Verkauf, der die Menge des eigenen
    "echt"-Lots übersteigt, wird verweigert (`UnzureichenderBestandFehler`)
    — obwohl ein grösserer "simuliert"-Lot desselben Titels existiert. Der
    "simuliert"-Lot darf den "echt"-Verkauf NIEMALS decken."""
    repository = _FakeRepository()
    verbuche_fill(
        _kauf(
            mode="simuliert", menge=Decimal("100"), fill_preis=Decimal("100"), kosten=Decimal("10")
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    echt_kauf_ergebnis = verbuche_fill(
        _kauf(mode="echt", menge=Decimal("5"), fill_preis=Decimal("100"), kosten=Decimal("5")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    echt_lot = repository.lots[echt_kauf_ergebnis.position_id]
    menge_vor_verkauf = echt_lot.menge

    with pytest.raises(UnzureichenderBestandFehler):
        verbuche_fill(
            _verkauf(
                mode="echt", menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("10")
            ),
            repository=repository,
            einstand_methode_default="gleitender_durchschnitt",
        )

    assert echt_lot.menge == menge_vor_verkauf
    assert echt_lot.status == "offen"


# --- S-035: append-only Transaktionshistorie & TCA (AC4/AC7) --------------


def test_verbuche_fill_schreibt_transaktionshistorie_eintrag_bei_kauf() -> None:
    """@trace depot#AC4 — ein erfolgreich verbuchter Kauf-Fill schreibt
    genau EINEN unveränderlichen Eintrag in die Transaktionshistorie, mit
    der neu angelegten `position_id`."""
    repository = _FakeRepository()
    fill = _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10"))
    ergebnis = verbuche_fill(
        fill, repository=repository, einstand_methode_default="gleitender_durchschnitt"
    )

    assert len(repository.transaktionen) == 1
    gebuchter_fill, position_id = repository.transaktionen[0]
    assert gebuchter_fill is fill
    assert position_id == ergebnis.position_id


def test_verbuche_fill_schreibt_transaktionshistorie_eintrag_bei_einzelnem_lot_verkauf() -> None:
    """@trace depot#AC4 — ein Verkauf, der genau EINEN Lot verbraucht
    (gleitender Durchschnitt: immer der Fall), schreibt den Eintrag mit
    der `position_id` dieses Lots."""
    repository = _FakeRepository()
    kauf_ergebnis = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    verbuche_fill(
        _verkauf(menge=Decimal("4"), fill_preis=Decimal("150"), kosten=Decimal("4")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )

    assert len(repository.transaktionen) == 2
    _verkauf_fill, position_id = repository.transaktionen[1]
    assert position_id == kauf_ergebnis.position_id


def test_verbuche_fill_schreibt_position_id_none_bei_fifo_multi_lot_verkauf() -> None:
    """@trace depot#AC4 — ein FIFO-Verkauf, der mehrere Lots verbraucht
    (A2), ist keinem einzelnen Lot eindeutig zuordenbar — der
    Transaktionshistorie-Eintrag trägt `position_id=None`."""
    repository = _FakeRepository()
    verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )
    verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("120"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="fifo",
    )
    ergebnis = verbuche_fill(
        _verkauf(menge=Decimal("15"), fill_preis=Decimal("150"), kosten=Decimal("15")),
        repository=repository,
        einstand_methode_default="fifo",
    )

    assert len(ergebnis.lot_buchungen) == 2
    _verkauf_fill, position_id = repository.transaktionen[-1]
    assert position_id is None


def test_verbuche_fill_schreibt_keine_transaktion_bei_bereits_verbuchtem_fill() -> None:
    """@trace depot#AC4 — ADR-011/P8: ein Fill mit bereits bekannter
    `client_order_id` (At-least-once-Zustellung) wird NICHT ein zweites
    Mal in die Transaktionshistorie geschrieben."""
    repository = _FakeRepository()
    fill = _kauf(
        client_order_id="order-transaktion-dedup-1",
        menge=Decimal("10"),
        fill_preis=Decimal("100"),
        kosten=Decimal("10"),
    )
    verbuche_fill(fill, repository=repository, einstand_methode_default="gleitender_durchschnitt")
    verbuche_fill(fill, repository=repository, einstand_methode_default="gleitender_durchschnitt")

    assert len(repository.transaktionen) == 1


def test_verbuche_fill_historie_eintrag_traegt_arrival_price_und_slippage() -> None:
    """@trace depot#AC7 — der über `historie_je_titel` abrufbare Eintrag
    trägt Arrival-Price, Fill-Preis und die daraus berechnete realisierte
    Slippage je Trade."""
    repository = _FakeRepository()
    fill = _kauf(
        menge=Decimal("10"),
        fill_preis=Decimal("101.5"),
        kosten=Decimal("10"),
        arrival_price=Decimal("100"),
    )
    verbuche_fill(fill, repository=repository, einstand_methode_default="gleitender_durchschnitt")

    historie = repository.historie_je_titel(_TITEL_ID, mode="simuliert")
    assert len(historie) == 1
    assert historie[0].arrival_price == Decimal("100")
    assert historie[0].fill_preis == Decimal("101.5")
    assert historie[0].slippage == Decimal("1.5")


# --- S-053: FX-Attribution (AC6, deckt A3) --------------------------------


def test_verbuche_kauf_chf_fill_lot_bleibt_ohne_fx_kurs() -> None:
    """@trace depot#AC6 — ein CHF-Fill (`fx_rate=None`) legt einen Lot OHNE
    FX-Kurs an — keine Attribution nötig (BR-129)."""
    repository = _FakeRepository()
    ergebnis = verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    assert repository.lots[ergebnis.position_id].einstand_fx_rate is None


def test_verbuche_kauf_fremdwaehrung_erstkauf_setzt_lot_fx_kurs() -> None:
    """@trace depot#AC6 — ein Fremdwährungs-Erstkauf setzt den FX-Kurs des
    Fills unverändert als Ø-Einstands-FX-Kurs des neuen Lots."""
    repository = _FakeRepository()
    ergebnis = verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("100"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("0.90"),
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    assert repository.lots[ergebnis.position_id].einstand_fx_rate == Decimal("0.90")


def test_verbuche_kauf_fremdwaehrung_nachkauf_mittelt_lot_fx_kurs_gewichtet() -> None:
    """@trace depot#AC6 — ein Nachkauf (gleitender Durchschnitt) mittelt
    den Ø-Einstands-FX-Kurs mengen-gewichtet mit dem bisherigen Lot-Kurs."""
    repository = _FakeRepository()
    erster = verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("100"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("0.90"),
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("120"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("1.00"),
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    # (10*0.90 + 10*1.00) / 20 = 0.95
    assert repository.lots[erster.position_id].einstand_fx_rate == Decimal("0.95")


def test_verbuche_kauf_fremdwaehrung_nachkauf_rundet_einstand_fx_rate_an_schreibgrenze() -> None:
    """@trace depot#AC6 — Reviewer-Befund (Iteration 2, Important): der
    gemittelte Ø-Einstands-FX-Kurs wird VOR der Übergabe an
    `repository.aktualisiere_kauf` auf 8 Nachkommastellen gerundet
    (NUMERIC(20,8), P7/ADR-010) — analog zu `neuer_einstand`. Eine
    Mittelung mit einem nicht glatt teilbaren Mengenverhältnis (1:2, /3)
    ergibt ungerundet mehr als 8 Nachkommastellen (0.9666666666...)."""
    repository = _FakeRepository()
    erster = verbuche_fill(
        _kauf(
            menge=Decimal("1"),
            fill_preis=Decimal("100"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("0.9"),
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    verbuche_fill(
        _kauf(
            menge=Decimal("2"),
            fill_preis=Decimal("120"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("1.0"),
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    # (1*0.9 + 2*1.0) / 3 = 0.96666666666...  → gerundet 0.96666667
    assert repository.lots[erster.position_id].einstand_fx_rate == Decimal("0.96666667")


def test_verbuche_kauf_fifo_jeder_lot_traegt_eigenen_fx_kurs() -> None:
    """@trace depot#AC6 — bei FIFO legt jeder Kauf einen eigenen Lot mit
    seinem EIGENEN FX-Kurs an, keine Mittelung über Lots hinweg."""
    repository = _FakeRepository()
    erster = verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("100"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("0.90"),
        ),
        repository=repository,
        einstand_methode_default="fifo",
    )
    zweiter = verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("120"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("1.00"),
        ),
        repository=repository,
        einstand_methode_default="fifo",
    )
    assert repository.lots[erster.position_id].einstand_fx_rate == Decimal("0.90")
    assert repository.lots[zweiter.position_id].einstand_fx_rate == Decimal("1.00")


def test_verbuche_verkauf_chf_hat_keinen_fx_split() -> None:
    """@trace depot#AC6 — ein CHF-Verkauf berechnet keinen FX-Split
    (`fx_split_gesamt=None`) — keine Attribution nötig."""
    repository = _FakeRepository()
    verbuche_fill(
        _kauf(menge=Decimal("10"), fill_preis=Decimal("100"), kosten=Decimal("10")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    ergebnis = verbuche_fill(
        _verkauf(menge=Decimal("5"), fill_preis=Decimal("120"), kosten=Decimal("5")),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    assert ergebnis.fx_split_gesamt is None
    assert repository.fx_splits[-1] is None


def test_verbuche_verkauf_fremdwaehrung_berechnet_fx_split_gesamt() -> None:
    """@trace depot#AC6 — ein Fremdwährungs-Verkauf (einzelner Lot,
    gleitender Durchschnitt) berechnet den realisierten FX-Split und
    übergibt ihn unverändert an `schreibe_transaktion`."""
    repository = _FakeRepository()
    verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("100"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("0.90"),
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )
    ergebnis = verbuche_fill(
        _verkauf(
            menge=Decimal("5"),
            fill_preis=Decimal("120"),
            kosten=Decimal("5"),
            waehrung="USD",
            fx_rate=Decimal("0.95"),
        ),
        repository=repository,
        einstand_methode_default="gleitender_durchschnitt",
    )

    assert ergebnis.fx_split_gesamt is not None
    assert ergebnis.lot_buchungen[0].fx_split == ergebnis.fx_split_gesamt
    assert repository.fx_splits[-1] == ergebnis.fx_split_gesamt

    # Ø-Einstand nach Kauf-Netting: (10*100 + 10) / 10 = 101.
    einstand_preis_genettet = (Decimal("10") * Decimal("100") + Decimal("10")) / Decimal("10")
    erloes_netto = Decimal("5") * Decimal("120") - Decimal("5")
    erwarteter_kapital_gv = (erloes_netto - einstand_preis_genettet * Decimal("5")) * Decimal(
        "0.90"
    )
    erwartete_waehrungs_gv = erloes_netto * (Decimal("0.95") - Decimal("0.90"))
    assert ergebnis.fx_split_gesamt.kapital_gv_chf == erwarteter_kapital_gv
    assert ergebnis.fx_split_gesamt.waehrungs_gv_chf == erwartete_waehrungs_gv


def test_verbuche_verkauf_fifo_multi_lot_aggregiert_fx_split_ueber_lots() -> None:
    """@trace depot#AC6 — ein FIFO-Verkauf über mehrere, unterschiedlich
    FX-datierte Lots (A2) aggregiert den FX-Split je Lot zu
    `fx_split_gesamt` (Summe, nicht nur der erste/letzte Lot-Anteil)."""
    repository = _FakeRepository()
    verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("100"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("0.90"),
        ),
        repository=repository,
        einstand_methode_default="fifo",
    )
    verbuche_fill(
        _kauf(
            menge=Decimal("10"),
            fill_preis=Decimal("120"),
            kosten=Decimal("10"),
            waehrung="USD",
            fx_rate=Decimal("1.00"),
        ),
        repository=repository,
        einstand_methode_default="fifo",
    )
    ergebnis = verbuche_fill(
        _verkauf(
            menge=Decimal("15"),
            fill_preis=Decimal("150"),
            kosten=Decimal("15"),
            waehrung="USD",
            fx_rate=Decimal("1.10"),
        ),
        repository=repository,
        einstand_methode_default="fifo",
    )

    assert len(ergebnis.lot_buchungen) == 2
    assert all(b.fx_split is not None for b in ergebnis.lot_buchungen)
    erwartete_summe_kapital = sum(
        (b.fx_split.kapital_gv_chf for b in ergebnis.lot_buchungen), Decimal("0")
    )
    erwartete_summe_waehrung = sum(
        (b.fx_split.waehrungs_gv_chf for b in ergebnis.lot_buchungen), Decimal("0")
    )
    assert ergebnis.fx_split_gesamt.kapital_gv_chf == erwartete_summe_kapital
    assert ergebnis.fx_split_gesamt.waehrungs_gv_chf == erwartete_summe_waehrung
