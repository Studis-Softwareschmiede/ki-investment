---
id: depot
title: Depotmodul (Bestand, G/V, Transaktionshistorie)
status: active
version: 2
spec_format: use-case-2.0
area: depot
---

# Spec: Depotmodul (Bestand, G/V, Transaktionshistorie)  (`depot`)

> Konzept-Herkunft: (← C-017)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck

Das Depotmodul ist die **Wahrheit über den Bestand**: es führt je Position alle Attribute, berechnet realisierten und unrealisierten Gewinn/Verlust inkl. echter Kosten, hält die **volle Transaktionshistorie** und liefert Portfolio-Aggregate als Input für das Risikomanagement. Es entsteht ausschliesslich aus den Ausführungsergebnissen des Kauf-/Verkaufsmoduls; das Depot-Dashboard ist eine reine Anzeige-Schicht darüber und verändert keine Trading-Logik.

## Main Success Scenario   <!-- Buchung eines Fills bis zum aktualisierten Bestand -->

1. Das Modul empfängt vom Kauf-/Verkaufsmodul ein Ausführungsergebnis (Fill): Titel-Identität, Anlageklasse (1–11), Richtung (Kauf/Verkauf), Menge, Fill-Preis, tatsächliche Gebühren/Kosten, Arrival-Price, Zeitstempel, Handelswährung.
2. Bei einem **Kauf** legt es die Position an oder ergänzt sie: es nettet die Gebühren in die Kostenbasis und aktualisiert den Einstand nach der konfigurierten Methode (Default gleitender Durchschnitt). Beim Kauf werden zusätzlich Strategie, Zeithorizont, Exit-Regeln und die These an der Position hinterlegt (aus der Anlagestrategie-Box, via Ausführung).
3. Bei einem **Verkauf** bestimmt es den G/V-Anteil aus Verkaufspreis (abzüglich Gebühren) gegen die Kostenbasis, schreibt ihn als realisierten G/V fort und reduziert die Menge; bei Vollverkauf wird die Position geschlossen, ihre Historie bleibt erhalten.
4. Es schreibt den Fill unveränderlich in die Transaktionshistorie (append-only) und speichert je Trade Arrival-Price, Fill-Preis und die daraus berechnete realisierte Slippage für die Transaction-Cost-Analysis (TCA).
5. Es berechnet je offener Position den unrealisierten G/V gegen die aktuelle Bewertung (Live-Kurs via Socket) und trennt bei Fremdwährungspositionen den Kapital- vom Währungsgewinn (FX-Attribution, CHF-Basis).
6. Es aktualisiert die Portfolio-Aggregate: Gewichtung je GICS-Branche und je Anlageklasse sowie Cash-Quote, und stellt diese dem Risikomanagement bereit.
7. Es stellt dem Risikomanagement den Depot-Stand und der Depot-Überwachung Titel + Strategie + Exit-Regeln bereit.

## Alternative Flows

### A1: Teilverkauf mit gleitendem Durchschnitt (CH-Default)
- Beim Teilverkauf bleibt der Ø-Einstandspreis der Restposition **unverändert**; nur die Menge sinkt und der realisierte G/V wächst.

### A2: Einstand-Methode FIFO (optional, provisorisch)
- Ist FIFO konfiguriert, werden beim Teilverkauf die ältesten Anteile zuerst entnommen; der Ø-Einstandspreis der Restposition kann sich dadurch ändern.

### A3: Fremdwährungs-Trade (US-Broker, CHF-Basis)
- Fill in Fremdwährung: der G/V wird in Kapital- und Währungskomponente zerlegt, beide in CHF ausgewiesen (FX-Attribution).

### E1: Ausführungsergebnis unvollständig oder inkonsistent
- Fehlen Pflichtfelder (Menge, Fill-Preis, Kosten, Zeitstempel) oder ergäbe die Buchung eine negative Menge, wird der Fill nicht gebucht, sondern als fehlerhaft protokolliert; der bisherige Bestand bleibt unverändert.

## Acceptance-Kriterien

