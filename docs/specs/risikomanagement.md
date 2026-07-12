---
id: risikomanagement
title: Depotstrategie & Risikomanagement-Gate
status: active
version: 1
spec_format: use-case-2.0
area: handel
---

# Spec: Depotstrategie & Risikomanagement-Gate  (`risikomanagement`)

> Konzept-Herkunft: (← C-015)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Zwei zusammengehörige Bausteine: (a) die **Depotstrategie** als nutzerkonfiguriertes Grenzwert-Regelwerk fürs Gesamtdepot (Makro-Ebene) und (b) das **Risikomanagement-Gate**, das jeden geplanten **Kauf** gegen diese Grenzwerte und den aktuellen Depot-Stand prüft und ihn durchwinkt, runtersized oder blockiert. **Verkäufe umgehen das Gate immer** — ein Verkauf reduziert Risiko und darf nicht durch den Disposition-Effekt behindert werden.

## Main Success Scenario
1. Der Nutzer konfiguriert die Depotstrategie (Grenzwerte) oder wählt eines von drei Risikoprofil-Presets (konservativ / ausgewogen / offensiv).
2. Das Gate erhält eine geplante Kauf-Order (Titel + Grösse) samt Attributen von der Strategie-/Zeithorizont-Stufe.
3. Das Gate lädt den aktuellen Depot-Stand (bestehende Positionen, Gewichtungen, Cash) und die geltenden Grenzwerte.
4. Es prüft Klumpenrisiko, Korrelation zu bestehenden Positionen, Drawdown-Limits und den portfolio-weiten Kelly-Cap.
5. Es trifft einen Drei-Wege-Entscheid — durchwinken / runtersizen (deckeln) / blockieren — und reicht das Ergebnis an das Kauf-&-Verkaufsmodul weiter.

## Alternative Flows
### A1: Runtersizen (Deckelung)
- Würde die Order ein Limit überschreiten, kürzt das Gate sie auf das erlaubte Maximum (einfache Deckelung) und gibt die gedeckelte Order frei — **ohne** Rück-Durchlauf ins Position-Sizing.

### A2: Blockieren mit Warteliste
- Ist ein Limit bereits ausgeschöpft oder der Korrelations-/Klumpenwert zu hoch, wird der Kauf abgelehnt; der Titel kann optional auf eine Warteliste gesetzt werden.

### A3: Verkauf
- Ein Verkaufsauftrag durchläuft das Gate nicht — er wird ohne Grenzwert-Prüfung durchgelassen (harte Regel).

### E1: Kein Depot-Stand verfügbar
- Kann der Depot-Stand nicht geladen werden, trifft das Gate keinen Durchwink-Entscheid; der Kauf wird sicherheitshalber nicht freigegeben.

## Acceptance-Kriterien
- **AC1** — Die Depotstrategie ist ein nutzerkonfiguriertes Grenzwert-Regelwerk mit mindestens: max. Gewicht je Branche/Sektor (Schema GICS), max. Gewicht je Anlageklasse (der 11 Klassen), max. Einzelposition und Cash-Quote.
- **AC2** — Branchen-/Sektor-Grenzen werden über **alle** Positionen hinweg geprüft, nicht anhand der nominellen Anzahl Titel (versteckte Konzentration muss erkannt werden).
- **AC3** — Drei Risikoprofile (konservativ / ausgewogen / offensiv) existieren als Presets, die die Grenzwerte als Paket setzen; der Nutzer kann ein Preset wählen und einzelne Werte feinjustieren.
- **AC4** — Die Preset-Grenzwerte sind als **provisorische, konfigurierbare Defaults** hinterlegt: Einzelposition zwischen 2 % (konservativ) und bis 10 % (offensiv), Sektor/Branche max. 20 %, Anlageklasse Krypto 5–15 % (profilabhängig), Cash-Quote ~5 %.
- **AC5** — Das Risikomanagement-Gate greift **nur beim Kauf**; jeder Verkaufsauftrag umgeht das Gate vollständig und ungeprüft (harte Regel, deckt A3).
- **AC6** — Das Gate liefert je Kauf genau einen von drei Entscheiden: durchwinken (volle geplante Grösse), runtersizen (Deckelung auf erlaubtes Maximum, **kein** Rück-Durchlauf ins Position-Sizing) oder blockieren (deckt A1).
- **AC7** — Beim Blockieren kann der Titel optional auf eine Warteliste gesetzt werden (deckt A2).
- **AC8** — Das Gate prüft mindestens: Klumpenrisiko (Branchen-/Klassen-/Einzelpositions-Limits), Korrelation zu bestehenden Positionen, Drawdown-Limits und den portfolio-weiten Kelly-Cap.
- **AC9** — Die Korrelationsprüfung berücksichtigt Korrelation zu bestehenden Positionen, sodass ein weiterer Titel eines bereits stark vertretenen Korrelations-Clusters gedeckelt oder blockiert werden kann, auch wenn das nominelle Sektorlimit noch nicht erreicht ist; wenn verfügbar wird Stress-Korrelation (oder ein konservativer Aufschlag) statt Normalphasen-Korrelation verwendet.
- **AC10** — Der portfolio-weite Kelly-Cap begrenzt das Gesamt-Exposure; der Default ist als **provisorischer, konfigurierbarer** Wert von 20–30 % Gesamt-Exposure hinterlegt.
- **AC11** — Das Gate bezieht seine Limits ausschliesslich aus der Depotstrategie und definiert keine eigenen Grenzwerte.
- **AC12** — Kann der aktuelle Depot-Stand nicht geladen werden, gibt das Gate den Kauf nicht frei (deckt E1).

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace risikomanagement#AC<n>`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC ≥ 1 deckender Test).

