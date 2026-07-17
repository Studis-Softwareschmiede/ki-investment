---
id: strategie-exit-regeln
title: Strategie, Zeithorizont & Exit-Regeln beim Kauf
status: active
version: 1
spec_format: use-case-2.0
area: handel
---

# Spec: Strategie, Zeithorizont & Exit-Regeln beim Kauf  (`strategie-exit-regeln`)

> Konzept-Herkunft: (← C-014)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Legt **beim Kauf** je Position die begleitenden Handels-Attribute verbindlich fest: die Anlagestrategie (aus 18 Strategien in 4 Clustern), den Zeithorizont (9 Stufen) und die Exit-Regeln (Stop-Loss, Take-Profit, Thesis-Invalidierung, optional Time-Box) samt der dokumentierten Kauf-These. Diese Attribute begleiten die Position bis zum Verkauf und werden danach nicht mehr neu verhandelt — das verhindert das emotionsgetriebene «Verschieben der Ziele» (Disposition-Effekt).

## Main Success Scenario
1. Das Modul erhält vom Position-Sizing die geplante Ordergrösse für einen Titel.
2. Es bestimmt (aus Signalquelle bzw. Nutzerprofil) die Anlagestrategie und den Zeithorizont für genau diese Position.
3. Es leitet aus dem Default-Exit-Set der gewählten Strategie/Anlageklasse die konkreten Exit-Regeln ab (Stop-Loss, Take-Profit, Thesis-Invalidierung, optional Time-Box).
4. Es hinterlegt die Kauf-These als gespeicherten, später prüfbaren Text.
5. Es fixiert das Attribut-Bündel (Strategie, Zeithorizont, Exit-Regeln, These) unveränderlich an der Position und reicht die annotierte Kauf-Order an das Risikomanagement weiter.

## Alternative Flows
### A1: Strategie liegt zusammen mit dem Signal vor
- Ist der Position bereits eine Strategie zugeordnet (aus der Signalquelle), wird diese übernommen; sonst greift die Zuordnung aus dem Nutzerprofil bzw. der zur Anlageklasse passende Default.

### A2: Time-Box nicht anwendbar
- Für Strategien/Klassen ohne Time-Box (z. B. Index/Buy-and-Hold) bleibt die Time-Box leer; alle anderen Exit-Regel-Kategorien bleiben Pflicht.

### E1: Versuch der Attribut-Änderung nach dem Kauf
- Jeder Schreibzugriff auf Strategie, Zeithorizont, Exit-Regeln oder These einer bereits gekauften Position wird abgelehnt; der Versuch wird protokolliert und der bestehende Wert bleibt unverändert.

### E2: Nur-MVP-Cluster-Verletzung
- Wird eine Strategie ausserhalb des für die aktuelle App-Stufe freigeschalteten Clusters angefordert, wird die Zuordnung abgelehnt und das Modul fällt auf eine im MVP-Cluster erlaubte Strategie zurück bzw. meldet einen Fehler.

