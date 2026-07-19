"""Anlageklassen-Lese-/Schreibpfad (Story S-069, `docs/specs/frontend-cockpit.md`
AC9; Story S-074, AC20) — analog `app.db.depotstrategie.lade_aktive_depotstrategie`:
ein reiner Lesepfad, der die 11 seed-gepflegten `AssetClass`-Zeilen
(`app.db.models.AssetClass`, S-003/AC12, Toggle S-019) direkt als
Cockpit-Vertrag (`app.contracts.anlageklassen_config.AnlageklasseEintrag`)
liefert — die einzige erlaubte Quelle für `GET /api/config/anlageklassen`
(`app.api.config`/`app.api.queries.config`).

`setze_toggle` (S-074, AC20) ist der Konfig-Schreibpfad hinter `POST
/api/control/anlageklassen/{asset_class_id}/toggle` (→ BR-017/BR-018): das
einzige erlaubte Schreib-Gegenstück, direkt auf derselben Spalte
(`AssetClass.aktiv`) wie `lade_alle_anlageklassen` liest — kein zweiter,
abweichender Persistenz-Pfad. BR-018 ("Deaktivierung lässt gehaltene
Positionen nicht erblinden") ist keine Schreib-Sperre — eine Deaktivierung
mit offenen Positionen bleibt erlaubt (nur `neue_verarbeitung_erlaubt`
sperrt, `app.domain.assetclasses.toggle_guard`, S-019); diese Funktion
schreibt den reinen Toggle-Zustand unbedingt.

**Präzisierung (Story S-076, AC18):** beide Funktionen liefern zusätzlich
`hat_offene_positionen` (→ BR-018-Warn-Band der Konfigurations-View) —
ermittelt über eine direkte `Position.status == "offen"`-Abfrage
(modus-übergreifend, siehe `AnlageklasseEintrag`-Docstring). Bewusst ohne
`PositionRepository`-Port/Adapter-Umweg: `app/db/asset_classes.py` hat
bereits eine gebundene `Session` (Modul-Konvention dieser Datei), eine
zusätzliche Repository-Instanziierung hier wäre ein unnötiger zweiter
Zugriffspfad auf dieselbe Tabelle."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.db.models import AssetClass, Position


def _anlageklassen_mit_offenen_positionen(session: Session) -> set[int]:
    """AC18 (→ BR-018): die Menge der `asset_class_id`, die mindestens eine
    offene Position (`Position.status == "offen"`) halten — modus-
    übergreifend (siehe `AnlageklasseEintrag.hat_offene_positionen`-
    Docstring)."""
    abfrage = select(Position.asset_class_id).where(Position.status == "offen").distinct()
    zeilen = session.execute(abfrage).scalars().all()
    return set(zeilen)


def lade_alle_anlageklassen(session: Session) -> list[AnlageklasseEintrag]:
    """AC9/AC18: alle 11 Anlageklassen mit Toggle-Zustand (`aktiv`) + Prio
    (`prio_stufe`) + `hat_offene_positionen` (→ BR-018-Warn-Band),
    sortiert nach `id`."""
    zeilen = session.execute(select(AssetClass).order_by(AssetClass.id)).scalars().all()
    offene_klassen = _anlageklassen_mit_offenen_positionen(session)
    return [
        AnlageklasseEintrag(
            id=zeile.id,
            name=zeile.name,
            aktiv=zeile.aktiv,
            prio_stufe=zeile.prio_stufe,
            hat_offene_positionen=zeile.id in offene_klassen,
        )
        for zeile in zeilen
    ]


def setze_toggle(session: Session, asset_class_id: int, aktiv: bool) -> AnlageklasseEintrag | None:
    """AC20 (→ BR-017/BR-018): setzt `AssetClass.aktiv` für genau eine
    Anlageklasse und liefert den aktualisierten Cockpit-Eintrag (inkl.
    `hat_offene_positionen`, AC18) zurück — `None`, wenn `asset_class_id`
    keine bestehende Zeile referenziert (der Router meldet das als 404)."""
    zeile = session.get(AssetClass, asset_class_id)
    if zeile is None:
        return None
    zeile.aktiv = aktiv
    session.commit()
    session.refresh(zeile)
    hat_offene_positionen = zeile.id in _anlageklassen_mit_offenen_positionen(session)
    return AnlageklasseEintrag(
        id=zeile.id,
        name=zeile.name,
        aktiv=zeile.aktiv,
        prio_stufe=zeile.prio_stufe,
        hat_offene_positionen=hat_offene_positionen,
    )


__all__ = ["lade_alle_anlageklassen", "setze_toggle"]
