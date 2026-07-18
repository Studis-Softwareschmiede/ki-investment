"""Tests für den Demo-/Seed-Modus (Story S-070, `docs/specs/
frontend-cockpit.md` AC22).

Covers (frontend-cockpit): AC22

- **Env-Gate (AC22 "env-gated über `SEED_DEMO`, default aus"):**
  `test_ist_demo_seed_aktiv_*` belegen, dass nur ein gesetzter
  Wahrheits-Wert (`"1"`/`"true"`/`"yes"`, gross-/kleinschreibungsunabhängig)
  aktiviert, jeder andere Wert (inkl. fehlender Variable) inaktiv bleibt.
- **Idempotenz (AC22):** `test_seed_demo_data_is_idempotent` führt
  `seed_demo_data()` zweimal gegen dieselbe Session aus und belegt, dass
  sich KEINE der geschriebenen Tabellen zwischen Lauf 1 und Lauf 2 in der
  Zeilenzahl ändert (kein Duplikat).
- **`mode="simuliert"` (AC22 Kern-Invariante):** `test_seed_demo_data_
  schreibt_ausschliesslich_mode_simuliert` belegt, dass jede Position/
  Transaktion/Analyse ausschliesslich `mode="simuliert"` trägt.
- **Inhalt (AC22):** `test_seed_demo_data_befuellt_alle_geforderten_
  entitaeten` belegt, dass alle in AC22 genannten Entitäten tatsächlich
  entstehen — inklusive genau eines Sanity-Cap-Falls
  (`AnalysisResult.sanity_cap_applied`) und einer Gate-Ampel
  (`GateResult.ampel`).
- **Order-Freiheit (AC22 "löst keine Order aus", §13.7-6):**
  `test_demo_modul_importiert_keinen_order_pfad` belegt per Quelltext-Scan,
  dass kein Modul unter `app/demo/**` `app.domain.sizing`/
  `app.domain.risikomanagement`/`app.domain.execution`/
  `app.orchestration.*_pipeline`/`app.orchestration.execution_service`
  importiert (analog `tests/architecture/test_order_pfad_invariante.py`).

SQLite (in-memory) reicht aus — reiner SQLAlchemy-/App-Layer-Code, keine
Postgres-spezifischen Konstrukte (Trigger/Partitionierung) im Pfad, den
diese Tests ausüben (analog `tests/db/test_bronze.py`/`tests/adapters/
repositories/test_position_repository.py`). Die reale Nebenläufigkeits-
Härtung der wiederverwendeten Store-Funktionen (`app.db.bronze`/
`app.db.silver`/`app.db.gold`) ist bereits in deren eigenen Testsuiten
abgedeckt — hier nicht erneut geprüft (kein neues Verhalten dieser Story)."""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    AnalysisCategory,
    AnalysisCategoryScore,
    AnalysisFact,
    AnalysisMethodVersion,
    AnalysisResult,
    AssetClass,
    CategoryWeightVersion,
    DataSource,
    DepotFillDedup,
    GateResult,
    Instrument,
    MarketDataBronze,
    MarketDataGold,
    MarketDataSilver,
    Position,
    RuleHypothesis,
    Strategy,
    StrategyCluster,
    TimeHorizon,
    Transaction,
    TrialRegistry,
)
from app.demo.seed import ist_demo_seed_aktiv, seed_demo_data

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_MODUL_ROOT = _REPO_ROOT / "app" / "demo"

#: Identisch zum Order-Pfad-Katalog aus `tests/architecture/
#: test_order_pfad_invariante.py` (BR-001, architecture.md §9) — AC22
#: verlangt explizit "kein Sizing-/Risiko-/Execution-Aufruf".
_VERBOTENE_PRAEFIXE: tuple[str, ...] = (
    "app.domain.sizing",
    "app.domain.risikomanagement",
    "app.domain.execution",
    "app.orchestration.execution_service",
)
_PIPELINE_SUFFIX = "_pipeline"
_PIPELINE_PARENT = "app.orchestration"


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        _seed_stammdaten(db_session)
        yield db_session


def _seed_stammdaten(session: Session) -> None:
    """Minimale Stammdaten, wie sie unter echtem Postgres bereits über die
    bestehenden Seed-Migrationen vorliegen (`b2bd709be080`, `ddaf9dcc6216`,
    `ea80c97626ee`, `386f43ae972d`, `8f183aee9753`, `2da446925bbc`) — unter
    SQLite (kein Migrations-Lauf in Unit-Tests, analog `tests/adapters/
    repositories/test_position_repository.py`) hier von Hand nachgebildet,
    nur die von `app.demo.seed` tatsächlich referenzierten Zeilen."""
    session.add_all(
        [
            AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True),
            AssetClass(id=2, name="ETFs", prio_stufe="MVP", aktiv=True, retail_driven=False),
            AssetClass(
                id=7, name="Kryptowährungen", prio_stufe="Stufe3", aktiv=True, retail_driven=True
            ),
        ]
    )
    session.add(
        StrategyCluster(code="passiv_regelbasiert", name="Passiv/Regelbasiert", freigeschaltet=True)
    )
    session.add(Strategy(id=uuid.uuid4(), name="Index", cluster="passiv_regelbasiert", stufe="MVP"))
    session.add(
        TimeHorizon(
            id=6,
            name="Mittelfristig",
            transaktionskosten_relevanz="NIEDRIG",
            break_even_anforderung="2–5 % pro Position",
        )
    )
    session.add_all(
        [
            AnalysisCategory(code="fundamental", name="Fundamental"),
            AnalysisCategory(code="technisch", name="Technisch"),
            AnalysisCategory(code="qualitativ", name="Qualitativ"),
            AnalysisCategory(code="makro", name="Makro"),
            AnalysisCategory(code="risiko_quant", name="Risiko (quantitativ)"),
        ]
    )
    session.add(
        DataSource(
            id=uuid.uuid4(),
            name="SEC Form 4 Insider-Trades",
            kategorie="equity_fundamentals",
            qualitaet="hoch",
            frequenz_sekunden=7200,
            aktiv=True,
        )
    )
    session.add(CategoryWeightVersion(id=uuid.uuid4(), is_current=True))
    session.add(AnalysisMethodVersion(id=uuid.uuid4(), is_current=True))
    session.commit()