## Acceptance-Kriterien
- **AC1** — Beim Kauf wird je Position genau ein Bündel fixiert, das mindestens enthält: Anlagestrategie, Zeithorizont, Exit-Regeln (Stop-Loss, Take-Profit, Thesis-Invalidierung, optional Time-Box) und die Kauf-These als Text.
- **AC2** — Die wählbare Strategie stammt aus dem Katalog von 18 Strategien in 4 Clustern (Passiv/Regelbasiert, Aktiv-Fundamental, Aktiv-Technisch/Makro, Professionell/Algorithmisch). Im MVP sind nur Strategien des Clusters «Passiv/Regelbasiert» (u. a. Index, DCA, Dividende, Factor/Smart Beta) auswählbar; eine Anforderung ausserhalb des freigeschalteten Clusters wird abgelehnt (deckt E2).
- **AC3** — Der Zeithorizont stammt aus genau 9 Stufen (1 Hochfrequenz, 2 Scalping, 3 Daytrading, 4 Swing-Trading, 5 Position-Trading, 6 Mittelfristig, 7 Langfristig, 8 Buy-and-Hold, 9 Generationell); zu jeder Stufe sind Transaktionskosten-Relevanz und Break-Even-Anforderung als Attribut hinterlegt.
- **AC4** — Strategie und Zeithorizont sind unabhängige Dimensionen: dieselbe Strategie ist mit unterschiedlichen Zeithorizonten kombinierbar, ohne dass eine Kombination systemseitig blockiert wird.
- **AC5** — Nach dem Kauf sind Strategie, Zeithorizont, Exit-Regeln und These der Position unveränderlich: jeder Änderungsversuch wird abgelehnt und protokolliert, der gespeicherte Wert bleibt erhalten (harte Regel, deckt E1).
- **AC6** — Beim Kauf werden immer drei Exit-Regel-Kategorien dokumentiert: (1) Thesis-Breakpoint (Bedingung, unter der der Kaufgrund entfällt), (2) Drawdown-/Stop-Trigger, (3) Time-Box; die Time-Box darf leer sein, Thesis-Breakpoint und Stop-Trigger nicht (deckt A2).
- **AC7** — Stop-Regeln sind je Strategie/Klasse als ATR-basierte Vorgaben (Vielfaches des ATR) statt fixer Prozentwerte hinterlegt; ein fixer Prozent-Stop ist nicht der Default (Whipsaw-Vermeidung bei volatilen Titeln).
- **AC8** — Ein Default-Exit-Set je Strategie/Anlageklasse ist als **provisorischer, konfigurierbarer Default** vorhanden und liefert beim Kauf die Startwerte gemäss folgender Tabelle: Value (Aktien) → fundamentaler Stop (These bricht), Take-Profit bei Zielwert, Time-Box ~3 Jahre; Growth/Momentum → ATR-Trailing-Stop 2.5–3× ATR, gestaffelter/kein fixer Take-Profit; Index/Buy-and-Hold → weiter Stop 25–30 % oder keiner, keine Time-Box; Krypto → weiter ATR-Trailing-Stop plus Teilgewinne; Daytrade/Swing → technischer Stop (unter Support − Puffer) plus enges Zeitfenster.