- **AC1** — Je Position führt das Modul mindestens: Titel-Identität, Menge, Einstandspreis, aktuelle Bewertung, Anlageklasse (1–11), GICS-Branche, Strategie, Zeithorizont, Exit-Regeln und die These. Fehlt beim Kauf eines dieser Attribute, wird die Position als unvollständig protokolliert und nicht stillschweigend akzeptiert.
- **AC2** — Der unrealisierte G/V je offener Position ist `(aktueller Preis − Ø-Einstandspreis) × gehaltene Menge`; der realisierte G/V je Verkauf ist `(Verkaufspreis − Ø-Einstandspreis) × verkaufte Menge`. Beide Werte sind je Position und aggregiert abrufbar.
- **AC3** — Tatsächliche Transaktionskosten (Gebühren/Kommissionen) werden in die Kostenbasis genettet: sie erhöhen die Kostenbasis beim Kauf und mindern den Erlös beim Verkauf, sodass der ausgewiesene G/V die echten Kosten enthält.
- **AC4** — Jeder Fill (Kauf wie Verkauf) wird als unveränderlicher Eintrag in einer append-only Transaktionshistorie festgehalten (Titel, Richtung, Menge, Fill-Preis, Kosten, Zeitstempel, Währung). Kein Eintrag wird nachträglich verändert oder gelöscht; ein Vollverkauf schliesst die Position, entfernt ihre Historie aber nicht. (Voraussetzung für Steuerauszug + Dashboard.)
- **AC5** — Die Einstand-Methode ist konfigurierbar; **Default ist gleitender Durchschnitt** (CH-Kontext, provisorisch, konfigurierbar). Bei gleitendem Durchschnitt bleibt der Ø-Einstandspreis der Restposition nach einem Teilverkauf unverändert (deckt A1); bei aktivierter FIFO-Option werden die ältesten Anteile zuerst entnommen (deckt A2).
- **AC6** — Für Positionen in Fremdwährung wird der G/V in eine Kapital- und eine Währungskomponente zerlegt und beide in CHF-Basiswährung ausgewiesen (FX-Attribution, deckt A3).
- **AC7** — Je Trade werden Arrival-Price (Kurs bei Signal/Order-Auslösung), Fill-Preis und die daraus berechnete realisierte Slippage gespeichert und als Grundlage der TCA je Trade und aggregiert abrufbar gemacht.
- **AC8** — Das Modul stellt Portfolio-Aggregate bereit: Gewichtung je GICS-Branche, Gewichtung je Anlageklasse und Cash-Quote; diese dienen als Input für die Risikoprüfung beim Kauf.
- **AC9** — Das Modul stellt dem Risikomanagement den Depot-Stand und der Depot-Überwachung je gehaltenem Titel Strategie + Exit-Regeln bereit (die beim Kauf fixierten Werte, unverändert über die Haltedauer).
- **AC10** — Ein unvollständiges oder inkonsistentes Ausführungsergebnis (fehlende Pflichtfelder oder resultierende negative Menge) wird nicht gebucht, sondern als fehlerhaft protokolliert; der bisherige Bestand bleibt unverändert (deckt E1).
- **AC11** — Das Depot-Dashboard ist eine reine Anzeige-Schicht: es liest ausschliesslich aus dem Depotmodul (Depot live, je Titel Kauf-Historie und laufendes Plus/Minus) und aus dem Socket-Live-Kurs-Zugriff (Cross-Cutting); es hält keine eigene Preisanbindung und verändert weder Bestand noch Trading-Logik.

- **AC12** — Die Fill→Position-Orchestrierung ist Sache dieses Moduls: es konsumiert das Ausführungsergebnis (inkl. Pflichtfeld `modus` und `order_id`) und schreibt Position + Transaktion im selben Modus; ein Fill ohne `modus` oder ohne auflösbare `strategie_id` (bei Kauf) wird nicht gebucht, sondern als fehlerhaft protokolliert (deckt E1). Simulierte Fills erzeugen ausschliesslich simulierte Positionen/Transaktionen.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace depot#AC<n>`.

## Verträge

