---
id: ausfuehrung-paper
title: Order-Ausführung, Modus-Schalter & Handelsplattformen (Paper)
status: active
version: 1
spec_format: use-case-2.0
area: handel
---

# Spec: Order-Ausführung, Modus-Schalter & Handelsplattformen (Paper)  (`ausfuehrung-paper`)

> Konzept-Herkunft: (← C-016)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Das Kauf-&-Verkaufsmodul führt gebilligte Käufe (vom Risikomanagement-Gate) und Verkaufsaufträge (vom Exit-Sizing) aus. Ein **Modus-Schalter «echt / simuliert»** entscheidet, ob eine Order an einen realen Broker oder an die Paper-Simulation geht — beide Modi teilen sich **denselben Order-Code-Pfad**, nur der Endpunkt/Key unterscheidet sich. Im MVP läuft das Modul **ausschliesslich simuliert (Paper)**, voll autonom, mit rein informativen Benachrichtigungen. Es misst je Trade die Arrival-Price-Slippage und behandelt Teilfills, Rejects und Timeouts sauber.

## Main Success Scenario
1. Das Modul erhält eine gebilligte Kauf-Order (ggf. gedeckelt) vom Risikomanagement-Gate bzw. einen Verkaufsauftrag vom Exit-Sizing.
2. Es bestimmt anhand der Anlageklasse den wirksamen Modus (global, ggf. je Anlageklasse überschrieben) und die zuständige Handelsplattform.
3. Es merkt sich den Signal-Kurs (Arrival Price) zum Zeitpunkt der Order.
4. Es setzt den vom Sizing vorgegebenen Order-Typ um (Market/Limit/Stop/Stop-Limit/Trailing/TWAP) und sendet die Order über den gemeinsamen Code-Pfad an den Ziel-Endpunkt (Paper im MVP).
5. Bei Ausführung berechnet es die Arrival-Price-Slippage (Signal-Kurs vs. Fill) und meldet Fill-Preis, tatsächliche Kosten und Slippage an das Depotmodul/TCA.
6. Es sendet eine informative Benachrichtigung über die Ausführung (keine Bestätigungsabfrage im MVP).

## Alternative Flows
### A1: Modus-Überschreibung je Anlageklasse
- Der Modus ist global gesetzt, kann aber je Anlageklasse überschrieben werden (z. B. Aktien anders als Krypto); der wirksame Modus je Order ergibt sich aus der spezifischsten gesetzten Ebene.

### A2: Paper-Fill mit Realismus-Modell
- Im simulierten Modus erzeugt das Modul den Fill über ein eigenes Slippage-/Spread-Modell, statt zum unveränderten Signal-Kurs zu füllen (Paper-Fills sind sonst zu optimistisch).

### A3: Krypto ohne Broker
- Ist für Krypto kein Broker angebunden, wird die Order im Paper-Modus brokerlos simuliert (Detail der Krypto-Anbindung offen).

### E1: Teilfill
- Wird eine Order nur teilweise ausgeführt, protokolliert das Modul die ausgeführte Teilmenge, meldet sie ans Depot und behandelt die Restmenge definiert (weiter offen / storniert je Order-Typ) — kein stiller Verlust der Restmenge.

### E2: Reject
- Lehnt die Plattform die Order ab, wird kein Bestand verändert; der Reject wird mit Grund protokolliert und gemeldet.

### E3: Timeout
- Antwortet die Plattform nicht innerhalb der Frist, geht das Modul nicht von einer Ausführung aus; es protokolliert den Timeout und verändert den Bestand nicht ohne bestätigten Fill.

## Acceptance-Kriterien
- **AC1** — Das Modul führt sowohl Käufe (Quelle: Risikomanagement-Gate) als auch Verkäufe (Quelle: Exit-Sizing) aus.
- **AC2** — Ein Modus-Schalter «echt / simuliert» existiert global **und** ist je Anlageklasse überschreibbar; der wirksame Modus einer Order ergibt sich aus der spezifischsten gesetzten Ebene (deckt A1).
- **AC3** — Im MVP ist ausschliesslich der simulierte (Paper-)Modus aktiv; das Modul handelt voll autonom und sendet zu Ausführungen nur informative Benachrichtigungen (keine Bestätigungsabfrage vor der Order).
- **AC4** — Echter und simulierter Modus nutzen denselben Order-Code-Pfad; der Unterschied liegt allein in Endpunkt/Zugangsschlüssel, nicht in getrennter Order-Logik.
- **AC5** — Die MVP-Broker-Anbindung ist Interactive Brokers im Paper-Modus; Krypto kann bei fehlender Broker-Anbindung brokerlos im Paper-Modus simuliert werden (deckt A3).
- **AC6** — Das Modul setzt die vom Sizing vorgegebenen Order-Typen um: Market, Limit, Stop, Stop-Limit, Trailing und TWAP.
- **AC7** — Je Trade wird die Arrival-Price-Slippage als Differenz zwischen Signal-Kurs (zum Order-Zeitpunkt) und tatsächlichem Fill gemessen und an das Depotmodul/TCA gemeldet.
- **AC8** — Teilfills, abgelehnte Orders (Rejects) und Timeouts werden definiert behandelt und protokolliert; bei Reject/Timeout wird der Bestand nicht ohne bestätigten Fill verändert (Kernanforderung, deckt E1–E3).
- **AC9** — Im simulierten Modus werden Paper-Fills über ein eigenes Slippage-/Spread-Modell erzeugt (nicht zum unveränderten Signal-Kurs); das Modell ist als **provisorischer, konfigurierbarer** Default hinterlegt (deckt A2).
- **AC10** — Das Modul wählt die Handelsplattform je Anlageklasse anhand von Plattform-Stammdaten (Referenzdaten: Gebührenmodell, Mindestgebühr, typischer Spread je Anlageklasse).
- **AC11** — Die Plattform-Referenzdaten liefern erwartete Kosten (Courtage + Spread + geschätzte Slippage) an die Sizing-Module (Pre-Trade-Kalkulation).
- **AC12** — Die Bewährungsregel vor Echtgeld ist als **provisorischer, konfigurierbarer** Default hinterlegt: mindestens 30–50 Trades bzw. 3–6 Monate im Simulationsmodus vor einem Live-Start, Live-Start mit 10–20 % des Kapitals; Live-Betrieb ist ausdrücklich Nicht-Ziel des MVP.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace ausfuehrung-paper#AC<n>`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC ≥ 1 deckender Test).