def test_ist_demo_seed_aktiv_default_aus_ohne_variable() -> None:
    assert ist_demo_seed_aktiv({}) is False


@pytest.mark.parametrize("wert", ["0", "false", "False", "", "nein", "off"])
def test_ist_demo_seed_aktiv_falsy_werte(wert: str) -> None:
    assert ist_demo_seed_aktiv({"SEED_DEMO": wert}) is False


@pytest.mark.parametrize("wert", ["1", "true", "True", "TRUE", "yes", "Yes"])
def test_ist_demo_seed_aktiv_truthy_werte(wert: str) -> None:
    assert ist_demo_seed_aktiv({"SEED_DEMO": wert}) is True


def test_seed_demo_data_befuellt_alle_geforderten_entitaeten(session: Session) -> None:
    seed_demo_data(session)

    assert session.execute(select(func.count()).select_from(Instrument)).scalar_one() >= 3
    assert session.execute(select(func.count()).select_from(Position)).scalar_one() >= 1
    assert session.execute(select(func.count()).select_from(Transaction)).scalar_one() >= 3

    assert session.execute(select(func.count()).select_from(MarketDataBronze)).scalar_one() == 2
    assert session.execute(select(func.count()).select_from(MarketDataSilver)).scalar_one() == 2
    assert session.execute(select(func.count()).select_from(MarketDataGold)).scalar_one() == 2

    analysen = session.execute(select(AnalysisResult)).scalars().all()
    assert len(analysen) == 3
    assert sum(1 for a in analysen if a.sanity_cap_applied) == 1
    kategorie_score_anzahl = session.execute(
        select(func.count()).select_from(AnalysisCategoryScore)
    ).scalar_one()
    assert kategorie_score_anzahl == 5 * len(analysen)
    assert session.execute(select(func.count()).select_from(AnalysisFact)).scalar_one() >= 1

    gate_ergebnisse = session.execute(select(GateResult)).scalars().all()
    assert len(gate_ergebnisse) == 1
    assert gate_ergebnisse[0].ampel in ("gruen", "gelb", "rot")

    assert session.execute(select(func.count()).select_from(RuleHypothesis)).scalar_one() == 1
    assert session.execute(select(func.count()).select_from(TrialRegistry)).scalar_one() == 1


def test_seed_demo_data_schreibt_ausschliesslich_mode_simuliert(session: Session) -> None:
    seed_demo_data(session)

    positionen = session.execute(select(Position)).scalars().all()
    assert positionen and all(p.mode == "simuliert" for p in positionen)

    transaktionen = session.execute(select(Transaction)).scalars().all()
    assert transaktionen and all(t.mode == "simuliert" for t in transaktionen)

    analysen = session.execute(select(AnalysisResult)).scalars().all()
    assert analysen and all(a.mode == "simuliert" for a in analysen)


def _zeilenzahlen(session: Session) -> dict[str, int]:
    tabellen = {
        "instrument": Instrument,
        "position": Position,
        "transaction": Transaction,
        "depot_fill_dedup": DepotFillDedup,
        "market_data_bronze": MarketDataBronze,
        "market_data_silver": MarketDataSilver,
        "market_data_gold": MarketDataGold,
        "analysis_result": AnalysisResult,
        "analysis_category_score": AnalysisCategoryScore,
        "analysis_fact": AnalysisFact,
        "rule_hypothesis": RuleHypothesis,
        "trial_registry": TrialRegistry,
        "gate_result": GateResult,
    }
    return {
        name: session.execute(select(func.count()).select_from(modell)).scalar_one()
        for name, modell in tabellen.items()
    }


def test_seed_demo_data_is_idempotent(session: Session) -> None:
    seed_demo_data(session)
    zeilenzahlen_lauf_1 = _zeilenzahlen(session)

    seed_demo_data(session)
    zeilenzahlen_lauf_2 = _zeilenzahlen(session)

    assert zeilenzahlen_lauf_2 == zeilenzahlen_lauf_1


def _demo_dateien() -> list[Path]:
    return sorted(p for p in _DEMO_MODUL_ROOT.glob("*.py") if p.is_file())


def _importierte_module(baum: ast.AST) -> list[str]:
    module: list[str] = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            module.extend(alias.name for alias in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.module is not None:
            module.append(knoten.module)
    return module


def test_demo_modul_importiert_keinen_order_pfad() -> None:
    for datei in _demo_dateien():
        baum = ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
        for modul in _importierte_module(baum):
            for praefix in _VERBOTENE_PRAEFIXE:
                assert not (modul == praefix or modul.startswith(praefix + ".")), (
                    f"{datei} importiert Order-Pfad-Modul {modul!r} (AC22-Verstoss)"
                )
            if modul.startswith(_PIPELINE_PARENT + ".") and modul.endswith(_PIPELINE_SUFFIX):
                pytest.fail(f"{datei} importiert Pipeline-Modul {modul!r} (AC22-Verstoss)")
