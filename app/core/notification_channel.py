"""Benachrichtigungskanal (Story S-026, AC7 + AC10, Spec
`docs/specs/betriebssicherung.md`).

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4), analog
zu `app.core.alerts` (der internen Alert-Sammlung + Callback-Andockstelle,
S-025) — kein I/O, keine externe Netzwerkverbindung in dieser Story.

**AC7 (Benachrichtigungskanal selbst):** `app.core.alerts` bietet seit
S-025 nur die Andockstelle (`registriere_callback()`); AC7 selbst — „Alle
sicherheitsrelevanten Ereignisse ... werden über einen Benachrichtigungs-
kanal gemeldet; im Paper-MVP sind diese Benachrichtigungen informativ" —
war dort explizit Nicht-Ziel und wird HIER realisiert: `registriere()`
hängt sich als Callback bei `app.core.alerts` ein und „versendet" jeden
gemeldeten `Alert` über eine injizierbare `VersandFunktion`. Kein
konkreter externer Dienst (Telegram/E-Mail/Webhook) ist Teil dieser
Spec/dieses MVP — der Default-Versand (`_standard_versand`) ist daher eine
dedizierte, strukturierte Logzeile (informativ, „kein Eingriff/keine
Bestätigungspflicht erforderlich", AC7). Ein künftiger echter externer
Kanal kann `registriere(versand=...)` mit einer eigenen Versandfunktion
aufrufen, ohne dieses Modul zu ändern.

**AC10 (Kanal nicht erreichbar):** Wirft die Versandfunktion (z. B. ein
künftiger externer Dienst ist nicht erreichbar), wird der betroffene
`Alert` NICHT verworfen, sondern in einer Zustell-Warteschlange
vorgemerkt (`ausstehende_zustellungen()`) und beim nächsten
`sende_ausstehende()`-Aufruf erneut zugestellt — „persistent" bedeutet
hier (Cold-Start, analog zu `app.core.kill_switch`/`app.core.heartbeat`/
`app.core.alerts`, die `docs/data-model.md` §7 `kill_switch_status`/
`heartbeat`/`alert_log` ebenfalls noch nicht in die DB spiegeln): die
Warteschlange übersteht wiederholte `melde()`-Aufrufe innerhalb des
laufenden Prozesses, nicht zwingend einen Prozess-Neustart — eine
DB-gestützte Persistenz ist Sache einer künftigen Story, sobald diese
Tabellen migriert werden. Kill-Switch/Heartbeat/Drawdown bleiben davon
unabhängig funktionsfähig, weil `app.core.alerts.melde()` bereits JEDEN
Callback-Fehler abfängt (NFR „Verfügbarkeit") — `_zustellen()` wirft daher
selbst nie, unabhängig vom Versand-Ergebnis.

Cold-Start-Hinweis: kein bestehender App-Bootstrap ruft `registriere()`
bislang auf (kein Scheduler/App-Start-Modul existiert, analog zu allen
anderen `app.core.*`-Betriebssicherungs-Modulen dieses Features) — ein
künftiger App-Bootstrap tut dies beim Start.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable

from app.contracts.betriebssicherung import Alert
from app.core.alerts import registriere_callback

_logger = logging.getLogger("notification.channel")

#: Versandfunktion (AC7): nimmt einen `Alert` entgegen und „versendet" ihn.
#: Wirft sie, gilt der Kanal für DIESEN Alert als nicht erreichbar (AC10).
VersandFunktion = Callable[[Alert], None]


def _standard_versand(alert: Alert) -> None:
    """Paper-MVP-Default-Versand (AC7): eine rein informative, strukturierte
    Logzeile — kein externer Dienst angebunden (kein konkreter Kanal in der
    Spec benannt), keine Bestätigungspflicht/kein Eingriff nötig."""
    _logger.info(json.dumps(alert.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))


_lock = threading.Lock()
_versand: VersandFunktion = _standard_versand
_registriert = False
_ausstehend: list[Alert] = []


def _zustellen(alert: Alert) -> None:
    """Callback-Ziel für `app.core.alerts.registriere_callback()` (AC7):
    wird bei jedem `melde()`-Aufruf synchron mit dem gemeldeten `Alert`
    aufgerufen. Schlägt der Versand fehl (Kanal nicht erreichbar), wird der
    Alert persistent vorgemerkt (AC10) statt verworfen — diese Funktion
    wirft selbst NIE, damit ein fehlschlagender Kanal weder die
    Alert-Historie noch andere Callbacks noch Kill-Switch/Heartbeat/
    Drawdown blockiert (NFR „Verfügbarkeit")."""
    with _lock:
        versand = _versand
    try:
        versand(alert)
    except Exception:
        _logger.exception(
            "Benachrichtigungskanal nicht erreichbar — Alert wird persistent "
            "vorgemerkt und später zugestellt (AC10)."
        )
        with _lock:
            _ausstehend.append(alert)


def registriere(versand: VersandFunktion | None = None) -> None:
    """Registriert den Benachrichtigungskanal als Callback bei
    `app.core.alerts` (AC7). `versand` ist injizierbar (Default:
    `_standard_versand`) — ein künftiger echter Kanal übergibt hier seine
    eigene Versandfunktion, ohne dieses Modul zu ändern. Aktualisiert die
    Versandfunktion auch bei einem wiederholten Aufruf, registriert den
    Callback selbst aber NICHT mehrfach bei `app.core.alerts` (Idempotenz —
    verhindert doppelte Zustellung desselben Alerts)."""
    global _versand, _registriert
    with _lock:
        if versand is not None:
            _versand = versand
        bereits_registriert = _registriert
        _registriert = True
    if not bereits_registriert:
        registriere_callback(_zustellen)


def sende_ausstehende() -> tuple[Alert, ...]:
    """Versucht, alle aktuell vorgemerkten Alerts erneut zuzustellen (AC10:
    „beim nächsten erreichbaren Zeitpunkt zugestellt"). Liefert die bei
    DIESEM Aufruf erfolgreich zugestellten Alerts; weiterhin
    fehlschlagende Alerts bleiben in der Warteschlange (der Kanal gilt
    dann weiterhin als nicht erreichbar)."""
    with _lock:
        kandidaten = list(_ausstehend)
        versand = _versand

    zugestellt: list[Alert] = []
    weiterhin_ausstehend: list[Alert] = []
    for alert in kandidaten:
        try:
            versand(alert)
        except Exception:
            weiterhin_ausstehend.append(alert)
        else:
            zugestellt.append(alert)

    with _lock:
        # Nur die in DIESEM Lauf verarbeiteten Kandidaten ersetzen —
        # zwischenzeitlich (nebenläufig) neu hinzugekommene bleiben erhalten.
        neu_hinzugekommen = _ausstehend[len(kandidaten) :]
        _ausstehend[:] = weiterhin_ausstehend + neu_hinzugekommen

    return tuple(zugestellt)


def ausstehende_zustellungen() -> tuple[Alert, ...]:
    """Liefert eine unveränderliche Kopie aller aktuell nicht zugestellten
    Alerts (Inspektion, z. B. in Tests)."""
    with _lock:
        return tuple(_ausstehend)


def reset_fuer_tests() -> None:
    """Nur für Tests: setzt Versandfunktion, Registrierungs-Flag und
    Zustell-Warteschlange vollständig zurück. Deregistriert den Callback
    NICHT bei `app.core.alerts` — dessen eigener `reset_fuer_tests()` leert
    die dortige Callback-Liste bereits vollständig; Tests müssen daher
    `alerts.reset_fuer_tests()` VOR einem erneuten `registriere()`-Aufruf
    nutzen, damit der Callback dort tatsächlich neu eingehängt wird."""
    global _versand, _registriert
    with _lock:
        _versand = _standard_versand
        _registriert = False
        _ausstehend.clear()