## Verträge
- **Input:**
  - gebilligte Kauf-Order (Titel, Anlageklasse, freigegebene Grösse, Order-Typ, Preis) vom Risikomanagement-Gate;
  - Verkaufsauftrag (Tranchen, Order-Typ, Preis) vom Exit-Sizing;
  - Gebühren/Spread der Plattform von den Handelsplattform-Stammdaten.
- **Output:**
  - Order an Broker-Endpunkt (echt) bzw. Paper-Simulation (virtuell);
  - Ausführungsergebnis an das Depotmodul: `{ fill_preis, ausgefuehrte_menge, tatsaechliche_kosten, arrival_price, slippage, status: filled|partial|rejected|timeout }`;
  - informative Benachrichtigung.
- **Handelsplattform-Stammdaten (Referenzdaten):** je Plattform/Anlageklasse `{ gebuehrenmodell, mindestgebuehr, typischer_spread }` → erwartete Kosten an Position-/Exit-Sizing.
- **Konfiguration:** Modus (global + je Anlageklasse), Plattform-Zuordnung je Anlageklasse, Order-Timeout/Retry, Paper-Slippage-/Spread-Modell-Parameter.

> **AC11-Präzisierung (S-017):** Die "geschätzte Slippage" der Pre-Trade-Kalkulation (AC11) ist NICHT dasselbe wie das Paper-Fill-Slippage-/Spread-Modell aus AC9 (das modelliert die tatsächliche Fill-Slippage einer bereits gesendeten Order, nicht die Vorab-Schätzung an das Sizing). Für AC11 ist ein eigener, einfacher **provisorischer, konfigurierbarer** Default-Prozentsatz vorgesehen (`Settings.erwartete_slippage_pct_default`, Default 0.05 % — Konzept/Spec nennen keinen konkreten Wert), unabhängig von den (Folge-Story S-049) Fill-Modell-Parametern.



## Edge-Cases & Fehlerverhalten
- Order kleiner als die Mindest-Ordergrösse/Mindestgebühr-Schwelle → das Modul meldet dies zurück (Mindestgebühr-Effekt), statt einen unwirtschaftlichen Trade auszuführen.
- Signal-Kurs zum Order-Zeitpunkt nicht verfügbar → Arrival-Price wird als unbestimmt markiert, Slippage nicht fälschlich als 0 gemeldet.
- Modus-Überschreibung für eine Anlageklasse ohne angebundene Live-Plattform → im MVP unkritisch (nur Paper aktiv), spätere Live-Aktivierung erfordert vorhandene Plattform.

## NFRs
- Fehlerbehandlung (Teilfills/Rejects/Timeouts) ist Kernanforderung — «die häufigste Verlustquelle ist der Logikfehler, nicht der Markt».
- Kein LLM im Order-Pfad (harte Architektur-Regel des Konzepts).
- Latenz je Plattform dokumentiert (für die MVP-Zeithorizonte, kein HFT, unkritisch).
- Alle als «(Default, provisorisch)» gekennzeichneten Werte sind konfigurierbar und im Simulationsmodus kalibrierbar.

## Nicht-Ziele
- Kein Live-/Echtgeld-Handel im MVP (nur Paper).
- Kein Bestätigungspflicht-Modus (hybrider Betrieb mit Nutzerbestätigung ist späteres Feature).
- Kein separates historisches Backtesting-System (durch Paper-Modus mit Live-Daten ersetzt).
- Keine Klärung von FINMA-Frequenzgrenze oder CH-Stempelabgabe (offen, ausserhalb dieser Spec).

## Offene Punkte (aus dem Konzept übernommen)
- Krypto-Anbindung: über IBKR vs. separater Broker (z. B. Kraken) vs. brokerlose Paper-Simulation — offen.
- Fill-/Slippage-Modell der Simulation im Detail — offen.
- FINMA-Frequenzgrenze; CH-Steuern/Stempelabgabe bei US-Brokern — offen.

## Abhängigkeiten
- Vorgelagert: [[risikomanagement]] (gebilligte Käufe), Exit-Sizing (Verkaufsaufträge), Handelsplattform-Stammdaten (Kosten/Routing), Socket (Live-Kurse/Arrival Price).
- Nachgelagert: Depotmodul (Ausführungsergebnis, TCA), Position-/Exit-Sizing (erwartete Kosten Pre-Trade).
- Querschnitt: [[betriebssicherung]] (Paper-/Live-Trennung, Kill-Switch), Slippage-/Spread-Realismus-Modell.
