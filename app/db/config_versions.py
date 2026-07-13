"""Versionierungs-Mechanik für Methodentabellen + Kategoriegewichte (AC10).

Jede Konfigurationsänderung (Kategoriegewichte ODER Methodentabellen) legt
eine neue, referenzierbare Version an (append-only, vollständiger Snapshot)
statt bestehende Zeilen zu überschreiben; die jeweils gültige Version ist
über `is_current = True` markiert (data-model.md `category_weight_version` /
`analysis_method_version`, BR-133, DB-seitig durch einen partiellen
UNIQUE-Index erzwungen).

Beide Konfig-Domänen versionieren **unabhängig** voneinander — kein
gemeinsamer Versionszähler (siehe Migration `386f43ae972d`/`8f183aee9753`
Docstrings). Eine künftige `analysis_result`-Zeile referenziert bei Bedarf
beide IDs getrennt (Folge-Story, sobald `analysis_result` existiert,
docs/data-model.md §11).

Diese Funktionen erwarten den **vollständigen** neuen Stand (kein
automatisches Fortschreiben unveränderter Zeilen aus der Vorversion) — die
Aufruferseite ist für Vollständigkeit verantwortlich; das hält den
Versions-Snapshot einfach nachvollziehbar (kein impliziter Merge).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.category_weights import validate_category_weights
from app.db.models import (
    AnalysisMethod,
    AnalysisMethodVersion,
    CategoryWeight,
    CategoryWeightVersion,
)


def _markiere_bisherige_version_als_veraltet(session: Session, version_model: type) -> None:
    """Setzt eine ggf. bestehende `is_current=True`-Zeile von `version_model`
    auf `False` — Voraussetzung für BR-133 (genau eine aktuelle Version),
    bevor eine neue Version eingefügt wird."""
    bisherige = (
        session.execute(select(version_model).where(version_model.is_current.is_(True)))
        .scalars()
        .all()
    )
    for version in bisherige:
        version.is_current = False


def erstelle_neue_category_weight_version(
    session: Session,
    *,
    gewichte_je_klasse: Mapping[int, Mapping[str, Decimal | float | int]],
    note: str | None = None,
) -> CategoryWeightVersion:
    """Legt eine neue `category_weight`-Version an (AC10).

    `gewichte_je_klasse` bildet `asset_class_id -> {category_code: weight_pct}`
    ab und muss den **vollständigen** neuen Stand tragen (alle Klassen, deren
    Gewichte in der neuen Version gelten sollen). Jede Klassen-Gewichtung
    wird vorab über `validate_category_weights` geprüft (AC7/E1) — bei einer
    ungültigen Gewichtung wird **keine** Version angelegt (nichts wird
    wirksam, Session bleibt unverändert bis auf die geprüfte Ausnahme).

    Die zuvor aktuelle Version bleibt als Historie erhalten (append-only,
    `is_current` wird auf `False` gesetzt) — kein Überschreiben bestehender
    Zeilen.
    """
    for gewichte in gewichte_je_klasse.values():
        validate_category_weights(dict(gewichte))

    _markiere_bisherige_version_als_veraltet(session, CategoryWeightVersion)

    neue_version = CategoryWeightVersion(is_current=True, note=note)
    session.add(neue_version)
    session.flush()  # config_version_id fuer die neuen Zeilen verfuegbar

    for asset_class_id, gewichte in gewichte_je_klasse.items():
        for category_code, weight_pct in gewichte.items():
            session.add(
                CategoryWeight(
                    asset_class_id=asset_class_id,
                    category_code=category_code,
                    config_version_id=neue_version.id,
                    weight_pct=Decimal(str(weight_pct)),
                )
            )
    return neue_version


def erstelle_neue_analysis_method_version(
    session: Session,
    *,
    methoden: Sequence[Mapping[str, Any]],
    note: str | None = None,
) -> AnalysisMethodVersion:
    """Legt eine neue `analysis_method`-Version an (AC10).

    `methoden` trägt den **vollständigen** neuen Stand (jedes Element ein
    Feld-Mapping analog `AnalysisMethod`-Spalten, z.B. `asset_class_id`,
    `category_code`, `code`, `kurzbezeichnung`, `ranking`, …) — kein
    automatisches Fortschreiben unveränderter Zeilen aus der Vorversion.

    `ranking` wird NICHT app-seitig vorab geprüft (data-model.md BR-102:
    Enforcement-Layer ist ausschliesslich DB-CHECK) — eine ungültige
    Ranking-Zeile wirft beim `session.flush()`/`commit()` eine
    `sqlalchemy.exc.IntegrityError` (Zeilen-CHECK
    `ck_analysis_method_ranking_range`).

    Die zuvor aktuelle Version bleibt als Historie erhalten (append-only).
    """
    _markiere_bisherige_version_als_veraltet(session, AnalysisMethodVersion)

    neue_version = AnalysisMethodVersion(is_current=True, note=note)
    session.add(neue_version)
    session.flush()

    for methode in methoden:
        session.add(AnalysisMethod(config_version_id=neue_version.id, **methode))
    return neue_version
