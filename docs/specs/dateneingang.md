---
id: dateneingang
title: Dateneingang — Socket, Datenquellen-Registry & geteilte Abfrage
status: active
version: 1
spec_format: use-case-2.0
area: dateneingang
---

# Spec: Dateneingang — Socket, Datenquellen-Registry & geteilte Abfrage  (`dateneingang`)

> Konzept-Herkunft: (← C-009)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Die technische Anbindungsschicht (Socket) zapft alle externen Datenquellen einheitlich an, normalisiert sie in ein internes Schema und stellt den nachgelagerten Modulen über EINE geteilte Datenquellen-Abfrage (DRY) je Titel ein einheitliches Signal-Bündel bereit. Die nachgelagerten Module müssen nicht wissen, woher die Daten technisch kommen.

## Main Success Scenario
1. Der Scheduler löst für eine aktive Quelle gemäss ihrem konfigurierten Abrufintervall einen Abruf aus.
2. Der zuständige Quellen-Adapter authentifiziert sich (gekapselt), ruft die Quelle unter Beachtung ihres Rate-Limits ab und übersetzt die quellenspezifische Antwort in das einheitliche interne Schema.
3. Jeder normalisierte Datenpunkt erhält die Metadaten Quelle, Timestamp, Anlageklassen-Tag (1–11) und Qualitätsindikator.
4. Ein Konsument (Suchkriteria, Depot-Suchkriterien oder Research) fragt über die geteilte Datenquellen-Abfrage einen Titel ab.
5. Die Abfrage wählt anhand der Anlageklassen-Zuordnung aus der Quellen-Registry die passenden Quellen, aggregiert deren Daten und liefert je Titel ein einheitliches Signal-Bündel inklusive Liquidität und Volatilität.

## Alternative Flows
### A1: Inaktive Anlageklasse (Toggle aus)
- Ist die einem Abruf zugeordnete Anlageklasse per Toggle deaktiviert, findet weder Abruf noch Datenkosten statt; der Scheduler überspringt die betroffenen Quellen für diese Klasse.

### A2: Revisionsbehaftete Quelle (FRED)
- Für Quellen, die Werte rückwirkend korrigieren, zieht der Adapter zusätzlich das Recalculation-Window der letzten Tage erneut und überschreibt/ergänzt die betroffenen Datenpunkte idempotent.

### E1: Transienter Quellenfehler (429/5xx/Timeout)
- Der Abruf wird mit Exponential Backoff wiederholt; bei dauerhaftem Fehlschlag landet das Arbeitselement in der Dead-Letter-Queue und wird geloggt, ohne den restlichen Betrieb zu blockieren.

## Acceptance-Kriterien

- **AC1** — Für jede registrierte Datenquelle existiert genau ein Adapter, der die quellenspezifische Antwort in dasselbe einheitliche interne Schema übersetzt; nachgelagerte Konsumenten erhalten quellen-unabhängig identisch strukturierte Datensätze.
- **AC2** — Jeder normalisierte Datenpunkt trägt die Pflicht-Metadaten Quelle, Timestamp, Anlageklassen-Tag (ganzzahliger Wert 1–11) und Qualitätsindikator; fehlt eine dieser Metadaten, gilt der Datenpunkt als ungültig und wird nicht weitergereicht.
- **AC3** — Authentifizierung (API-Keys/OAuth-Tokens) und Rate-Limits sind je Quelle im Adapter gekapselt; Credentials liegen nicht im Code und erscheinen nicht im Klartext in Logs.
- **AC4** — Das Abrufintervall ist je Quelle ein konfigurierbarer Scheduler-Parameter mit den provisorischen Default-Werten: Polymarket, Whale Alert und Nansen 30–60 s; Reddit 15–30 min; SEC 2 h; FRED täglich. Die Werte sind ohne Codeänderung überschreibbar.
- **AC5** — Die Quellen-Registry führt 12 Datenquellen in 5 Kategorien (Equity Insider & Fundamentals, Retail Sentiment & Social, Blockchain & Crypto, ETFs & Fonds, Makro & Anleihen) und ordnet jeder Quelle die Anlageklassen (1–11) zu, für die sie verwertbare Signale liefert.
- **AC6** — Reddit-Sentiment wird ausschliesslich für retail-getriebene Anlageklassen (Aktien = 1, Krypto = 7) herangezogen; für nicht-retail-getriebene Klassen (z. B. Obligationen = 4, FX = 10) wird Reddit als Quelle nicht abgefragt.
- **AC7** — Es existiert genau EINE Datenquellen-Abfrage-Schnittstelle, die von drei Konsumenten (Suchkriteria, Depot-Suchkriterien, Research) genutzt wird; alle drei erhalten Ergebnisse über dieselbe Schnittstelle (keine parallele Zweit-Implementierung).
- **AC8** — Die Datenquellen-Abfrage wählt je Titel anhand der Anlageklassen-Zuordnung aus der Registry die passenden Quellen, aggregiert deren Daten und liefert je Titel ein einheitliches Signal-Bündel, das mindestens Liquidität und Volatilität enthält.
- **AC9** — Ist die Anlageklasse eines Abrufs per Toggle inaktiv, erfolgt für diese Klasse kein Quellenabruf und es entstehen keine Datenkosten (deckt A1). Nachweisbar daran, dass für eine deaktivierte Klasse keine externen Aufrufe ausgelöst werden.
- **AC10** — Transiente Quellenfehler (HTTP 429, 5xx, Timeout) werden mit Exponential Backoff erneut versucht; nach erschöpften Versuchen wird das Arbeitselement in eine Dead-Letter-Queue verschoben und protokolliert, ohne andere Quellen zu blockieren (deckt E1). *(provisorischer, konfigurierbarer Default)*
- **AC11** — Jede Abfrage wird als Arbeitselement in eine Queue-of-Work eingereiht und von Workern mit einem Token-Bucket je Quelle abgearbeitet, sodass die quellenspezifischen Rate-Limits eingehalten und die unterschiedlichen Frequenzen entkoppelt werden. *(provisorischer, konfigurierbarer Default)*
- **AC12** — Für Quellen mit rückwirkenden Revisionen (z. B. FRED) zieht der Adapter zusätzlich ein konfigurierbares Recalculation-Window (Default 2–3 Tage, provisorisch) erneut und aktualisiert die betroffenen Datenpunkte idempotent (deckt A2).
- **AC13** — Im MVP sind nur die kostenlosen Quellen (SEC Form 4, Reddit, Polymarket, FRED, Wirtschaftskalender) aktiv; kostenpflichtige/institutionelle Quellen sind registriert, aber deaktiviert und lösen ohne Aktivierung keinen Abruf aus.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace dateneingang#AC<n>[,BR-NNN]`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC ≥ 1 deckender Test). Details: `docs/architecture/traceability-subsystem.md`.