## Verträge
- **Input:** geplante Kauf-Order (Titel, Anlageklasse, Grösse, Attribute) von [[strategie-exit-regeln]]; Grenzwerte aus der Depotstrategie; Depot-Stand (Positionen, Gewichtungen, Cash) vom Depotmodul.
- **Output:** Gate-Entscheid an das Kauf-&-Verkaufsmodul: `{ entscheid: durchwinken | deckeln | blockieren, freigegebene_groesse, begruendung, warteliste?: bool }`.
- **Depotstrategie-Konfiguration:** `{ profil: konservativ|ausgewogen|offensiv, max_einzelposition, max_sektor (GICS), max_anlageklasse[1..11], cash_quote, kelly_cap_gesamt }` — alle Werte konfigurierbar, Presets als Startpakete.

## Edge-Cases & Fehlerverhalten
- Geplante Order = 0 oder negativ → keine Freigabe.
- Korrelations-Daten nicht verfügbar → das Gate arbeitet konservativ (Aufschlag/Deckelung) statt die Korrelationsprüfung zu überspringen.
- Order genau am Limit → gilt als eingehalten (durchwinken), Überschreitung → deckeln.
- Bedingtes Zulassen («kaufen nur wenn etwas anderes reduziert wird») ist Rebalancing und hier bewusst nicht implementiert.

## NFRs
- Der Gate-Entscheid ist deterministisch und ohne LLM-Beteiligung (Order-Pfad-Regel des Konzepts).
- Alle als «(Default, provisorisch)» gekennzeichneten Bandbreiten sind konfigurierbar und im Simulationsmodus kalibrierbar.

## Nicht-Ziele
- Kein Rebalancing (geparkt) — keine verkaufsauslösenden Grenzwert-Reaktionen bei Kursdrift.
- Kein Gesamt-Drawdown-Kill-Switch — die Kill-Switch-Schwelle ist offen und gehört in [[betriebssicherung]].
- Keine Positionsgrössen-Neuberechnung (das ist Position-Sizing; das Gate deckelt nur).

## Offene Punkte (aus dem Konzept übernommen)
- Korrelations-Messung: Datenquelle und Zeitfenster (Stress- vs. Normalphase) — offen.
- Warteliste-Mechanik bei Blockade (wann/wie erneut geprüft) — offen.
- Gesamt-Drawdown-Kill-Switch-Schwelle — offen (→ [[betriebssicherung]]).

## Abhängigkeiten
- Vorgelagert: [[strategie-exit-regeln]] (geplante Kauf-Order), Depotmodul (Depot-Stand), Position-Sizing (Kelly-Basis).
- Nachgelagert: [[ausfuehrung-paper]] (Kauf-&-Verkaufsmodul).
- Konfiguration: Depotstrategie-Presets (Bereich Konfiguration).