> **AC8-Präzisierung (S-038):** Die Tabelle deckt namentlich nur 5 Kategorien ab, nicht alle 18 Strategien/11 Klassen (siehe „Offene Punkte": „Tabelle als Startpunkt"). `app.db.exit_regel_ableitung.klassifiziere_exit_kategorie` ordnet zu wie folgt: **Krypto** (Anlageklasse Kryptowährungen) dominiert unabhängig von Strategie/Horizont; sonst **Daytrade/Swing** bei Zeithorizont Daytrading/Swing-Trading; sonst **Value** bei Strategie „Value"; **Growth/Momentum** bei Strategie „Growth"/„Momentum"; **Index/Buy-and-Hold** bei Strategie „Index". Für jede Strategie ohne einen dieser Namens-/Klassen-/Horizont-Treffer (z. B. DCA, Dividende, Factor/Smart Beta — weitere MVP-Strategien ohne eigene Tabellenzeile) gilt der **generische AC7-Default**: ATR-Trailing-Stop (kein fixer Prozent-Stop), kein Take-Profit-Default, keine Time-Box. Für „Index/Buy-and-Hold" (Prozent-Spanne 25–30 %) ist der angewandte Default-Wert der Spannen-Mittelpunkt **27.5 %** (Spec nennt keinen Einzelwert). „Enges Zeitfenster" (Daytrade/Swing) hat konkret: Daytrading → 1 Handelstag, Swing-Trading → 10 Handelstage (~2 Wochen) — beides provisorische, konfigurierbare Defaults (Spec nennt nur „eng", keinen Zahlenwert), analog zur AC11-Präzisierung in `docs/specs/ausfuehrung-paper.md`.

- **AC9** — Der ATR-Multiplikator ist als provisorischer, konfigurierbarer Default je Volatilitätsklasse hinterlegt (Richtwert: ruhige Titel 2–2.5×, volatile Titel 3–4×).

> **AC9-Präzisierung (S-038):** Der als Default angewandte Punktwert je Volatilitätsklasse ist der Bandbreiten-Mittelpunkt: **2.25×** (ruhig, Spanne 2.0–2.5×), **3.5×** (volatil, Spanne 3.0–4.0×) — Spec nennt nur die Spanne, keinen Einzelwert; beide Grenzwerte bleiben zusätzlich als Referenz in der Konfiguration (`atr_multiplier_default.multiplikator_min`/`_max`) erhalten.
- **AC10** — Die gespeicherte Kauf-These ist maschinell auslesbar, sodass die nachgelagerte «Analyse bestehende Titel» sie später gegen die aktuelle Lage prüfen kann.
- **AC11** — Die annotierte Kauf-Order (Ordergrösse plus fixiertes Attribut-Bündel) wird an das Risikomanagement weitergegeben; kein Kauf durchläuft dieses Modul ohne vollständig gesetzte Attribute (Strategie, Zeithorizont, Exit-Regeln, These).

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace strategie-exit-regeln#AC<n>`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC ≥ 1 deckender Test).

## Verträge
- **Input:** geplante Ordergrösse (Titel, Anlageklasse 1–11, Menge/Betrag) vom Position-Sizing; Strategie-/Horizont-Auswahl aus Signalquelle bzw. Nutzerprofil.
- **Output:** annotierte Position/Kauf-Order an das Risikomanagement mit Feldern:
  - `strategie` (eine der 18, Cluster-Zuordnung), `zeithorizont` (Stufe 1–9),
  - `exit_regeln`: `{ stop_typ, stop_parameter (z. B. ATR-Multiplikator), take_profit, thesis_invalidierung, time_box (optional) }`,
  - `these` (Text), `fixiert_am` (Zeitstempel), `unveraenderlich` (true nach Kauf).
- **Konfigurationsdaten (provisorische Defaults):** Default-Exit-Set-Tabelle je Strategie/Klasse; ATR-Multiplikatoren je Volatilitätsklasse; Freischaltung der Strategie-Cluster je App-Stufe (MVP = Passiv/Regelbasiert).

## Edge-Cases & Fehlerverhalten
- Fehlende oder unvollständige Exit-Regeln (kein Stop-Trigger oder keine Thesis-Invalidierung) verhindern die Weitergabe an das Risikomanagement — der Kauf wird nicht annotiert freigegeben.
- Anforderung einer nicht freigeschalteten Strategie → Ablehnung/Fallback (E2).
- Änderungsversuch nach Kauf → Ablehnung + Protokoll (E1).
- ATR nicht berechenbar (zu wenig Kurshistorie) → das Modul kennzeichnet den Stop-Parameter als unbestimmt und behandelt die Exit-Regel als unvollständig.

## NFRs
- Die Fixierung ist deterministisch und ohne LLM-Beteiligung (Order-Pfad-Regel aus dem Konzept: kein LLM im Entscheidungs-/Order-Pfad).
- Alle als «(Default, provisorisch)» gekennzeichneten Werte sind zur Laufzeit konfigurierbar und im Simulationsmodus kalibrierbar.

## Nicht-Ziele
- Keine Ausführung von Trailing-Stops zur Laufzeit (nur Definition hier; Ausführung im Exit-Sizing/Kauf-&-Verkaufsmodul).
- Keine automatische Neubewertung oder Anpassung der Attribute nach dem Kauf.
- Keine Erhebung des Nutzer-/Risikoprofils (Suitability) — offen, ausserhalb dieser Spec.
- Keine FINMA-Frequenz-/Suitability-Prüfung.

## Offene Punkte (aus dem Konzept übernommen)
- Strategie-Wahl je Titel: automatisch aus der Signalquelle vs. aus dem Nutzerprofil — offen.
- Zeithorizont global (für alle Positionen) vs. je Position einstellbar — offen.
- Finalisierung des Default-Exit-Sets je Strategie/Klasse (Tabelle als Startpunkt).

## Abhängigkeiten
- Vorgelagert: Position-Sizing (Ordergrösse).
- Nachgelagert: [[risikomanagement]] (annotierte Kauf-Order); später Depotmodul (Speicherung), «Analyse bestehende Titel» (Prüfung gegen These/Exit-Regeln).
- ATR-Berechnung: Technik-Skill (Eigenbau gemäss Konzept C-018).
