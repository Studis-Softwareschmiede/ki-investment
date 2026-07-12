"""Validierungs-Layer fuer eingehende Bronze-Kandidaten (Story S-023).

Deckt `docs/specs/datenqualitaet.md` AC7/AC8:

- **AC7 (Pflicht-Regeln, ab MVP aktiv, nicht abschaltbar):**
  `validate_bronze_kandidat()` prueft jeden Kandidaten gegen die drei in AC7
  genannten Pflicht-Regeln-Kategorien:
  1. **Schema/Feldtypen** — `beobachtungs_zeitpunkt` muss ein `datetime`,
     `source_event_id` ein `str`, `anlageklassen_tag` (falls gesetzt) ein
     `int` sein.
  2. **erlaubte Wertebereiche** — `anlageklassen_tag` (falls gesetzt) muss
     in `1..11` liegen (dieselbe Domaene wie `AssetClass.id`,
     data-model.md §1 CHECK `id BETWEEN 1 AND 11`, und der
     `Datenpunkt.anlageklassen_tag`-Vertrag aus `dateneingang.py`).
  3. **Pflicht-Metadaten-Vollstaendigkeit** — die laut data-model.md §2 als
     `NOT NULL` deklarierten Bronze-Datensatz-Felder (`quelle`/
     `data_source_id`, `event_id`/`source_event_id`,
     `beobachtungs_zeitpunkt`/`observed_at`, `roh_wert`/`payload`) muessen
     gesetzt sein. `anlageklassen_tag` ist laut data-model.md §2 physisch
     nullable — daher NICHT Teil der Pflicht-Metadaten-Vollstaendigkeit,
     sondern nur (falls gesetzt) der Wertebereichspruefung unterworfen
     (Spec-Praezisierung in `docs/specs/datenqualitaet.md`, Vertrag
     "Validierungs-Ergebnis").
  4. **Event-ID-Kollision** (Edge-Case-Abschnitt der Spec, explizit AC7/AC8
     zugeordnet und laut S-022-Handoff dieser Story uebertragen): trifft
     fuer eine bereits bekannte Ereignis-Identitaet
     `(data_source_id, source_event_id)` ein Kandidat mit ABWEICHENDEM
     `beobachtungs_zeitpunkt` ein, ist das keine Revision derselben
     Beobachtung (AC10/A1 — dort bleibt `beobachtungs_zeitpunkt` gleich, nur
     der Wert aendert sich, siehe `tests/db/test_bronze.py::
     test_revision_creates_new_pit_version_without_overwriting_old_row`),
     sondern eine Ereignis-ID, die faelschlich fuer eine andere Beobachtung
     wiederverwendet wurde -> Validierungsfehler `event_id_kollision`.
  Es gibt keinen Parameter/Konfigurationsschalter, der die Pruefung umgeht
  (NFR "Pflicht ab MVP: der Validierungs-Layer darf nicht abschaltbar
  sein").

- **AC8 (verwerfen + protokollieren, deckt E1):** ein ungueltiger Kandidat
  bekommt `ValidierungsErgebnis.valide=False` plus die Liste der verletzten
  Regeln und wird strukturiert geloggt (`logger.warning`) — analog zum
  bereits etablierten Muster fuer den strukturgleichen AC2-Fall der
  `dateneingang`-Spec (`app.adapters.sockets.base.SocketAdapter.fetch`,
  dort ebenfalls nur `logger.warning`, keine DB-Tabelle). Aufrufer (die
  spaetere Silver-Schreibstufe, ausserhalb dieser Story) duerfen einen
  Kandidaten mit `valide=False` nicht weiterreichen — dass er dadurch
  "nicht in den Gold-Ergebnissen erscheint", ist eine Anschlusspflicht der
  (noch nicht gebauten) Silver/Gold-Schreibpfade, nicht dieses Moduls.

**Warum kein DB-Log-Table:** Der Spec-Vertrag "Validierungs-Ergebnis:
{ event_id, valide, verletzte_regeln[...], zeitstempel }" nennt keine
Persistenzform; `docs/data-model.md` definiert (Stand dieser Story) keine
physische Tabelle dafuer, und der BR-100er-Katalog (data-model.md §10)
endet bei BR-131 ohne Eintrag fuer diesen Validierungs-Layer. Eine
dauerhaft abfragbare Persistenz (eigene Tabelle/Migration) ist eine
Schema-Entscheidung ausserhalb der Coder-Kompetenz dieser Story
(SPEC-LUECKE, siehe Coder-Handoff S-023) — diese Story bildet den Vertrag
daher, wie den strukturell identischen Fall in `dateneingang` AC2, rein
applikationsseitig per strukturiertem Log ab.

`validate_bronze_kandidat()` ist bewusst eine von `app.db.bronze
.record_observation()` UNABHAENGIGE Funktion (kein automatischer Aufruf
ineinander) — die Verdrahtung "erst Bronze schreiben (Main-Flow-Schritt 2),
dann validieren (Main-Flow-Schritt 3)" ist Sache der kuenftigen
Orchestrierungsschicht (noch nicht Teil der Codebasis), nicht dieses
Moduls.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.bronze import _als_utc_naiv
from app.db.models import MarketDataBronze

logger = logging.getLogger(__name__)

# AC7 "erlaubte Wertebereiche": dieselbe Domaene wie `AssetClass.id`
# (data-model.md §1, CHECK `id BETWEEN 1 AND 11`).
ANLAGEKLASSEN_TAG_MIN = 1
ANLAGEKLASSEN_TAG_MAX = 11

# Regel-Bezeichner (AC7/AC8) — als Konstanten exportiert, damit Aufrufer/Tests
# nicht auf frei getippte Strings angewiesen sind.
REGEL_QUELLE_FEHLT = "quelle_fehlt"
REGEL_EVENT_ID_FEHLT = "event_id_fehlt"
REGEL_EVENT_ID_FALSCHER_TYP = "event_id_falscher_typ"
REGEL_BEOBACHTUNGS_ZEITPUNKT_FEHLT = "beobachtungs_zeitpunkt_fehlt"
REGEL_BEOBACHTUNGS_ZEITPUNKT_FALSCHER_TYP = "beobachtungs_zeitpunkt_falscher_typ"
REGEL_ROH_WERT_FEHLT = "roh_wert_fehlt"
REGEL_ANLAGEKLASSEN_TAG_FALSCHER_TYP = "anlageklassen_tag_falscher_typ"
REGEL_ANLAGEKLASSEN_TAG_AUSSERHALB_WERTEBEREICH = "anlageklassen_tag_ausserhalb_wertebereich"
REGEL_EVENT_ID_KOLLISION = "event_id_kollision"


@dataclass(frozen=True)
class ValidierungsErgebnis:
    """Spec-Vertrag "Validierungs-Ergebnis" (`docs/specs/datenqualitaet.md`)."""

    event_id: str
    valide: bool
    verletzte_regeln: tuple[str, ...]
    zeitstempel: datetime


def validate_bronze_kandidat(
    session: Session,
    *,
    data_source_id: uuid.UUID | None,
    source_event_id: str | None,
    payload: Any,
    beobachtungs_zeitpunkt: datetime | None,
    anlageklassen_tag: int | None = None,
) -> ValidierungsErgebnis:
    """Prueft einen Bronze-Kandidaten gegen die AC7-Pflicht-Regeln und
    protokolliert einen ungueltigen Befund mit Grund (AC8). Nicht
    abschaltbar — es existiert kein Parameter, der die Pruefung uebergeht.
    """
    verletzte_regeln: list[str] = []

    # --- Pflicht-Metadaten-Vollstaendigkeit (AC7) ---
    if data_source_id is None:
        verletzte_regeln.append(REGEL_QUELLE_FEHLT)

    if source_event_id is None or (
        isinstance(source_event_id, str) and not source_event_id.strip()
    ):
        verletzte_regeln.append(REGEL_EVENT_ID_FEHLT)
    elif not isinstance(source_event_id, str):
        verletzte_regeln.append(REGEL_EVENT_ID_FALSCHER_TYP)

    if beobachtungs_zeitpunkt is None:
        verletzte_regeln.append(REGEL_BEOBACHTUNGS_ZEITPUNKT_FEHLT)
    elif not isinstance(beobachtungs_zeitpunkt, datetime):
        verletzte_regeln.append(REGEL_BEOBACHTUNGS_ZEITPUNKT_FALSCHER_TYP)

    if payload is None:
        verletzte_regeln.append(REGEL_ROH_WERT_FEHLT)

    # --- Schema/Feldtypen + erlaubte Wertebereiche (AC7) ---
    if anlageklassen_tag is not None:
        if not isinstance(anlageklassen_tag, int) or isinstance(anlageklassen_tag, bool):
            verletzte_regeln.append(REGEL_ANLAGEKLASSEN_TAG_FALSCHER_TYP)
        elif not (ANLAGEKLASSEN_TAG_MIN <= anlageklassen_tag <= ANLAGEKLASSEN_TAG_MAX):
            verletzte_regeln.append(REGEL_ANLAGEKLASSEN_TAG_AUSSERHALB_WERTEBEREICH)

    # --- Event-ID-Kollision (Edge-Case, AC7/AC8) ---
    if (
        data_source_id is not None
        and isinstance(source_event_id, str)
        and source_event_id.strip()
        and isinstance(beobachtungs_zeitpunkt, datetime)
        and _hat_abweichende_beobachtung(
            session,
            data_source_id=data_source_id,
            source_event_id=source_event_id,
            beobachtungs_zeitpunkt=beobachtungs_zeitpunkt,
        )
    ):
        verletzte_regeln.append(REGEL_EVENT_ID_KOLLISION)

    ergebnis = ValidierungsErgebnis(
        event_id=source_event_id if isinstance(source_event_id, str) else "",
        valide=not verletzte_regeln,
        verletzte_regeln=tuple(verletzte_regeln),
        zeitstempel=datetime.now(tz=UTC),
    )

    if not ergebnis.valide:
        # AC8: verwerfen + MIT GRUND protokollieren (deckt E1).
        logger.warning(
            "Bronze-Kandidat als ungueltig markiert (AC7/AC8, event_id=%s, quelle=%s): %s",
            ergebnis.event_id or "<fehlt>",
            data_source_id,
            ", ".join(ergebnis.verletzte_regeln),
        )

    return ergebnis


def _hat_abweichende_beobachtung(
    session: Session,
    *,
    data_source_id: uuid.UUID,
    source_event_id: str,
    beobachtungs_zeitpunkt: datetime,
) -> bool:
    """Edge-Case-Erkennung (AC7/AC8): existiert fuer dieselbe
    Ereignis-Identitaet `(data_source_id, source_event_id)` bereits eine
    Bronze-Zeile mit ABWEICHENDEM `observed_at`? Dann handelt es sich nicht
    um eine Revision derselben Beobachtung (AC10/A1 — dort bleibt
    `observed_at` gleich, nur der Wert aendert sich), sondern um eine
    Ereignis-ID, die faelschlich fuer eine andere Beobachtung wiederverwendet
    wurde."""
    bestehende_beobachtungszeitpunkte = (
        session.execute(
            select(MarketDataBronze.observed_at)
            .where(
                MarketDataBronze.data_source_id == data_source_id,
                MarketDataBronze.source_event_id == source_event_id,
            )
            .distinct()
        )
        .scalars()
        .all()
    )

    ziel = _als_utc_naiv(beobachtungs_zeitpunkt)
    return any(_als_utc_naiv(vorhanden) != ziel for vorhanden in bestehende_beobachtungszeitpunkte)
