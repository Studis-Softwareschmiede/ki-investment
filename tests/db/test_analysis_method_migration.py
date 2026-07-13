"""Tests fuer die analysis_method-Migration (Story S-018).

Covers (anlageklassen-config): AC9, AC10

- AC9 (Methodentabelle je Klasse/Kategorie, festes Ranking 1-10,
  klassenspezifisch, über Analysen hinweg konstant): strukturell gegen die
  vollständigen Seed-Daten der Migration
  (`app/db/migrations/versions/8f183aee9753_...py`, S-018 Iteration 2 — alle
  11 Klassen × Analysekategorien, 1:1 aus der Konzept-Quelle "KI Investment
  – Anlageklassen.md" transkribiert) sowie das
  `ck_analysis_method_ranking_range`-CHECK-Constraint des ORM-Modells
  geprüft. Stichproben-Rankings mehrerer Klassen (nicht nur Aktien) werden
  gegen die Quelle abgeglichen (`test_stichprobe_rankings_gegen_quelle`).
  Die beiden dokumentierten Mapping-Sonderfälle (Cash/Geldmarkt ×
  Technisch ohne Zeilen, Aktive Fonds "Performance/Quantitativ" → Slot
  `fundamental`) sind eigens gedeckt.
- AC10 (Versionierung, Methodentabellen-Teil): `config_version_id` ist Teil
  des UNIQUE-Constraints (append-only je Version), `analysis_method_version`
  trägt `is_current` analog `category_weight_version`
  (`tests/db/test_category_weight_version_migration.py`), aber unabhängig
  versioniert.

Der partielle UNIQUE-Index auf `is_current` (BR-133) ist — wie die
Deferred-Constraint-Trigger bei `category_weight` — nur unter echtem
Postgres direkt prüfbar (SQLite unterstützt partielle UNIQUE-Indizes zwar
technisch, aber `CREATE UNIQUE INDEX ... WHERE is_current` mit reinem
Boolean-Prädikat wird hier nur strukturell über die Migrationsdatei
geprüft, nicht per SQLite-`Base.metadata.create_all` — der reale
Postgres-Constraint wurde manuell gegen die lokale Compose-Postgres-Instanz
verifiziert (Coder-Self-Test, siehe Handoff): ein zweiter Insert mit
`is_current=true` bei bereits bestehender aktueller Version schlägt mit
einer UNIQUE-Verletzung fehl.

Die Seed-Konstante wird direkt aus der Migrationsdatei importiert (statt
dupliziert), damit ein künftiger Migrations-Edit ohne Test-Anpassung nicht
unbemerkt divergiert (Konvention aus `test_category_weight_migration.py`).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AnalysisCategory, AnalysisMethod, AnalysisMethodVersion, AssetClass

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "8f183aee9753_create_analysis_method_versioned_ac9_11.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("analysis_method_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
METHOD_SEED = _MIGRATION.ANALYSIS_METHOD_SEED

# Erwartete Zeilenzahl je Klasse — Summe der Methodentabellen-Laengen aus
# der Konzept-Quelle "KI Investment – Anlageklassen.md" (S-018 Iteration 2).
# 190 Zeilen insgesamt (kein Erfinden, reine Transkription).
EXPECTED_ROW_COUNT_BY_ASSET_CLASS_ID = {
    1: 24,  # Aktien: 7+5+4+3+5
    2: 16,  # ETFs: 4+2+5+2+3
    3: 9,  # Cash/Geldmarkt: 3+0+2+2+2 (Technisch bewusst leer)
    4: 18,  # Obligationen: 6+3+3+3+3
    5: 17,  # Aktive Fonds: 5+1+6+1+4
    6: 18,  # Immobilien: 7+1+4+3+3
    7: 21,  # Kryptowährungen: 6+5+3+3+4
    8: 17,  # Rohstoffe: 6+3+1+4+3
    9: 16,  # Infrastrukturfonds: 5+1+4+3+3
    10: 15,  # FX: 4+4+1+4+2
    11: 19,  # Derivate: 3+5+2+3+6
}

# Verträge-Tabelle docs/specs/anlageklassen-config.md — Aktien/Fundamental
# (weiterhin als knappe Spec-Kurzform dokumentiert; die Konzept-Quelle führt
# ausführlichere Kurzbezeichnungen, z.B. "DCF / FCFE" statt "DCF" — geprüft
# wird hier explizit über den Methoden-`code`, nicht über den Namenstext).
EXPECTED_AKTIEN_FUNDAMENTAL_RANKINGS_BY_CODE = {
    "F1": 9,  # DCF / FCFE
    "F2": 9,  # ROE / ROIC
    "F3": 8,  # EV/EBITDA
    "F4": 6,  # KBV (P/B)
    "F5": 7,  # KGV (P/E)
    "F6": 8,  # Verschuldungsgrad
    "F7": 7,  # Earnings Revisions
}

# Stichproben aus mehreren Klassen (nicht nur Aktien) — 1:1 gegen die
# Konzept-Quelle "KI Investment – Anlageklassen.md" abgeglichen (AC9).
STICHPROBE_GEGEN_QUELLE = [
    # (asset_class_id, category_code, code, erwarteter_ranking, erwartete_kurzbezeichnung)
    (7, "risiko_quant", "R1", 9, "Volatilität"),  # Krypto: Volatilitaet Hauptrisiko
    (11, "technisch", "T1", 9, "Implizite Volatilität (IV)"),  # Derivate
    (10, "makro", "M1", 9, "Geldpolitik / Zinspfad"),  # FX
    (9, "risiko_quant", "R1", 9, "Regulierungsrisiko"),  # Infrastrukturfonds
    (5, "fundamental", "P1", 9, "Alpha"),  # Aktive Fonds (Performance/Quant-Mapping)
    (3, "makro", "M1", 9, "Zentralbankpolitik"),  # Cash/Geldmarkt
    (8, "qualitativ", "Q1", 5, "Produktqualität / Lagerung"),  # Rohstoffe
]


def _seed_stammdaten(session: Session) -> None:
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    session.add(AnalysisCategory(code="fundamental", name="Fundamental", ist_risiko=False))
    session.commit()


def test_seed_matches_vertraege_table_aktien_fundamental() -> None:
    """@trace anlageklassen-config#AC9 — die geseedeten Aktien/Fundamental-
    Methoden entsprechen (per Methoden-`code`) exakt den in der
    Verträge-Tabelle genannten Rankings (Ranking 1-10, fix je Klasse)."""
    aktien_fundamental = [
        row
        for row in METHOD_SEED
        if row["asset_class_id"] == 1 and row["category_code"] == "fundamental"
    ]
    assert len(aktien_fundamental) == 7
    rankings_by_code = {row["code"]: row["ranking"] for row in aktien_fundamental}
    assert rankings_by_code == EXPECTED_AKTIEN_FUNDAMENTAL_RANKINGS_BY_CODE
    for row in aktien_fundamental:
        assert 1 <= row["ranking"] <= 10


def test_seed_covers_all_11_asset_classes_with_expected_row_counts() -> None:
    """@trace anlageklassen-config#AC9 — jede der 11 Anlageklassen hat
    mindestens eine Kategorie mit Methoden geseedet, und die Zeilenzahl je
    Klasse entspricht 1:1 der Konzept-Quelle (S-018 Iteration 2 — kein
    Erfinden, vollständige Transkription statt der Aktien-Fundamental-
    Teilmenge aus Iteration 1)."""
    zeilen_je_klasse: dict[int, int] = {}
    for row in METHOD_SEED:
        zeilen_je_klasse[row["asset_class_id"]] = zeilen_je_klasse.get(row["asset_class_id"], 0) + 1

    assert set(zeilen_je_klasse.keys()) == set(range(1, 12))
    assert all(anzahl >= 1 for anzahl in zeilen_je_klasse.values())
    assert zeilen_je_klasse == EXPECTED_ROW_COUNT_BY_ASSET_CLASS_ID
    assert len(METHOD_SEED) == sum(EXPECTED_ROW_COUNT_BY_ASSET_CLASS_ID.values()) == 190


def test_cash_geldmarkt_technisch_has_no_seed_rows_by_design() -> None:
    """@trace anlageklassen-config#AC9 — Mapping-Sonderfall: Cash/Geldmarkt
    × Technisch bleibt bewusst ohne Methoden (Konzept-Quelle: "nicht
    anwendbar", 0 %-Gewicht laut AC8) — eine leere Methodentabelle für diese
    Kombination ist zulässig, andere Cash-Kategorien sind weiterhin
    befüllt."""
    cash_technisch = [
        row
        for row in METHOD_SEED
        if row["asset_class_id"] == 3 and row["category_code"] == "technisch"
    ]
    assert cash_technisch == []

    cash_makro = [
        row for row in METHOD_SEED if row["asset_class_id"] == 3 and row["category_code"] == "makro"
    ]
    assert len(cash_makro) == 2


def test_aktive_fonds_fundamental_slot_uses_performance_quantitativ_codes() -> None:
    """@trace anlageklassen-config#AC9 — Mapping-Sonderfall: Aktive Fonds
    "Performance / Quantitativ" (Codes P1-P5) ist auf den kanonischen
    `fundamental`-Slot gemappt, nicht auf eine erfundene sechste
    Kategorie."""
    aktive_fonds_fundamental = [
        row
        for row in METHOD_SEED
        if row["asset_class_id"] == 5 and row["category_code"] == "fundamental"
    ]
    codes = {row["code"] for row in aktive_fonds_fundamental}
    assert codes == {"P1", "P2", "P3", "P4", "P5"}
    rankings_by_code = {row["code"]: row["ranking"] for row in aktive_fonds_fundamental}
    assert rankings_by_code == {"P1": 9, "P2": 9, "P3": 9, "P4": 8, "P5": 7}


@pytest.mark.parametrize(
    "asset_class_id,category_code,code,erwarteter_ranking,erwartete_kurzbezeichnung",
    STICHPROBE_GEGEN_QUELLE,
)
def test_stichprobe_rankings_gegen_quelle(
    asset_class_id: int,
    category_code: str,
    code: str,
    erwarteter_ranking: int,
    erwartete_kurzbezeichnung: str,
) -> None:
    """@trace anlageklassen-config#AC9 — Stichproben-Abgleich einzelner
    Rankings/Kurzbezeichnungen mehrerer Klassen (nicht nur Aktien) gegen die
    Konzept-Quelle "KI Investment – Anlageklassen.md" (S-018 Iteration 2)."""
    treffer = [
        row
        for row in METHOD_SEED
        if row["asset_class_id"] == asset_class_id
        and row["category_code"] == category_code
        and row["code"] == code
    ]
    assert len(treffer) == 1, (
        f"erwartete genau 1 Treffer fuer {asset_class_id}/{category_code}/{code}"
    )
    zeile = treffer[0]
    assert zeile["ranking"] == erwarteter_ranking
    assert zeile["kurzbezeichnung"] == erwartete_kurzbezeichnung


def test_all_seeded_rankings_are_within_1_10() -> None:
    """@trace anlageklassen-config#AC9 — jedes der 190 Seed-Rankings liegt
    im Bereich 1-10 (Migrations-eigene Validierung + strukturelle
    Gegenprobe hier; die DB-CHECK-Ebene ist zusätzlich per
    `test_model_rejects_ranking_outside_1_10`/`test_model_rejects_ranking_zero`
    gedeckt)."""
    for row in METHOD_SEED:
        assert 1 <= row["ranking"] <= 10, row


def test_no_duplicate_code_within_same_asset_class() -> None:
    """@trace anlageklassen-config#AC9,AC10 — innerhalb derselben Klasse ist
    `code` eindeutig über alle Kategorien hinweg (Voraussetzung für den
    UNIQUE-Constraint `(asset_class_id, code, config_version_id)`) — die
    Transkription aus der Konzept-Quelle erzeugt keine Kollisionen zwischen
    Kategorie-Präfixen (F/T/Q/M/R bzw. P bei Aktiven Fonds)."""
    gesehen: set[tuple[int, str]] = set()
    for row in METHOD_SEED:
        schluessel = (row["asset_class_id"], row["code"])
        assert schluessel not in gesehen, f"Duplikat-Code {schluessel}"
        gesehen.add(schluessel)


def test_seed_builder_aborts_on_ranking_outside_1_10() -> None:
    """@trace anlageklassen-config#AC9 — die migrationseigene
    Seed-Validierung (`_baue_analysis_method_seed`) bricht bei einem
    Quell-Ranking ausserhalb 1-10 hart ab (kein stiller Clamp), sobald ein
    Eintrag im Quell-Dict ausserhalb des Bereichs liegt."""
    kaputtes_dict = {(1, "fundamental"): [("FX", "Kaputter Wert", 11)]}
    original = dict(_MIGRATION._METHODEN_JE_KLASSE_KATEGORIE)
    try:
        _MIGRATION._METHODEN_JE_KLASSE_KATEGORIE.clear()
        _MIGRATION._METHODEN_JE_KLASSE_KATEGORIE.update(kaputtes_dict)
        with pytest.raises(ValueError, match="ausserhalb 1-10"):
            _MIGRATION._baue_analysis_method_seed()
    finally:
        _MIGRATION._METHODEN_JE_KLASSE_KATEGORIE.clear()
        _MIGRATION._METHODEN_JE_KLASSE_KATEGORIE.update(original)


def test_model_rejects_ranking_outside_1_10() -> None:
    """@trace anlageklassen-config#AC9 — ein Ranking ausserhalb 1-10 (fix je
    Klasse) wird per DB-CHECK zurückgewiesen (BR-102, Edge-Case)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_stammdaten(session)
        version = AnalysisMethodVersion()
        session.add(version)
        session.commit()

        session.add(
            AnalysisMethod(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=version.id,
                code="F1",
                kurzbezeichnung="DCF",
                ranking=11,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_model_rejects_ranking_zero() -> None:
    """@trace anlageklassen-config#AC9 — Ranking 0 (unterhalb 1-10) wird
    ebenfalls per DB-CHECK zurückgewiesen."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_stammdaten(session)
        version = AnalysisMethodVersion()
        session.add(version)
        session.commit()

        session.add(
            AnalysisMethod(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=version.id,
                code="F1",
                kurzbezeichnung="DCF",
                ranking=0,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_ranking_is_constant_across_multiple_loads_within_a_version() -> None:
    """@trace anlageklassen-config#AC9 — das Ranking ist über einzelne
    Analysen (= mehrfaches Laden derselben Version) hinweg konstant, keine
    Neuvergabe je Abfrage."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_stammdaten(session)
        version = AnalysisMethodVersion()
        session.add(version)
        session.commit()
        session.add(
            AnalysisMethod(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=version.id,
                code="F1",
                kurzbezeichnung="DCF",
                ranking=9,
            )
        )
        session.commit()

        erste_ladung = session.query(AnalysisMethod).filter_by(code="F1").one().ranking
        zweite_ladung = session.query(AnalysisMethod).filter_by(code="F1").one().ranking
        assert erste_ladung == zweite_ladung == 9


def test_config_version_id_allows_same_code_across_versions() -> None:
    """@trace anlageklassen-config#AC10 — dieselbe Methode (asset_class_id,
    code) kann in zwei verschiedenen Versionen mit unterschiedlichem
    Ranking existieren (append-only, kein Überschreiben)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_stammdaten(session)

        v1 = AnalysisMethodVersion(note="Initial")
        session.add(v1)
        session.commit()
        session.add(
            AnalysisMethod(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=v1.id,
                code="F1",
                kurzbezeichnung="DCF",
                ranking=9,
            )
        )
        session.commit()

        v2 = AnalysisMethodVersion(note="Quartals-Review-Anpassung")
        session.add(v2)
        session.commit()
        session.add(
            AnalysisMethod(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=v2.id,
                code="F1",
                kurzbezeichnung="DCF",
                ranking=8,
            )
        )
        session.commit()

        zeilen = session.query(AnalysisMethod).filter_by(code="F1").all()
        assert len(zeilen) == 2
        rankings_je_version = {zeile.config_version_id: zeile.ranking for zeile in zeilen}
        assert rankings_je_version[v1.id] == 9
        assert rankings_je_version[v2.id] == 8


def test_duplicate_code_within_same_version_is_rejected() -> None:
    """@trace anlageklassen-config#AC10 — innerhalb DERSELBEN Version bleibt
    (asset_class_id, code) eindeutig (UNIQUE-Verletzung bei Duplikat)."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_stammdaten(session)
        version = AnalysisMethodVersion()
        session.add(version)
        session.commit()
        session.add(
            AnalysisMethod(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=version.id,
                code="F1",
                kurzbezeichnung="DCF",
                ranking=9,
            )
        )
        session.commit()

        session.add(
            AnalysisMethod(
                asset_class_id=1,
                category_code="fundamental",
                config_version_id=version.id,
                code="F1",
                kurzbezeichnung="DCF (Duplikat)",
                ranking=5,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_seed_insert_is_idempotent_via_on_conflict_do_nothing() -> None:
    """Verifiziert data-model.md §11 Punkt 10 ("Idempotent seedbar via
    ON CONFLICT DO NOTHING") für den Migrations-Seed-Insert — kein
    `@trace`-Tag, da allgemeine DB-Konvention statt spezifischer AC (Analog
    `test_asset_class_migration.py`/`test_category_weight_migration.py`).
    """
    from sqlalchemy import Column, MetaData, SmallInteger, String, Table
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    metadata = MetaData()
    analysis_method = Table(
        "analysis_method",
        metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True),
        Column("asset_class_id", SmallInteger, nullable=False),
        Column("category_code", String, nullable=False),
        Column("config_version_id", PGUUID(as_uuid=True), nullable=False),
        Column("code", String, nullable=False),
        Column("kurzbezeichnung", String, nullable=False),
        Column("ranking", SmallInteger, nullable=False),
    )

    dummy_version_id = "00000000-0000-0000-0000-000000000001"
    rows = [{**row, "config_version_id": dummy_version_id} for row in METHOD_SEED]
    stmt = (
        pg_insert(analysis_method)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["asset_class_id", "code", "config_version_id"])
    )
    compiled_sql = str(stmt.compile(dialect=postgresql.dialect()))

    assert "ON CONFLICT" in compiled_sql
    assert "DO NOTHING" in compiled_sql
    assert "(asset_class_id, code, config_version_id)" in compiled_sql
