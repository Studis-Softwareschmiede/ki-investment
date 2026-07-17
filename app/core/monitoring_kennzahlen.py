"""Alert-Fatigue-Leitplanke: Monitoring-Kennzahl "Ereignisse pro Tag"
(Story S-033, Spec `docs/specs/depot-ueberwachung.md` AC7, Main-Success-
Scenario Schritt 6: "zählt die je Tag ausgelösten Ereignisse als
Monitoring-Kennzahl").

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4: "core/
... kill_switch, heartbeat, drawdown_monitor, secrets, logging, errors" —
dieselbe Kategorie deterministischer Betriebszustand, kein I/O), analog
`app.core.hallucination_kpi` (in-memory Registrierungs-Historie +
Zeitfenster-/Tages-Auswertung statt DB-Persistenz — kein Story-Scope für
eine dedizierte Tabelle, siehe `docs/data-model.md`, das für die
Depot-Überwachung kein Monitoring-Kennzahl-Schema führt).

`registriere_ereignisse` wird vom Aufrufer (Orchestrierung,
`app.orchestration.depot_ueberwachung.werte_monitoring_ereignisse_aus`) je
Zyklus mit der Anzahl der in diesem Zyklus erzeugten
`UeberwachungsEreignis`-Objekte aufgerufen; `berechne_tageskennzahl`
zählt die für den angefragten Kalendertag (UTC) registrierten Ereignisse
und markiert `zu_sensibel=True`, sobald der konfigurierte Tages-
Schwellwert (Default 10, AC7) STRIKT überschritten wird (Edge-Case "genau
am Schwellwert -> kein Alarm", analog dem Schwellwertvergleich in
`app.core.hallucination_kpi.berechne_kpi`)."""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime

from app.config import get_settings
from app.contracts.depot_ueberwachung import MonitoringTagesKennzahl

_lock = threading.Lock()
#: Zeitpunkte aller bisher registrierten Ereignisse (App-Start bis jetzt,
#: bzw. bis zum letzten `reset_fuer_tests()`).
_registrierungen: list[datetime] = []


def registriere_ereignisse(anzahl: int, *, zeitpunkt: datetime | None = None) -> None:
    """Registriert `anzahl` (>= 0, sonst No-Op) neu erzeugte Überwachungs-
    Ereignisse zum selben Zeitpunkt (Default: jetzt) für die
    Tages-Kennzahl (AC7)."""
    if anzahl <= 0:
        return
    ts = zeitpunkt or datetime.now(UTC)
    with _lock:
        _registrierungen.extend([ts] * anzahl)


def berechne_tageskennzahl(*, tag: date | None = None) -> MonitoringTagesKennzahl:
    """AC7: zählt die für `tag` (Default: heute, UTC) registrierten
    Ereignisse und liefert `zu_sensibel=True`, sobald die Anzahl den
    konfigurierten Schwellwert (Default 10, ohne Codeänderung über
    `DEPOT_UEBERWACHUNG_EREIGNISSE_PRO_TAG_SCHWELLWERT` überschreibbar)
    STRIKT überschreitet."""
    zieltag = tag or datetime.now(UTC).date()
    schwellwert = get_settings().depot_ueberwachung_ereignisse_pro_tag_schwellwert
    with _lock:
        anzahl = sum(1 for zeitpunkt in _registrierungen if _als_utc(zeitpunkt).date() == zieltag)
    return MonitoringTagesKennzahl(
        datum=zieltag,
        ereignisse_pro_tag=anzahl,
        schwellwert=schwellwert,
        zu_sensibel=anzahl > schwellwert,
    )


def _als_utc(zeitpunkt: datetime) -> datetime:
    """Normalisiert auf UTC-aware (analog
    `app.domain.depot_ueberwachung.frische._als_utc_aware`)."""
    if zeitpunkt.tzinfo is None:
        return zeitpunkt.replace(tzinfo=UTC)
    return zeitpunkt.astimezone(UTC)


def reset_fuer_tests() -> None:
    """Nur für Tests: leert die Registrierungs-Historie zwischen
    Testfällen, damit Assertions nicht von zuvor gelaufenen Tests
    beeinflusst werden."""
    with _lock:
        _registrierungen.clear()


__all__ = ["berechne_tageskennzahl", "registriere_ereignisse", "reset_fuer_tests"]
