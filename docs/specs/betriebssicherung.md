---
id: betriebssicherung
title: Betriebssicherung (Kill-Switch, Heartbeat, Alerts, Secrets)
status: active
version: 1
spec_format: use-case-2.0
area: betrieb
---

# Spec: Betriebssicherung (Kill-Switch, Heartbeat, Alerts, Secrets)  (`betriebssicherung`)

> Konzept-Herkunft: (← C-019)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck

Die Betriebssicherung ist der Notaus- und Wächter-Layer des Systems: ein manuell und automatisch auslösbarer **Kill-Switch («flatten & halt»)**, **Heartbeat-Überwachung** aller Pipeline-Module, **Drawdown-Alerts**, sicheres **Secrets-Management** (getrennte Paper-/Live-Zugänge) und ein **Benachrichtigungskanal**. Ein automatisiertes System ohne Notausschalter und sicheres Schlüsselmanagement ist ein Totalverlust-Risiko — diese Bausteine sind ab MVP Pflicht (PoC-Priorität 1–2). Im Paper-MVP sind Benachrichtigungen informativ.

## Main Success Scenario   <!-- Kill-Switch «flatten & halt» -->

1. Ein Auslöser trifft ein: entweder eine **manuelle** Kill-Switch-Aktion (durch den Owner) oder ein **automatischer Trigger** (z. B. Gesamt-Drawdown-Schwelle überschritten oder Heartbeat-Ausfall).
2. Das System stoppt sofort die Erzeugung neuer Orders (halt): keine neuen Käufe, kein neues Sizing.
3. Es leitet «flatten» ein — die offenen Positionen werden gemäss hinterlegter Ausstiegs-Order-Logik geschlossen (im Paper-Modus simuliert).
4. Es setzt den Betriebszustand auf „angehalten" und protokolliert Auslöser, Zeitpunkt und Grund unveränderlich.
5. Es sendet über den Benachrichtigungskanal einen Alarm mit Auslöser und Zustand.
6. Aus dem Zustand „angehalten" wird nur durch eine **explizite** Wieder-Freigabe (manuell) in den Normalbetrieb zurückgekehrt — nie automatisch.

## Alternative Flows

### A1: Automatischer Trigger bei Gesamt-Drawdown-Schwelle
- Überschreitet der portfolioweite Drawdown die konfigurierte Schwelle, löst der Kill-Switch ohne manuelles Zutun aus (Schwellenwert konfigurierbar, konkreter Default in der Umsetzung offen/noch festzulegen).

### A2: Heartbeat-Ausfall eines Pipeline-Moduls
- Meldet sich ein überwachtes Modul länger als das konfigurierte Intervall nicht, wird dies als Ausfall erkannt, ein Alert erzeugt und — je nach Konfiguration und Kritikalität des Moduls — der Kill-Switch ausgelöst.

### A3: Quellenausfall (No-Evidence-No-Trade)
- Fällt eine benötigte Datenquelle aus oder liefert veraltete Daten, greift das Fallback/Alerting: es wird kein Trade auf fehlender Datengrundlage erzeugt (No-Evidence-No-Trade), und der Ausfall wird gemeldet.

### E1: Alarm-Kanal nicht erreichbar
- Ist der Benachrichtigungskanal nicht erreichbar, wird der Alarm dennoch persistent protokolliert und beim nächsten erreichbaren Zeitpunkt zugestellt; der Kill-Switch/Schutzmechanismus wird dadurch nicht blockiert.

## Acceptance-Kriterien

- **AC1** — Der Kill-Switch «flatten & halt» ist **manuell** auslösbar und stoppt sofort jede Erzeugung neuer Orders (halt) und leitet das Schliessen offener Positionen ein (flatten; im Paper-Modus simuliert).
- **AC2** — Der Kill-Switch besitzt zusätzlich **automatische Trigger**; mindestens ein Überschreiten einer konfigurierbaren Gesamt-Drawdown-Schwelle löst ihn ohne manuelles Zutun aus. Der Schwellenwert ist konfigurierbar (konkreter Default provisorisch/offen — in der Umsetzung festzulegen). (Deckt A1.)
- **AC3** — Nach Auslösen bleibt das System im Zustand „angehalten"; die Rückkehr in den Normalbetrieb erfolgt ausschliesslich durch eine explizite manuelle Wieder-Freigabe, nie automatisch.
- **AC4** — Jedes Pipeline-Modul wird per Heartbeat überwacht; bleibt der Heartbeat eines Moduls länger als das konfigurierte Intervall aus, wird dies als Ausfall erkannt, ein Alert erzeugt und je nach Kritikalität/Konfiguration der Kill-Switch ausgelöst (deckt A2).
- **AC5** — Der portfolioweite Drawdown wird laufend überwacht; bei Überschreiten konfigurierbarer Schwellen wird ein Drawdown-Alert erzeugt (Alert-Schwelle unabhängig von der Kill-Switch-Schwelle konfigurierbar).
- **AC6** — Secrets (API-Keys, Tokens, Credentials) liegen niemals im Code oder in versionierten Dateien, sondern in einem getrennten Secret-Store; Paper- und Live-Zugänge sind strikt getrennt (getrennte Credentials/Endpunkte), sodass eine Paper-Konfiguration nie versehentlich gegen einen Live-Endpunkt läuft.
- **AC7** — Alle sicherheitsrelevanten Ereignisse (Kill-Switch-Auslösung, Heartbeat-Ausfall, Drawdown-Alert, Quellenausfall) werden über einen Benachrichtigungskanal gemeldet; im Paper-MVP sind diese Benachrichtigungen informativ (kein Eingriff/keine Bestätigungspflicht erforderlich).
- **AC8** — Die Betriebssicherung konsumiert den Halluzinations-KPI aus dem LLM-Grounding-Cross-Check: übersteigt die Faktenabweichung die dort definierte Schwelle (> 2 %), wird ein Alarm ausgelöst (→ `[[llm-grounding]]`). Die KPI-Berechnung selbst liegt beim LLM-Grounding; die Betriebssicherung ist deren Alarm-Konsument.
- **AC9** — Bei Ausfall oder Veralten einer benötigten Datenquelle greift Fallback/Alerting; es wird kein Trade auf fehlender Datengrundlage erzeugt (No-Evidence-No-Trade) und der Ausfall wird gemeldet (deckt A3).
- **AC10** — Ist der Benachrichtigungskanal nicht erreichbar, wird der Alarm persistent protokolliert und später zugestellt; Kill-Switch und Schutzmechanismen bleiben davon unabhängig funktionsfähig (deckt E1).
- **AC11** — Jede Auslösung und jeder Alert wird unveränderlich mit Auslöser, Zeitpunkt und Grund protokolliert.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace betriebssicherung#AC<n>`.

