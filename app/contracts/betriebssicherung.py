"""Modul-Verträge Kill-Switch «flatten & halt» + Secret-Store (Story S-007
AC1/AC3/AC11, Story S-008 AC6, Spec `docs/specs/betriebssicherung.md`).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet die
Verträge aus `docs/specs/betriebssicherung.md` ("Verträge") ab, soweit sie
diese Stories betreffen:

- `KillSwitchAusloeser` — der Auslöser-Input (`{quelle, zeitstempel, grund,
  kennwert?}`). `quelle` ist bereits das volle Vertrags-`Literal`
  (`manuell|drawdown|heartbeat|extern`), obwohl diese Story nur den
  manuellen Pfad (AC1) tatsächlich auslöst — automatische Trigger (AC2
  Drawdown, AC4 Heartbeat, AC5-Alert) sind spätere Stories, die denselben
  Vertrag ohne Änderung nutzen können (Andock-Vorgabe im Board-Item).
- `Betriebszustand` — die zwei von der Spec benannten Zustände (AC3):
  `normal` / `angehalten`.
- `KillSwitchStatus` — der aktuelle, abfragbare Betriebszustand inkl. der
  zuletzt wirksamen Auslöse-Metadaten (`quelle`, `grund`, `ausgeloest_am`) —
  fachlich 1:1 zu `docs/data-model.md` §7 `kill_switch_status`
  (`active`/`reason`/`activated_at`), auch wenn diese Story den Zustand
  noch nicht in der DB persistiert (Cold-Start, siehe
  `app.core.kill_switch`-Modul-Docstring).
- `KillSwitchEreignis` — der unveränderliche Protokolleintrag einer
  Auslösung (AC11: "Jede Auslösung ... wird unveränderlich mit Auslöser,
  Zeitpunkt und Grund protokolliert"). Bewusst ein eigener, schlanker
  Vertrag statt Wiederverwendung von `app.contracts.llm_grounding.
  ProtokollEintrag` — dessen `ProtokollGrund`-Literal und Feldnamen
  (`kennzahl_typ`, `quellen_id`) sind an die llm-grounding-Spec gebunden und
  passen fachlich nicht zum Kill-Switch-Auslöser-Vertrag dieser Spec.
- `Umgebung` + `SecretStoreZugang` (Story S-008, AC6) — der Secret-Store-
  Vertrag ("Secrets-Zugriff: über den Secret-Store aufgelöst, getrennt nach
  Umgebung `paper` / `live`; nie im Klartext im Code/Repo"). Ein
  `SecretStoreZugang` bündelt die für EINEN Dienst in GENAU EINER Umgebung
  aufgelösten Zugangsdaten; `app.core.secrets.resolve_secret_store_zugang`
  ist die einzige Stelle, die ihn erzeugt (siehe dortiger Modul-Docstring
  für die strikte Paper/Live-Trennung der zugrundeliegenden Env-Variablen).
  Noch kein konkreter Dienst (z. B. ein Broker aus
  `docs/specs/ausfuehrung-paper.md`) konsumiert diesen Vertrag in dieser
  Story — der Broker-Adapter selbst ist Nicht-Ziel (Board-Item-Scope, siehe
  dort: "Live-Betrieb ist Nicht-Ziel des MVP").

Story S-025 (AC2, AC4, AC5) ergänzt die zuvor bewusst ausgesparten
Auto-Trigger-Verträge, ohne die obigen S-007/S-008-Verträge zu ändern:

- `Alert` — der Spec-Vertrag "Alert (Output an Benachrichtigungskanal):
  `{typ, schwere, nachricht, zeitstempel}`". `typ` trägt bereits das volle
  Vertrags-`Literal` (`kill|heartbeat|drawdown|quellenausfall|
  halluzination`), obwohl diese Story nur `heartbeat`/`drawdown` tatsächlich
  erzeugt — `quellenausfall` (AC9, S-014-Anschluss) und `halluzination`
  (AC8, bereits `app.core.hallucination_kpi`) sind spätere/parallele
  Konsumenten desselben Vertrags. `schwere` folgt dem bereits in
  `docs/data-model.md` §7 `alert_log.severity` festgelegten Vokabular
  (`info|warn|critical`) — kein neues Vokabular erfunden. AC7
  (Benachrichtigungskanal selbst) bleibt Nicht-Ziel dieser Story (S-026);
  `Alert` ist der interne, testbare Vertrag, an den S-026 andockt
  (`app.core.alerts`).
- `HeartbeatEintrag` — der Spec-Vertrag "Heartbeat (je Modul):
  `{modul_id, letzter_ping_zeitstempel, intervall_soll}`; Ausfall wenn
  `now − letzter_ping > intervall_soll`" (AC4). Trägt bewusst NUR diese drei
  Vertragsfelder — die zusätzliche, pro Modul konfigurierbare Kritikalität
  ("je nach Kritikalität/Konfiguration der Kill-Switch ausgelöst", AC4) ist
  kein Teil dieses Austausch-Vertrags, sondern interner Registrierungs-
  Zustand von `app.core.heartbeat` (siehe dortiger Modul-Docstring) — kein
  Gold-Plating über den wörtlichen Spec-Vertrag hinaus.
- `DrawdownStatus` — Lesemodell von `app.core.drawdown_monitor.
  pruefe_drawdown()` (AC2, AC5): aktueller Stand, laufender Höchststand
  (High-Water-Mark) und daraus abgeleiteter Drawdown in Prozent, plus die
  zwei Ergebnis-Flags `ueberwachungsluecke` (Edge-Case „fehlender
  Depot-Stand" — Verträge/Edge-Cases der Spec: wird als Lücke gemeldet,
  NICHT stillschweigend als „kein Drawdown" gewertet, deckt auch den
  Cold-Start ohne Baseline ab) und `kill_ausgeloest` (AC2, dieser Aufruf hat
  den bestehenden `app.core.kill_switch.ausloesen()` getriggert). Kein
  eigener Vertrag für den Equity-Kurve-Input selbst (Verträge: "Input:
  Depot-Stand/Equity-Kurve aus dem Depotmodul") — das Depotmodul existiert
  noch nicht (Cold-Start, Nicht-Ziel dieser Story); `aktualisiere_
  equity_stand()` in `app.core.drawdown_monitor` nimmt bewusst nur
  `Decimal` + `datetime` entgegen statt eines eigenen DTO, das mangels
  Depotmodul-Gegenstück nicht validierbar wäre.

Nicht Teil dieser Story (Board-Item-Scope): kein Alert-Benachrichtigungs-
kanal selbst (AC7, S-026 — `Alert` ist nur der interne Vertrag, an den der
künftige Kanal andockt); kein Depotmodul-Equity-Kurve-Vertrag (existiert
noch nicht).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Kill-Switch-Auslöser-Quelle (Verträge, Spec `betriebssicherung`) — nur
#: `"manuell"` wird von dieser Story tatsächlich ausgelöst (AC1); die
#: übrigen Werte docken künftige automatische Trigger-Stories an, ohne
#: diesen Vertrag zu ändern.
KillSwitchQuelle = Literal["manuell", "drawdown", "heartbeat", "extern"]

#: Betriebszustand (AC3) — die Spec benennt genau diese zwei extern
#: sichtbaren Zustände ("angehalten" als Ziel der Auslösung, "normal" als
#: Rückkehr-Ziel der expliziten manuellen Freigabe).
Betriebszustand = Literal["normal", "angehalten"]


class KillSwitchAusloeser(BaseModel):
    """Kill-Switch-Auslöser (Input, Verträge): `{quelle, zeitstempel, grund,
    kennwert?}`. `kennwert` ist optional und bleibt in dieser Story
    unverarbeitet (keine Drawdown-/Heartbeat-Berechnung, AC2/AC4 out of
    scope) — er wird nur durchgereicht und mitprotokolliert (AC11)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quelle: KillSwitchQuelle
    zeitstempel: datetime
    grund: str = Field(min_length=1)
    kennwert: Decimal | None = None


