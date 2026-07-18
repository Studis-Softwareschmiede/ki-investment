"""Portfolioweite Drawdown-Überwachung + automatischer Kill-Switch-Trigger
(Story S-025, AC2, AC5, Spec `docs/specs/betriebssicherung.md`).

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4: "core/
QUERSCHNITT: kill_switch, heartbeat, drawdown_monitor, secrets, logging,
errors"), analog zu `app.core.kill_switch`/`app.core.heartbeat` — kein I/O,
kein DB-Zugriff in dieser Story.

**Input (Verträge, AC5):** "Depot-Stand/Equity-Kurve aus dem Depotmodul".
Das Depotmodul existiert in dieser Codebasis noch nicht (Cold-Start,
Nicht-Ziel dieser Story, Spec-Abhängigkeiten). `aktualisiere_
equity_stand()` ist die Andockstelle, die das künftige Depotmodul bei
jeder Equity-Aktualisierung aufruft; dieses Modul hält intern nur den
laufenden Höchststand (High-Water-Mark) + den zuletzt gemeldeten Stand —
keine vollständige Zeitreihe (für die reine Drawdown-Berechnung genügt der
Höchststand, eine vollständige Historie ist Aufgabe des Depotmoduls
selbst).

**Zwei unabhängig konfigurierbare Schwellen (AC5):**
`drawdown_alert_schwelle` (nur Alert) und `drawdown_kill_schwelle`
(zusätzlich Kill-Switch-Trigger, AC2) — beide in `app.config.Settings`,
provisorische Defaults dort dokumentiert (AC2: "Default provisorisch/offen
— in der Umsetzung festzulegen"). Beide Vergleiche sind STRIKT (`>`), analog
zum Halluzinations-KPI-Schwellwertvergleich in
`app.core.hallucination_kpi` (Edge-Case „genau auf der Schwelle → kein
Alarm").

**Auto-Trigger (AC2, docks an S-007 an):** überschreitet der Drawdown
`drawdown_kill_schwelle`, ruft `pruefe_drawdown()` das BESTEHENDE
`app.core.kill_switch.ausloesen()` mit Quelle `"drawdown"` auf — keine
neue Zustandsmaschine, keine Änderung der Kill-Switch-Semantik (dessen
Idempotenz deckt wiederholte Drawdown-Checks im bereits `angehalten`-
Zustand bereits ab).

**Überwachungslücke = Cold-Start (Edge-Case der Spec):** "Fehlt der
Depot-Stand für die Drawdown-Berechnung, wird dies als Überwachungslücke
gemeldet, nicht stillschweigend als 'kein Drawdown' gewertet." Das deckt
GENAU den Cold-Start ohne Baseline ab (estimate_note: "kein Drawdown-
Fehlalarm" bei noch leerer Equity-Kurve): ohne jemals gemeldeten
Equity-Stand berechnet `pruefe_drawdown()` KEINEN Drawdown-Prozentsatz
(kein impliziter Wert wie `0` oder `100%`), sondern meldet einen `Alert`
vom Typ `"drawdown"` mit `schwere="warn"` und setzt
`DrawdownStatus.ueberwachungsluecke=True` — OHNE den Kill-Switch
auszulösen (kein Fehlalarm bei leerer Kurve, aber auch kein
stillschweigendes Verschweigen der Lücke).

**Update S-068** (`docs/specs/frontend-cockpit.md` AC8): ergänzt `status()`
— eine reine, seiteneffektfreie Zustandsabfrage für read-only Konsumenten
(Betriebs-Cockpit System-Status). Das bestehende `pruefe_drawdown()` bleibt
unverändert die einzige Stelle, die tatsächlich alarmiert/den Kill-Switch
auslöst.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from decimal import Decimal

from app.config import get_settings
from app.contracts.betriebssicherung import Alert, DrawdownStatus, KillSwitchAusloeser
from app.core import kill_switch
from app.core.alerts import melde

_lock = threading.Lock()
_hoechststand: Decimal | None = None
_aktueller_stand: Decimal | None = None


def aktualisiere_equity_stand(equity_wert: Decimal, zeitstempel: datetime) -> None:
    """Wird vom (künftigen) Depotmodul bei jeder Equity-Aktualisierung
    aufgerufen (AC5, Input "Depot-Stand/Equity-Kurve aus dem Depotmodul").
    Aktualisiert den zuletzt gemeldeten Stand sowie — falls überschritten —
    den laufenden Höchststand (High-Water-Mark). `zeitstempel` wird
    entgegengenommen (Vertragstreue zur Equity-Kurve), aber für die reine
    Höchststand-Berechnung nicht ausgewertet — eine chronologische
    Zeitreihen-Validierung ist Aufgabe des (künftigen) Depotmoduls."""
    global _hoechststand, _aktueller_stand
    with _lock:
        _aktueller_stand = equity_wert
        if _hoechststand is None or equity_wert > _hoechststand:
            _hoechststand = equity_wert


def _lese_drawdown_status_unlocked(
    aktueller_stand: Decimal | None, hoechststand: Decimal | None
) -> DrawdownStatus:
    """NUR mit bereits unter `_lock` gelesenen Werten aufrufen: liefert den
    reinen Zustand (Cold-Start-Erkennung + `drawdown_pct`-Formel), OHNE
    einen `Alert` zu melden oder den Kill-Switch auszulösen — `kill_
    ausgeloest` ist in diesem Kern deshalb immer `False`. Gemeinsamer Kern
    von `pruefe_drawdown()` (meldet zusätzlich Alerts/Kill-Switch on top)
    UND dem seiteneffektfreien `status()` (S-068) — analog zum bereits
    bestehenden Muster `_zaehle_relevante_unlocked()` in
    `app.core.hallucination_kpi`."""
    if aktueller_stand is None or hoechststand is None:
        return DrawdownStatus(
            aktueller_stand=None,
            hoechststand=None,
            drawdown_pct=None,
            ueberwachungsluecke=True,
            kill_ausgeloest=False,
        )

    drawdown_pct = (
        (hoechststand - aktueller_stand) / hoechststand if hoechststand > 0 else Decimal(0)
    )
    return DrawdownStatus(
        aktueller_stand=aktueller_stand,
        hoechststand=hoechststand,
        drawdown_pct=drawdown_pct,
        ueberwachungsluecke=False,
        kill_ausgeloest=False,
    )


def pruefe_drawdown(*, jetzt: datetime | None = None) -> DrawdownStatus:
    """Prüft den aktuellen Drawdown gegen die zwei unabhängig
    konfigurierbaren Schwellen (AC5) und löst bei Überschreiten der
    Kill-Schwelle automatisch den Kill-Switch aus (AC2). Fehlt ein
    gemeldeter Depot-Stand (Cold-Start/Überwachungslücke, Edge-Case der
    Spec), wird dies als `Alert` gemeldet, OHNE einen Drawdown-Wert zu
    unterstellen und OHNE den Kill-Switch auszulösen."""
    settings = get_settings()
    ts = jetzt or datetime.now(UTC)

    with _lock:
        aktueller_stand = _aktueller_stand
        hoechststand = _hoechststand

    basis_status = _lese_drawdown_status_unlocked(aktueller_stand, hoechststand)

    if basis_status.ueberwachungsluecke:
        melde(
            Alert(
                typ="drawdown",
                schwere="warn",
                nachricht=(
                    "Überwachungslücke: kein Depot-Stand für die Drawdown-Berechnung "
                    "vorhanden (Cold-Start ohne Baseline oder ausgebliebene "
                    "Equity-Aktualisierung)."
                ),
                zeitstempel=ts,
            )
        )
        return basis_status

    drawdown_pct = basis_status.drawdown_pct
    assert drawdown_pct is not None  # Cold-Start bereits oben behandelt

    kill_ausgeloest = False
    if drawdown_pct > Decimal(str(settings.drawdown_kill_schwelle)):
        melde(
            Alert(
                typ="drawdown",
                schwere="critical",
                nachricht=(
                    f"Portfolioweiter Drawdown {drawdown_pct:.2%} überschreitet die "
                    f"Kill-Schwelle {settings.drawdown_kill_schwelle:.2%} — Kill-Switch "
                    "wird ausgelöst."
                ),
                zeitstempel=ts,
            )
        )
        kill_switch.ausloesen(
            KillSwitchAusloeser(
                quelle="drawdown",
                zeitstempel=ts,
                grund=(
                    f"Portfolioweiter Drawdown {drawdown_pct:.4f} > Kill-Schwelle "
                    f"{settings.drawdown_kill_schwelle:.4f}"
                ),
                kennwert=drawdown_pct,
            )
        )
        kill_ausgeloest = True
    elif drawdown_pct > Decimal(str(settings.drawdown_alert_schwelle)):
        melde(
            Alert(
                typ="drawdown",
                schwere="warn",
                nachricht=(
                    f"Portfolioweiter Drawdown {drawdown_pct:.2%} überschreitet die "
                    f"Alert-Schwelle {settings.drawdown_alert_schwelle:.2%}."
                ),
                zeitstempel=ts,
            )
        )

    return DrawdownStatus(
        aktueller_stand=basis_status.aktueller_stand,
        hoechststand=basis_status.hoechststand,
        drawdown_pct=drawdown_pct,
        ueberwachungsluecke=False,
        kill_ausgeloest=kill_ausgeloest,
    )


def status() -> DrawdownStatus:
    """Reine Zustandsabfrage (S-068, `docs/specs/frontend-cockpit.md` AC8)
    — Gegenstück zu `pruefe_drawdown()` für read-only Konsumenten (Betriebs-
    Cockpit System-Status): nutzt denselben Kern (`_lese_drawdown_status_
    unlocked`, Cold-Start-Erkennung + `drawdown_pct`-Formel) wie
    `pruefe_drawdown()`, löst aber NIE einen `Alert` oder den Kill-Switch
    aus (kein `melde()`-/`kill_switch.ausloesen()`-Aufruf) — ein reiner
    Status-Read darf keine Nebenwirkung auf den Betriebszustand haben.
    `kill_ausgeloest` ist bei diesem Getter deshalb immer `False` (das Feld
    beschreibt nur, ob DIESER Aufruf ausgelöst hat, nicht den laufenden
    Kill-Switch-Zustand selbst — dafür `app.core.kill_switch.status()`)."""
    with _lock:
        aktueller_stand = _aktueller_stand
        hoechststand = _hoechststand

    return _lese_drawdown_status_unlocked(aktueller_stand, hoechststand)


def reset_fuer_tests() -> None:
    """Nur für Tests: setzt Höchststand UND aktuellen Stand vollständig
    zurück, damit Assertions nicht von zuvor gelaufenen Tests beeinflusst
    werden."""
    global _hoechststand, _aktueller_stand
    with _lock:
        _hoechststand = None
        _aktueller_stand = None