- **Input (Ausführungsergebnis, vom Kauf-/Verkaufsmodul):** `{ titel_id, anlageklasse (1–11), gics_branche, richtung (kauf|verkauf), modus (echt|simuliert), menge, fill_preis, kosten (gebuehren), arrival_price, waehrung, zeitstempel, order_id }`; bei Kauf zusätzlich das beim Kauf fixierte Attribut-Bündel `{ strategie_id (Katalog-ID aus [[strategie-exit-regeln]]), zeithorizont, exit_regeln, these }` — die Strategie wird ausschliesslich über ihre Katalog-ID referenziert (keine Namens-Zuordnung; Anzeige-Name kommt aus dem Strategie-Katalog).
- **Mode-Isolation (← C-016, Datenmodell BR-113/BR-130):** `modus` ist Pflichtfeld; Positionen, Transaktionen und Aggregate werden strikt je Modus getrennt geführt. Ein simulierter Fill verändert nie einen Echt-Bestand (und umgekehrt); alle Ausgaben an Risikomanagement/Überwachung/Dashboard sind modus-gefiltert.
- **Position (interner Zustand):** `{ titel_id, anlageklasse, gics_branche, menge, ø_einstand, aktuelle_bewertung, strategie, zeithorizont, exit_regeln, these, realisierter_gv, unrealisierter_gv, fx_kapital_gv, fx_waehrungs_gv }`.
- **Transaktionshistorie (append-only):** Liste von `{ trade_id, titel_id, richtung, menge, fill_preis, arrival_price, slippage, kosten, waehrung, zeitstempel }`.
- **Output an Risikomanagement (Depot-Stand + Aggregate):** `{ positionen[], branchen_gewichtung{gics→anteil}, klassen_gewichtung{1..11→anteil}, cash_quote }`.
- **Output an Depot-Überwachung:** je Titel `{ titel_id, strategie, exit_regeln }`.
- **Bewertung:** aktuelle Kurse werden über den Socket-Live-Kurs-Zugriff bezogen (keine separate Preisanbindung).

## Edge-Cases & Fehlerverhalten

- Erster Kauf eines noch nicht gehaltenen Titels legt eine neue Position an; Nachkauf mittelt den Einstand gemäss konfigurierter Methode.
- Vollverkauf schliesst die Position (Menge 0), ihre Transaktionshistorie bleibt vollständig erhalten.
- Fehlt für eine offene Position ein aktueller Live-Kurs, wird der unrealisierte G/V als „nicht bewertbar" markiert statt mit einem veralteten Wert ausgewiesen.
- Gebühren-Netting muss sowohl in der Kostenbasis (Kauf) als auch im Erlös (Verkauf) greifen, damit die realisierte Slippage/Gebühr sauber erfasst ist.

## NFRs

- Die Transaktionshistorie ist vollständig und dauerhaft (Voraussetzung für den späteren CH-Steuerauszug und das Dashboard); Aggregate sind aus Positionen + Historie reproduzierbar (kein stiller Zustand ohne Herleitung).
- Bewertungsfrequenz (wie oft neu bewertet wird) ist konfigurierbar.

## Nicht-Ziele

- **CH-Steuerauszug** ist ein eigenes, geparktes Reporting-Modul (← C-004): es liest die Historie aus dem Depotmodul, ist aber nicht Teil dieser Spec.
- **Rebalancing-Trigger** aus dem Depot ist geparkt (später eigene regelbasierte Funktion in der Depotstrategie).
- Keine Order-Erzeugung, kein Kauf-/Verkaufsentscheid (das ist das Kauf-/Verkaufsmodul bzw. die Analyse-/Sizing-Module).
- Keine eigene Preis-/Datenanbindung im Dashboard (Live-Kurse ausschliesslich via Socket, Cross-Cutting).

## Abhängigkeiten

- Kauf-/Verkaufsmodul (`[[kauf-verkauf]]`) — liefert Ausführungsergebnisse (Fills).
- Risikomanagement (`[[risikomanagement]]`) — Empfänger von Depot-Stand + Portfolio-Aggregaten.
- Depot-Überwachung (`[[depot-ueberwachung]]`) — Empfänger von Titel + Strategie + Exit-Regeln.
- Socket-Live-Kurs-Zugriff (Cross-Cutting, ← C-020) — Bewertung und Dashboard-Kurse.
- GICS-Branchenschema (Branchen-Zuordnung je Titel) und Anlageklassen-Konfiguration (← C-006).
