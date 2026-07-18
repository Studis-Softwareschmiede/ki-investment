"""Anlageklassen-Lesepfad (Story S-069, `docs/specs/frontend-cockpit.md`
AC9) — analog `app.db.depotstrategie.lade_aktive_depotstrategie`: ein reiner
Lesepfad, der die 11 seed-gepflegten `AssetClass`-Zeilen (`app.db.models
.AssetClass`, S-003/AC12, Toggle S-019) direkt als Cockpit-Vertrag
(`app.contracts.anlageklassen_config.AnlageklasseEintrag`) liefert — die
einzige erlaubte Quelle für `GET /api/config/anlageklassen`
(`app.api.config`/`app.api.queries.config`)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.db.models import AssetClass


def lade_alle_anlageklassen(session: Session) -> list[AnlageklasseEintrag]:
    """AC9: alle 11 Anlageklassen mit Toggle-Zustand (`aktiv`) + Prio
    (`prio_stufe`), sortiert nach `id`."""
    zeilen = session.execute(select(AssetClass).order_by(AssetClass.id)).scalars().all()
    return [
        AnlageklasseEintrag(
            id=zeile.id, name=zeile.name, aktiv=zeile.aktiv, prio_stufe=zeile.prio_stufe
        )
        for zeile in zeilen
    ]


__all__ = ["lade_alle_anlageklassen"]