class KillSwitchStatus(BaseModel):
    """Aktueller Betriebszustand (Verträge: Kill-Switch-Aktion `halt` +
    `flatten` → Betriebszustand `angehalten`). `quelle`/`grund`/
    `ausgeloest_am` sind gesetzt, solange `zustand == "angehalten"` ist, und
    werden bei einer Freigabe (AC3) zurückgesetzt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    zustand: Betriebszustand
    quelle: KillSwitchQuelle | None = None
    grund: str | None = None
    ausgeloest_am: datetime | None = None


class KillSwitchEreignis(BaseModel):
    """Unveränderlicher Protokolleintrag EINER Auslösung (AC11) — trägt
    genau die von der Spec geforderten Felder: Auslöser (`quelle`),
    Zeitpunkt (`zeitstempel`) und Grund (`grund`), plus den optionalen
    Kennwert. `wirkung` unterscheidet eine tatsächlich zustandsändernde
    Auslösung von einer idempotenten Mehrfach-Auslösung im bereits
    „angehalten"-Zustand (Edge-Case: "kein doppeltes Flatten, kein
    Zustandssprung") — AC11 fordert, JEDE Auslösung zu protokollieren,
    nicht nur die erste."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quelle: KillSwitchQuelle
    zeitstempel: datetime
    grund: str = Field(min_length=1)
    kennwert: Decimal | None = None
    wirkung: Literal["ausgeloest", "idempotent_bereits_angehalten"]


