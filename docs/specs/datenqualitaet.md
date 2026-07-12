---
id: datenqualitaet
title: Datenqualität — Bronze/Silver/Gold, Point-in-Time & Validierung
status: active
version: 1
spec_format: use-case-2.0
area: dateneingang
---

# Spec: Datenqualität — Bronze/Silver/Gold, Point-in-Time & Validierung  (`datenqualitaet`)

> Konzept-Herkunft: (← C-019, C-009)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Der Datenqualitäts-Layer garantiert, dass jede weiterverarbeitete Zahl korrekt, reproduzierbar und zeitpunkt-genau ist: Rohdaten werden immutabel und point-in-time gespeichert (Bronze), normalisiert (Silver) und angereichert weitergegeben (Gold); Survivorship-Bias und Corporate Actions werden korrekt behandelt und jeder Datenpunkt validiert. Pflichtmodul ab MVP (Betriebssicherung, PoC-Priorität 1–2).

## Main Success Scenario
1. Ein vom Socket normalisierter Datenpunkt trifft im Datenqualitäts-Layer ein.
2. Der Rohwert wird unverändert und immutabel in der Bronze-Schicht mit seinem Beobachtungs-Zeitpunkt (Point-in-Time) und einer stabilen Event-ID abgelegt.
3. Der Validierungs-Layer prüft den Datenpunkt gegen die Pflicht-Regeln (Schema, Wertebereiche, Vollständigkeit); nur valide Datenpunkte gelangen weiter.
4. In der Silver-Schicht wird der Wert normalisiert (Einheiten, Formate, Survivorship-bereinigte Titel-Universen, Corporate-Actions-adjustierte Kurse).
5. In der Gold-Schicht wird der Wert angereichert und den Konsumenten bereitgestellt; die Bronze-Schicht bleibt für Replay und Audit erhalten.

## Alternative Flows
### A1: Rückwirkende Revision (z. B. FRED)
- Trifft für eine bereits gespeicherte Beobachtung ein revidierter Wert ein, wird die frühere Beobachtung nicht überschrieben, sondern als neue Point-in-Time-Version mit eigenem Gültigkeits-Zeitpunkt abgelegt; ein Replay auf ein früheres Datum liefert weiterhin den damals bekannten Wert.

### A2: Corporate Action (Split, Dividende)
- Bei einem Split/einer Dividende werden historische Kurse konsistent adjustiert, sodass abgeleitete Signale keine künstlichen Sprünge zeigen; die unadjustierten Originalwerte bleiben in Bronze erhalten.

### E1: Ungültiger Datenpunkt
- Verletzt ein Datenpunkt eine Pflicht-Validierungsregel, wird er nicht in Silver/Gold übernommen, sondern als ungültig markiert und protokolliert; nachgelagerte Module erhalten ihn nicht.

### E2: Doppelte Event-ID
- Trifft ein Datenpunkt mit bereits bekannter Event-ID ein, wird er idempotent behandelt (kein Duplikat, keine doppelte Verarbeitung).

## Acceptance-Kriterien

