"""Tests für die Depot-Verlauf-Query (`app.api.queries.depot_verlauf`,
Story S-081, `docs/specs/frontend-cockpit.md` AC32/AC33).

Covers (frontend-cockpit): AC1, AC10, AC32

Deckt `hole_depot_verlauf` unmittelbar (Fake-`PortfolioSnapshotRepository`
statt echter Session, analog `tests/api/queries/test_depot_query.py`):
DTO-Abbildung, Mode-Default, Zeitraum-Filter-Durchreichung, leere Liste
(E2-Muster). Die HTTP-/Router-Ebene (coder/R06) deckt
`tests/api/test_depot_verlauf_route.py`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.api.queries.depot_verlauf import hole_depot_verlauf
from app.domain.portfolio_verlauf.ports import PortfolioSnapshotEintrag


class _FakePortfolioSnapshotRepository:
    def __init__(self, eintraege: list[PortfolioSnapshotEintrag] | None = None):
        self._eintraege = eintraege or []
        self.aufrufe: list[dict[str, object]] = []

    def verlauf(self, *, mode, von=None, bis=None):
        self.aufrufe.append({"mode": mode, "von": von, "bis": bis})
        return self._eintraege


def test_leere_historie_liefert_leere_eintraege_liste() -> None:
    """@trace frontend-cockpit#AC32 — Grundlage des definierten
    Empty-States (E2-Muster)."""
    response = hole_depot_verlauf(_FakePortfolioSnapshotRepository())

    assert response.mode == "echt"
    assert response.eintraege == []


def test_eintraege_werden_1_zu_1_als_dto_abgebildet() -> None:
    eintrag = PortfolioSnapshotEintrag(
        zeitpunkt=datetime(2026, 7, 1, 22, 0, tzinfo=UTC),
        portfolio_wert=Decimal("5000.00"),
        cash_quote=Decimal("9.500"),
    )
    response = hole_depot_verlauf(_FakePortfolioSnapshotRepository([eintrag]), mode="simuliert")

    assert response.mode == "simuliert"
    assert len(response.eintraege) == 1
    assert response.eintraege[0].zeitpunkt == eintrag.zeitpunkt
    assert response.eintraege[0].portfolio_wert == Decimal("5000.00")
    assert response.eintraege[0].cash_quote == Decimal("9.500")


def test_mode_und_zeitraum_werden_an_repository_durchgereicht() -> None:
    repository = _FakePortfolioSnapshotRepository()
    von = datetime(2026, 6, 1, tzinfo=UTC)
    bis = datetime(2026, 6, 30, tzinfo=UTC)

    hole_depot_verlauf(repository, mode="echt", von=von, bis=bis)

    assert repository.aufrufe == [{"mode": "echt", "von": von, "bis": bis}]
