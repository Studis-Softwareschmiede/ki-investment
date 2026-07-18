"""Halluzinations-KPI & Kill (AC8, AC9, Spec `docs/specs/llm-grounding.md`,
BR-006, C-008 Monitoring).

Misst laufend die Quote „Analysen mit Faktenabweichung" (verworfene /
geprüfte Analysen) aus den Ergebnissen des deterministischen Cross-Checks
(S-013, `app.adapters.llm.cross_check.pruefe_cross_check`, AC4) und nimmt
das LLM aus der Entscheidungskette, sobald die Quote den konfigurierten
Schwellwert STRIKT überschreitet (Default 2 %, `app.config`, AC9).

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4: "core/ ...
kill_switch, heartbeat, drawdown_monitor, secrets, logging, errors" —
dieselbe Kategorie deterministischer Betriebszustand, kein I/O, kein LLM).

Cold-Start-Hinweis (analog zu S-014, `app.domain.no_evidence_no_trade`):
dieses Modul ist eigenständig, deterministisch und vollständig getestet,
wird aber (noch) von keinem existierenden Produktionscode aufgerufen — der
künftige Buy-Pfad-Orchestrator (`orchestration/buy_pipeline.py`, noch nicht
gebaut) registriert je Analyse das `CrossCheckErgebnis` über
`registriere_ergebnis()` und fragt vor jeder Verwendung eines LLM-Scores
`ist_llm_aktiv()` ab (architecture.md §6, BR-006: "AKTIV →
(Halluzinations-KPI > 2 %) → DEAKTIVIERT (LLM aus Entscheidungskette,
Analyse fällt auf No-Evidence-No-Trade zurück) → manueller Reset"). Bewusst
KEINE Änderung an `app.adapters.llm.cross_check` in dieser Story: dessen
öffentlicher Vertrag (S-013, bereits reviewt/getestet) bleibt unangetastet;
die Registrierung ist Aufgabe des (künftigen) Aufrufers.

Zeitfenster (Vertrag "quote = verworfene_analysen / geprüfte_analysen über
ein Zeitfenster"): ohne explizit übergebenes `seit` misst `berechne_kpi()`
kumulativ seit dem letzten Reset (App-Start oder `reaktiviere_llm()`) —
Aufrufer können mit `seit` ein engeres Zeitfenster erzwingen.

Kill-Latch: einmal `deaktiviert`, bleibt die LLM-Kette deaktiviert — auch
wenn nachfolgend registrierte Analysen die Quote rechnerisch wieder unter
den Schwellwert drücken würden —, bis `reaktiviere_llm()` explizit (manuell,
"bis die Ursache geklärt ist", BR-006) aufgerufen wird. Kein automatisches
Selbst-Reaktivieren. `reaktiviere_llm()` leert zugleich die
Registrierungs-Historie: der manuelle Reset startet ein frisches
Beobachtungsfenster, statt sofort wieder gegen die (mutmaßlich behobene)
Altlast zu alarmieren.

Jeder Alarm/Kill-Übergang (`aktiv` → `deaktiviert`) wird auditiert
(AC10-Geist, `app.core.audit_log`, neuer `ProtokollGrund`-Wert
`halluzinations_kpi_alarm`) — genau einmal je Übergang, nicht bei jedem
`berechne_kpi()`-Aufruf während die Kette bereits deaktiviert ist.

**Update S-026 (`docs/specs/betriebssicherung.md` AC8):** Betriebssicherung
konsumiert diesen Halluzinations-KPI-Alarm — die KPI-Berechnung selbst
bleibt unverändert Sache dieses Moduls (llm-grounding AC8/AC9, s.o.), aber
derselbe Alarm-Übergang (`aktiv` → `deaktiviert`) meldet zusätzlich (genau
einmal je Übergang, analog zum Audit-Eintrag) einen
`Alert(typ="halluzination", schwere="critical")` über
`app.core.alerts.melde()` — die Andockstelle des Benachrichtigungskanals
(AC7).

**Update S-068** (`docs/specs/frontend-cockpit.md` AC8): ergänzt
`aktueller_kpi()` — eine reine, seiteneffektfreie Zustandsabfrage für
read-only Konsumenten (Betriebs-Cockpit System-Status): berechnet dieselbe
Quote über die registrierten Cross-Check-Ergebnisse und liest den
aktuellen Kill-Latch-Zustand, löst aber NIE selbst einen Alarm-Übergang
(Audit-Eintrag/`Alert`/Latch-Wechsel) aus — ein Status-Seiten-Aufruf darf
den Halluzinations-Kill-Latch nicht als Nebenwirkung verändern. Das
bestehende `berechne_kpi()` bleibt unverändert die einzige Stelle, die
tatsächlich einen Alarm-Übergang auslöst.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from app.config import get_settings
from app.contracts.betriebssicherung import Alert
from app.contracts.llm_grounding import (
    CrossCheckErgebnis,
    HalluzinationsKpiErgebnis,
    LlmKettenStatus,
    ProtokollEintrag,
)
from app.core.alerts import melde
from app.core.audit_log import protokolliere

_lock = threading.Lock()
#: (Zeitpunkt der Registrierung, war_verworfen) je registriertem
#: Cross-Check-Ergebnis.
_registrierungen: list[tuple[datetime, bool]] = []
_status: LlmKettenStatus = "aktiv"


def registriere_ergebnis(
    ergebnis: CrossCheckErgebnis, *, zeitpunkt: datetime | None = None
) -> None:
    """Registriert das Ergebnis EINES deterministischen Cross-Checks (AC4)
    für die laufende Halluzinations-KPI-Berechnung (AC8). Wird vom
    (künftigen) Aufrufer unmittelbar nach
    `app.adapters.llm.cross_check.pruefe_cross_check` aufgerufen — sowohl
    `status == "geerdet"` als auch `status == "verworfen"` zählen zu
    `geprueft`, nur `"verworfen"` zählt zusätzlich zu `verworfen`."""
    ts = zeitpunkt or datetime.now(UTC)
    with _lock:
        _registrierungen.append((ts, ergebnis.status == "verworfen"))


def _zaehle_relevante_unlocked(seit: datetime | None) -> tuple[int, int, float]:
    """NUR unter `_lock` aufrufen: `(geprueft, verworfen, quote)` über alle
    seit `seit` registrierten Cross-Check-Ergebnisse. Gemeinsamer Zähl-Kern
    von `berechne_kpi()` UND dem seiteneffektfreien `aktueller_kpi()`
    (S-068) — reine Arithmetik, kein Alarm-/Latch-Zustand."""
    relevant = [
        war_verworfen
        for zeitpunkt, war_verworfen in _registrierungen
        if seit is None or zeitpunkt >= seit
    ]
    geprueft = len(relevant)
    verworfen = sum(relevant)
    quote = (verworfen / geprueft) if geprueft else 0.0
    return geprueft, verworfen, quote


def berechne_kpi(*, seit: datetime | None = None) -> HalluzinationsKpiErgebnis:
    """Berechnet die Halluzinations-Quote (AC8) über alle seit `seit`
    registrierten Cross-Check-Ergebnisse (Default: die gesamte Historie seit
    dem letzten Reset/App-Start — kein Zeitfenster übergeben). Ohne
    registrierte Analysen ist die Quote `0.0` (kein Alarm — eine leere
    Stichprobe belegt keine Faktenabweichung).

    Übersteigt die Quote den konfigurierten Schwellwert (Default 2 %, AC9)
    STRIKT, wechselt die LLM-Kette einmalig von `aktiv` auf `deaktiviert`
    (Kill-Latch, s. Modul-Docstring), der Alarm wird auditiert (AC10-Geist)
    und zusätzlich als `Alert(typ="halluzination")` über den
    Benachrichtigungskanal gemeldet (`docs/specs/betriebssicherung.md`
    AC8, S-026). Eine Quote GENAU auf dem Schwellwert löst KEINEN Alarm aus
    (Edge-Case der Spec)."""
    global _status
    schwellwert = get_settings().halluzinations_kpi_schwellwert
    alarm_zeitpunkt = datetime.now(UTC)

    with _lock:
        geprueft, verworfen, quote = _zaehle_relevante_unlocked(seit)
        alarm = quote > schwellwert

        neu_ausgeloest = alarm and _status == "aktiv"
        if neu_ausgeloest:
            _status = "deaktiviert"
        aktueller_status = _status

    if neu_ausgeloest:
        eintrag = ProtokollEintrag(
            zeitpunkt=alarm_zeitpunkt,
            grund="halluzinations_kpi_alarm",
            kennzahl_typ=None,
            quellen_id=None,
            detail=(
                f"Halluzinations-Quote {quote:.4f} > Schwellwert {schwellwert:.4f} "
                f"({verworfen}/{geprueft} verworfene Analysen) — LLM aus der "
                "Entscheidungskette genommen (BR-006), bis manuell reaktiviert."
            ),
        )
        protokolliere(eintrag)
        melde(
            Alert(
                typ="halluzination",
                schwere="critical",
                nachricht=(
                    f"Halluzinations-Quote {quote:.2%} überschreitet die Schwelle "
                    f"{schwellwert:.2%} ({verworfen}/{geprueft} verworfene Analysen) — "
                    "LLM aus der Entscheidungskette genommen (betriebssicherung#AC8)."
                ),
                zeitstempel=alarm_zeitpunkt,
            )
        )

    return HalluzinationsKpiErgebnis(
        geprueft=geprueft,
        verworfen=verworfen,
        quote=quote,
        schwellwert=schwellwert,
        alarm=alarm,
        llm_status=aktueller_status,
    )


def aktueller_kpi(*, seit: datetime | None = None) -> HalluzinationsKpiErgebnis:
    """Reine Zustandsabfrage (S-068, `docs/specs/frontend-cockpit.md` AC8)
    — Gegenstück zu `berechne_kpi()` für read-only Konsumenten (Betriebs-
    Cockpit System-Status): berechnet dieselbe Quote über die registrierten
    Cross-Check-Ergebnisse und liest den AKTUELLEN Kill-Latch-Zustand
    (`aktiv`/`deaktiviert`), löst aber NIE selbst einen Alarm-Übergang aus
    (kein Audit-Eintrag, kein `Alert`, keine Latch-Änderung) — ein
    Status-Seiten-Aufruf darf den Halluzinations-Kill-Latch nicht als
    Nebenwirkung verändern. `alarm` spiegelt hier nur die rein informative
    Aussage „Quote überschreitet aktuell den Schwellwert" — sie kann `True`
    sein, während `llm_status` noch `"aktiv"` bleibt, weil DIESER Read den
    Übergang nicht auslöst (für den tatsächlichen Alarm-Übergang bleibt
    ausschliesslich `berechne_kpi()` zuständig)."""
    schwellwert = get_settings().halluzinations_kpi_schwellwert
    with _lock:
        geprueft, verworfen, quote = _zaehle_relevante_unlocked(seit)
        aktueller_status = _status

    return HalluzinationsKpiErgebnis(
        geprueft=geprueft,
        verworfen=verworfen,
        quote=quote,
        schwellwert=schwellwert,
        alarm=quote > schwellwert,
        llm_status=aktueller_status,
    )


def ist_llm_aktiv() -> bool:
    """Reine Zustandsabfrage (AC9): `True`, solange kein Halluzinations-
    KPI-Alarm ausgelöst wurde bzw. bis zum manuellen Reset. Berechnet die
    Quote NICHT neu (dafür `berechne_kpi()`) — der (künftige)
    Entscheidungsketten-Konsument fragt hierüber ab, ob eine LLM-basierte
    Analyse noch verwendet werden darf."""
    with _lock:
        return _status == "aktiv"


def reaktiviere_llm() -> None:
    """Manueller Reset (BR-006: "... → manueller Reset", "bis die Ursache
    geklärt ist") — schaltet die LLM-Kette wieder auf `aktiv` und leert die
    Registrierungs-Historie, damit ein frisches Beobachtungsfenster beginnt
    (s. Modul-Docstring "Kill-Latch")."""
    global _status
    with _lock:
        _status = "aktiv"
        _registrierungen.clear()


def reset_fuer_tests() -> None:
    """Nur für Tests: setzt Registrierungs-Historie UND Status vollständig
    zurück, damit Assertions nicht von zuvor gelaufenen Tests beeinflusst
    werden."""
    global _status
    with _lock:
        _registrierungen.clear()
        _status = "aktiv"