## Verträge
- **Interner Datenpunkt (Socket-Output):** `{ wert(e), quelle, timestamp, anlageklassen_tag: 1..11, qualitaetsindikator }` — einheitlich über alle Quellen.
- **Quellen-Registry-Eintrag:** `{ name, kategorie: 1 von 5, zugangsart, abrufintervall (konfigurierbar), rate_limit, kosten, aktiv: bool, anlageklassen: [1..11] }`.
- **Datenquellen-Abfrage (eine Schnittstelle, drei Konsumenten):**
  - Input: Filterkriterien / Titel-Anfrage inkl. Anlageklasse; Konsumenten-Kontext (neu / bestehend / research).
  - Output: je Titel ein Signal-Bündel `{ titel, anlageklasse, signale[...], liquiditaet, volatilitaet, quellen_metadaten[...] }`.
  - **Berechnung `liquiditaet`/`volatilitaet` (S-021, provisorischer Default, analog AC4/AC10/AC11/AC12):** solange weder eine dedizierte Volumen-/ADV-Quelle noch das für echte annualisierte Volatilität vorgesehene `domain/quant`-Modul (ADR-009) existieren, gilt: `liquiditaet` = Anzahl der Quellen, die für den Titel mindestens einen aggregierten Datenpunkt beigetragen haben (Datenverfügbarkeits-Proxy); `volatilitaet` = Populationsstandardabweichung aller aggregierten Werte über die passenden Quellen. Kein annualisiertes Mass, keine ADV/RVOL-Kennzahl (→ `docs/data-model.md` `instrument.liquiditaet`) — Kalibrierung/Ablösung durch eine echte Kennzahl ist Folgearbeit (`domain/quant`).
- **Scheduler-Parameter je Quelle:** Abrufintervall, Retry-/Timeout-Verhalten, Aktiv/Inaktiv-Schalter — alle konfigurierbar.

## Edge-Cases & Fehlerverhalten
- Quelle liefert unvollständige Metadaten → Datenpunkt verworfen (AC2), nicht geschätzt.
- Rate-Limit-Verletzung droht → Token-Bucket drosselt statt zu überschreiten (AC11).
- Dauerhaft fehlschlagende Quelle → Dead-Letter-Queue + Alert auf DLQ-Backlog (AC10), Rest des Systems läuft weiter.
- Deaktivierung einer Klasse während laufendem Betrieb → keine neuen Abrufe für diese Klasse (AC9); Überwachung offener Positionen ist Sache der nachgelagerten Module, nicht des Sockets.
- Doppelte Event-IDs bei Revisions-Re-Pull → idempotente Aktualisierung, keine Duplikate (AC12; Detail-Idempotenz siehe `[[datenqualitaet]]`).

## NFRs
- Kosten-Disziplin: inaktive Klassen und deaktivierte Quellen dürfen KEINE externen Aufrufe und damit keine Kosten verursachen (AC9, AC13).
- Secrets: keine Credentials im Code/Repo; maskierte Ausgabe in Logs (AC3).
- Robustheit: Ausfall einer Quelle darf die übrigen Quellen nicht blockieren (AC10).
- Konfigurierbarkeit: alle als provisorisch markierten Defaults (Intervalle, Token-Bucket, Backoff, DLQ, Recalculation-Window) ohne Codeänderung überschreibbar; Kalibrierung im Simulationsmodus.

## Nicht-Ziele
- Bronze/Silver/Gold-Schichtung, Point-in-Time-Immutabilität, Survivorship-Bias- und Corporate-Actions-Behandlung sowie die Datenvalidierung sind Gegenstand von `[[datenqualitaet]]`, nicht dieser Spec.
- Score-/Kategorie-Berechnung erfolgt in der Analyse, nicht in der Datenquellen-Abfrage (diese liefert nur normalisierte Signal-Bündel).
- Datenquellen für Immobilien (6) und Rohstoffe (8) sind noch offen und nicht Teil des MVP.

## Abhängigkeiten
- `[[datenqualitaet]]` (Bronze/Silver/Gold, Point-in-Time, Idempotenz, Validierungs-Layer).
- `[[kandidatensuche]]` und Depot-Suchkriterien sowie Research als Konsumenten der geteilten Abfrage.
- Anlageklassen-Toggles aus der Konfiguration (respektiert von Scheduler und Abfrage).
- Externe Dienste: SEC (data.sec.gov), Reddit/PRAW, Polymarket, FRED, Wirtschaftskalender (MVP-frei); Whale Alert, Nansen, Finnhub, u. a. (später/kostenpflichtig).