#: Umgebung eines Secret-Store-Zugangs (Verträge, AC6) — bewusst nur genau
#: diese zwei Werte. Es gibt hier KEINE dritte Umgebung, die beide Namen
#: teilt oder zwischen ihnen "fällt zurück auf" — jede Umgebung hat ihren
#: eigenen, vollständig getrennten Namensraum (siehe
#: `app.core.secrets.resolve_secret_store_zugang`).
Umgebung = Literal["paper", "live"]


class SecretStoreZugang(BaseModel):
    """Vom Secret-Store aufgelöste Zugangsdaten EINES Dienstes (z. B. eines
    künftigen Broker-Adapters) in GENAU EINER Umgebung (AC6: "Paper- und
    Live-Zugänge sind strikt getrennt ... sodass eine Paper-Konfiguration
    nie versehentlich gegen einen Live-Endpunkt läuft.").

    `api_key`/`api_secret` sind bewusst `repr=False` (NFR "keine Secrets im
    Klartext in Logs oder Alerts") — pydantic lässt Felder mit `repr=False`
    aus `repr()`/`str()` dieses Modells weg, ein versehentliches `logger.info
    (zugang)`/`print(zugang)` exponiert damit nie den Klartext-Wert."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dienst: str = Field(min_length=1)
    umgebung: Umgebung
    endpunkt: str = Field(min_length=1)
    api_key: str = Field(min_length=1, repr=False)
    api_secret: str | None = Field(default=None, repr=False)


#: Alert-Typ (Verträge, Spec `betriebssicherung`) — das volle Vertrags-
#: `Literal`; diese Story (S-025) erzeugt tatsächlich nur `"heartbeat"` und
#: `"drawdown"`, die übrigen Werte werden von parallelen/späteren Modulen
#: (`kill` bereits durch `app.core.kill_switch`-Auslösung motiviert,
#: `quellenausfall` AC9, `halluzination` bereits AC8 via
#: `app.core.hallucination_kpi`) verwendet, ohne diesen Vertrag zu ändern.
AlertTyp = Literal["kill", "heartbeat", "drawdown", "quellenausfall", "halluzination"]

#: Alert-Schwere — Vokabular übernommen aus `docs/data-model.md` §7
#: `alert_log.severity` (CHECK ∈ {info, warn, critical}), kein neues
#: Vokabular für diese Story erfunden.
AlertSchwere = Literal["info", "warn", "critical"]


class Alert(BaseModel):
    """Alert (Output an Benachrichtigungskanal, Verträge): `{typ, schwere,
    nachricht, zeitstempel}`. Im Paper-MVP informativ (AC7, Nicht-Ziel
    dieser Story) — `app.core.alerts` sammelt Alerts in-memory und bietet
    eine Callback-Andockstelle für den künftigen Benachrichtigungskanal
    (S-026)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    typ: AlertTyp
    schwere: AlertSchwere
    nachricht: str = Field(min_length=1)
    zeitstempel: datetime


class HeartbeatEintrag(BaseModel):
    """Heartbeat-Zustand EINES überwachten Pipeline-Moduls (Verträge, AC4):
    `{modul_id, letzter_ping_zeitstempel, intervall_soll}`. Ausfall wird
    von `app.core.heartbeat.pruefe_ausfaelle()` erkannt, wenn `now −
    letzter_ping_zeitstempel > intervall_soll` (STRIKT `>`, analog zum
    Halluzinations-KPI-Schwellwertvergleich in `app.core.hallucination_kpi`
    — ein Ping GENAU am Intervall-Ende gilt noch nicht als Ausfall)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    modul_id: str = Field(min_length=1)
    letzter_ping_zeitstempel: datetime
    intervall_soll: timedelta


class DrawdownStatus(BaseModel):
    """Lesemodell von `app.core.drawdown_monitor.pruefe_drawdown()` (AC2,
    AC5). `drawdown_pct` ist der relative Rückgang vom laufenden
    Höchststand (High-Water-Mark) zum aktuellen Stand (`0` = am
    Höchststand, `1` = Totalverlust). `ueberwachungsluecke=True` (Edge-Case
    „fehlender Depot-Stand", deckt auch den Cold-Start ohne Baseline ab)
    bedeutet: `aktueller_stand`/`hoechststand`/`drawdown_pct` sind `None` —
    es wurde bewusst NICHT `0` gerechnet (kein stillschweigendes „kein
    Drawdown"). `kill_ausgeloest=True` markiert, dass DIESER Aufruf den
    bestehenden `app.core.kill_switch.ausloesen()` getriggert hat (AC2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aktueller_stand: Decimal | None = None
    hoechststand: Decimal | None = None
    drawdown_pct: Decimal | None = None
    ueberwachungsluecke: bool
    kill_ausgeloest: bool