## Verträge

- **Kill-Switch-Auslöser (Input):** `{ quelle (manuell|drawdown|heartbeat|extern), zeitstempel, grund, kennwert? }`.
- **Kill-Switch-Aktion (Wirkung):** `halt` (keine neuen Orders) + `flatten` (offene Positionen schliessen, Paper simuliert) → Betriebszustand `angehalten`.
- **Heartbeat (je Modul):** `{ modul_id, letzter_ping_zeitstempel, intervall_soll }`; Ausfall wenn `now − letzter_ping > intervall_soll`.
- **Drawdown-Überwachung (Input):** Depot-Stand/Equity-Kurve aus dem Depotmodul; Vergleich gegen `drawdown_alert_schwelle` und `drawdown_kill_schwelle`.
- **Alert (Output an Benachrichtigungskanal):** `{ typ (kill|heartbeat|drawdown|quellenausfall|halluzination), schwere, nachricht, zeitstempel }`; im Paper-MVP informativ.
- **Halluzinations-KPI (Input, von `[[llm-grounding]]`):** Faktenabweichungs-Rate; Alarm bei Überschreiten von > 2 %.
- **Secrets-Zugriff:** über den Secret-Store aufgelöst, getrennt nach Umgebung `paper` / `live`; nie im Klartext im Code/Repo.

## Edge-Cases & Fehlerverhalten

- Mehrfach-Auslösung im „angehalten"-Zustand ist idempotent (kein doppeltes Flatten, kein Zustandssprung).
- Ein Heartbeat-Ausfall der Betriebssicherung selbst muss extern/über einen unabhängigen Wächter erkennbar sein (der Wächter darf nicht die einzige Selbstüberwachung sein).
- Fehlt der Depot-Stand für die Drawdown-Berechnung, wird dies als Überwachungslücke gemeldet, nicht stillschweigend als „kein Drawdown" gewertet.

## NFRs

- **Security:** Trennung Paper/Live ist hart (getrennte Credentials/Endpunkte); keine Secrets im Klartext in Logs oder Alerts.
- **Verfügbarkeit:** Der Kill-Switch muss auch bei degradiertem System (ausgefallene Module) auslösbar bleiben.
- **Auditierbarkeit:** Auslöse- und Alert-Protokoll ist vollständig und unveränderlich.

## Nicht-Ziele

- Kein Bestätigungspflicht-/Hybrid-Betriebsmodus im MVP (Benachrichtigungen sind informativ; Bestätigungspflicht ist späteres Feature, ← C-016).
- Keine Berechnung des Halluzinations-KPI selbst (liegt im LLM-Grounding; hier nur Konsum/Alarm).
- Kein Datenqualitäts-Layer im Detail (Point-in-Time, Survivorship, Corporate Actions sind eigene Bausteine des Dateneingangs, ← C-019/C-009).

## Abhängigkeiten

- Kauf-/Verkaufsmodul (`[[kauf-verkauf]]`) — Ziel des „halt" (keine neuen Orders) und „flatten" (Positionen schliessen).
- Depotmodul (`[[depot]]`) — liefert Depot-Stand/Equity-Kurve für die Drawdown-Überwachung.
- LLM-Grounding (`[[llm-grounding]]`) — liefert den Halluzinations-KPI (Alarm-Konsum, AC8).
- Socket / Datenquellen (`[[dateneingang]]`) — Quellenausfall-Signale (No-Evidence-No-Trade, AC9).
- Alle Pipeline-Module — Heartbeat-Quellen.