- **AC1** — Rohdaten werden in einer Bronze-Schicht immutabel gespeichert: ein einmal geschriebener Bronze-Datensatz wird nie verändert oder gelöscht; Korrekturen entstehen ausschliesslich als zusätzliche Versionen.
- **AC2** — Jeder Bronze-Datensatz trägt einen Point-in-Time-Zeitpunkt (wann der Wert bekannt/beobachtet war); eine Replay-Abfrage „Stand X" liefert exakt die Datenlage, die zum Zeitpunkt X bekannt war — spätere Revisionen fliessen nicht rückwirkend ein.
- **AC3** — Die Silver-Schicht enthält die normalisierten Werte (einheitliche Einheiten/Formate) und ist aus der Bronze-Schicht reproduzierbar (Replay-fähig).
- **AC4** — Die Gold-Schicht enthält die angereicherten, für Konsumenten bestimmten Werte; keine Anreicherung verändert oder ersetzt die zugrunde liegenden Bronze-Rohdaten.
- **AC5** — Titel-Universen für historische Auswertungen enthalten auch delistete/insolvente/fusionierte Titel (Survivorship-Bias-Vermeidung); eine Auswertung „welche Titel existierten zum Zeitpunkt X" schliesst zu X existierende, später verschwundene Titel ein.
- **AC6** — Kurse werden für Corporate Actions (Splits, Dividenden) konsistent adjustiert, sodass aus adjustierten Reihen abgeleitete Kennzahlen keine durch die Corporate Action verursachten künstlichen Sprünge enthalten; die unadjustierten Originalwerte bleiben in Bronze erhalten (deckt A2).
- **AC7** — Ein Datenvalidierungs-Layer prüft jeden eingehenden Datenpunkt gegen definierte Pflicht-Regeln (mindestens: Schema/Feldtypen, erlaubte Wertebereiche, Pflicht-Metadaten-Vollständigkeit); nur valide Datenpunkte gelangen nach Silver/Gold. Dieser Layer ist ab MVP aktiv (Pflichtmodul).
- **AC8** — Ungültige Datenpunkte werden nicht weitergereicht, sondern als ungültig markiert und mit Grund protokolliert (deckt E1); sie erscheinen nicht in den Gold-Ergebnissen der Konsumenten.
- **AC9** — Jeder Datenpunkt besitzt eine stabile Event-ID; das erneute Eintreffen desselben Ereignisses (gleiche Event-ID) führt zu idempotenter Verarbeitung ohne Duplikat und ohne doppelte Weiterverarbeitung (deckt E2).
- **AC10** — Rückwirkende Revisionen einer Quelle (z. B. FRED) erzeugen eine neue Point-in-Time-Version statt eines Überschreibens; die ursprüngliche Version bleibt abfragbar und ein Replay auf ein früheres Datum bleibt stabil (deckt A1).

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace datenqualitaet#AC<n>[,BR-NNN]`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC ≥ 1 deckender Test). Details: `docs/architecture/traceability-subsystem.md`.

## Verträge
- **Bronze-Datensatz:** `{ event_id (stabil), roh_wert, quelle, beobachtungs_zeitpunkt (point-in-time), empfangs_zeitpunkt, anlageklassen_tag }` — immutabel, versioniert.
- **Silver-Datensatz:** `{ event_id, normalisierter_wert, einheit, adjustierungs_info, abgeleitet_aus: bronze_version }` — reproduzierbar aus Bronze.
- **Gold-Datensatz:** `{ event_id, angereicherter_wert, qualitaetsindikator, herkunft: silver_version }` — Konsumenten-Sicht.
- **Validierungs-Ergebnis:** `{ event_id, valide: bool, verletzte_regeln[...], zeitstempel }`.
- **Replay-Abfrage:** Input `{ titel/quelle, stand_zeitpunkt }` → Output: Datenlage exakt wie zum `stand_zeitpunkt` bekannt.

## Edge-Cases & Fehlerverhalten
- Revision trifft für ein Datum ein, das bereits in Gold verarbeitet wurde → neue Point-in-Time-Version; nachgelagerte Recalculation über das Recalculation-Window (`[[dateneingang]]`) verwendet die neue Version, alte Replays bleiben stabil (AC10).
- Corporate Action rückwirkend gemeldet → historische Silver-Reihe wird neu adjustiert abgeleitet, Bronze bleibt unverändert (AC6).
- Delisting eines gehaltenen Titels → Titel verschwindet nicht aus dem historischen Universum (AC5).
- Event-ID kollidiert mit inhaltlich abweichendem Datenpunkt → als Validierungsfehler behandeln und protokollieren (AC7/AC8), nicht stillschweigend überschreiben.

## NFRs
- Reproduzierbarkeit: Silver und Gold müssen zu jedem Zeitpunkt aus Bronze rekonstruierbar sein (Audit/Replay).
- Integrität: Bronze ist append-only; jede Löschung/Änderung eines Bronze-Datensatzes ist ein Fehler.
- Pflicht ab MVP: der Validierungs-Layer darf nicht abschaltbar sein, wenn produktive/simulierte Trades daraus abgeleitet werden.

## Nicht-Ziele
- Adapter, Auth, Rate-Limits, Scheduler und die geteilte Abfrage sind Gegenstand von `[[dateneingang]]`.
- Score-/Signal-Aggregation (z-Scores, Kategorie-Scores) ist Gegenstand der Analyse, nicht dieser Spec.
- Feature Store, Model Registry und Drift-Monitoring sind spätere Stufen (Stufe 3/KI-Reife), nicht MVP.

## Abhängigkeiten
- `[[dateneingang]]` (liefert normalisierte Datenpunkte inkl. Metadaten und Recalculation-Window für Revisionen).
- Konsumenten der Gold-Schicht: Datenquellen-Abfrage, Analyse, Validierungs-Gate.
- Externe Quelle mit Revisionsverhalten: FRED (rückwirkende Korrekturen).
