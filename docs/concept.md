# Konzept — ki-investment

> **Schicht 1 von 3** (Konzept → Detailkonzept → Spezifikation). Das **WARUM & WAS**, sprach-/paradigma-unabhängig. Ändert selten. Source of Truth — der Code ist nachgelagert.
>
> Quelle: Obsidian-Vault `300 Projekte/KI Investment` (Ingest 2026-07-12 via /agent-flow:from-notes; IDEA-Anker siehe Abschnittsüberschriften). Präzedenz-Regel aus dem Stufe-a-Katalog: **neuere Detailnotiz schlägt ältere Hauptnotiz** (a-3); unvalidierte «⚠️ IN PRÜFUNG»-Recherche-Werte werden als **vorläufige Defaults** geführt und im Simulationsmodus kalibriert (a-2) — sie sind unten mit *(Default, provisorisch)* markiert.

## C-001 Problem & Vision (← IDEA-027, IDEA-028)

Semi-professionelle Anleger können Nachrichten, Marktdaten und Kennzahlen über viele Anlageklassen nicht kontinuierlich und diszipliniert auswerten — Entscheidungen fallen ad hoc, Exits werden in Euphorie/Panik neu verhandelt, Chancen werden verpasst. Die App ist eine **vollautomatische Investment-Engine**, die eigenständig Nachrichten und Marktdaten scannt, KI-gestützte Analysen über 11 Anlageklassen und 5 Analysekategorien fährt und daraus Kauf-/Verkaufsentscheide ableitet — **hybrid**: autonom oder mit Nutzerbenachrichtigung. Sie ist als Entscheidungsunterstützung und Lern-/Hobby-System konzipiert, ausdrücklich **nicht** als «Gelddruckmaschine» (PoC-Gesamturteil).

## C-002 Nutzer & Kontext (← IDEA-027, IDEA-028)

- **Zielgruppe:** Semi-Profis und erfahrene Anleger; Erstnutzer ist der Owner selbst (CH-Kontext, Investitionsvolumen ~70k CHF).
- **Kontext Schweiz:** Steuer-Safe-Harbor (ESTV-Kreisschreiben Nr. 36, gewerbsmässiger Wertschriftenhandel) ist bewusst **geparkt**, aber Bedingung vor Live-Schaltung; CHF-Basiswährung → FX-Attribution nötig bei US-Brokern.
- **Anlagehorizont:** konfigurierbar (9 Zeithorizont-Stufen, siehe C-014).
- **Kostenrahmen Daten:** MVP mit kostenlosen Quellen (SEC Form 4, Reddit, Polymarket, FRED, Wirtschaftskalender) ~CHF 0; volle Coverage ~CHF 75–175/Mo.

## C-003 Ziele (← IDEA-027, IDEA-028)

- Durchgängige Pipeline von Datenaufnahme bis Order-Ausführung (Paper-Modus), in der **jede Zahl aus einer API stammt und jede Entscheidung ein deterministisches Modul trifft** (LLM-Grounding, C-008).
- Disziplinierte Exits: Exit-Regeln werden **beim Kauf** definiert und nie beim Verkauf neu verhandelt (empirisch begründet: Disposition-Effekt, Shefrin & Statman 1985, Odean 1998).
- Messbare Vertrauensbildung: Validierungs-Metriken (PSR, MinTRL) beantworten «ab wann glauben wir dem System?» statt Bauchgefühl.
- Betriebssicherheit ab Start: Kill-Switch («flatten & halt»), Heartbeat, Drawdown-Alerts, Secrets-Management, getrennte Paper-/Live-Zugänge.
- Live-Schaltung erst wenn: (a) Paper-Ergebnisse über MinTRL-orientierten Zeitraum plausibel, (b) Betriebssicherung getestet, (c) Steuerfrage geklärt.

## C-004 Nicht-Ziele (← IDEA-028, IDEA-019)

- **Kein Hochfrequenz-/Scalping-Handel** (für Retail unrentabel; FINMA-/Steuer-Risiko).
- **Kein klassisches historisches Backtesting als eigenes System** — ersetzt durch Modus-Schalter «echt/simuliert» + zweistufiges Validierungs-Gate (C-012).
- **Keine Microservices zum Start** — modularer Monolith; Microservices erst bei echtem Bedarf.
- **Kein Live-Trading im MVP** — Start ausschliesslich im Paper-Modus.
- **Rebalancing geparkt** (später eigene regelbasierte Funktion in der Depotstrategie).
- **Steuerreport CH geparkt** (später: automatischer Steuerauszug aus dem Depotmodul).
- Keine Steuer-, Rechts- oder Anlageberatung.

## C-005 MVP & Stufenplan (← IDEA-028, IDEA-004; Katalog a-1)

**MVP (beschlossen im Stufe-a-Katalog):** PoC-Empfehlung **plus Krypto** —
- Anlageklassen-Toggle-Default: **Aktien + ETFs + Krypto** aktiv, alle übrigen inaktiv.
- **Ein Broker: Interactive Brokers (Paper-Modus)** — ausgereifte API, CHF-Basis, Paper- und Live-Modus über dieselbe API. Ob Krypto über IBKR oder eine separate Anbindung (z. B. Kraken) läuft, klärt die Spec-Phase; im Paper-Modus ist Krypto ohne Broker simulierbar.
- Dünne End-to-End-Pipeline (Datenaufnahme → Analyse → Sizing → Risiko → Paper-Order → Depot).
- Datenqualitäts-Layer und Betriebssicherung (Kill-Switch, Monitoring) **von Anfang an**.
- LLM nur als Analyse-Assistent (nie im Order-Pfad, C-008).
- **Lernschleife (Research + Validierungs-Gate) bewusst später** (Stufe 2) — die Gate-Metriken (PSR/MinTRL) für die Paper-Bewährung sind davon unabhängig und gehören in den MVP.

Erweiterung folgt der Prio-Empfehlung der Anlageklassen-Notiz (Stufe 2: Obligationen, aktive Fonds, Immobilien; Stufe 3: Rohstoffe, Infrastruktur, FX, Derivate) — als Empfehlung, nicht als technische Grenze (C-006).

## C-006 Anlageklassen als Konfiguration (← IDEA-004, IDEA-007)

**11 Anlageklassen** (verbindliche Nummerierung): 1 Aktien · 2 ETFs · 3 Cash/Geldmarkt · 4 Obligationen · 5 Aktive Fonds · 6 Immobilien · 7 Kryptowährungen · 8 Rohstoffe · 9 Infrastrukturfonds · 10 FX · 11 Derivate.

Beschlossen (Designentscheidung Nr. 8, 10.07.2026): Anlageklassen sind **Feature-Toggles in den Einstellungen**, nicht Code-Grenzen. Regeln:
- Alle 11 Klassen erscheinen als an/aus-Auswahl; Prio-Spalte ist Empfehlung für die Aktivierungsreihenfolge.
- Inaktive Klassen erzeugen **keinerlei Verarbeitung und keine Datenkosten** (Suchkriteria, Datenquellen-Abfrage, Analyse, Handelsplattformen, Depotstrategie respektieren den Toggle).
- **Deaktivierung mit offenen Positionen:** keine neuen Käufe, aber Überwachung + Exits bleiben aktiv («ein Toggle darf niemals dazu führen, dass eine gehaltene Position blind wird»).
- Je Klasse existiert eine vollständige Methodentabelle (Methoden mit festem Ranking 1–10 je Klasse) und eine Kategorien-Gewichtung (Summe 100 %) — Quelle: Anlageklassen-Notiz, wird 1:1 als Konfigurationsdaten übernommen.

## C-007 Analyse-Framework: 5 Kategorien, Score, Spinnennetz (← IDEA-001, IDEA-004)

- **5 Analysekategorien:** Fundamental, Technisch, Qualitativ, Makro, Risiko & Quantitativ (CFA/BlackRock-konform; Sentiment gehört zur Technischen Analyse, Geopolitik zu Makro, ESG materialitätsbasiert zu Qualitativ).
- **Formeln:** Kategorie-Score = Σ(Methodenscore × Ranking) / Σ(Ranking); Gesamtscore = Σ(Kategorie-Score × Kategoriegewicht je Anlageklasse). Methodenscore (1–10) wird je Analyse neu vergeben; Ranking ist fix je Anlageklasse (quartalsweise Review).
- **Score-Schwellen (0–10):** ≥ 8 KAUF · 6–7.9 BEOBACHTEN · 4–5.9 HALTEN · 2–3.9 REDUZIEREN · < 2 VERKAUF.
- **Sanity-Cap:** Gesamtsignal maximal «Halten», wenn der Risiko-Score < 3 ist.
- **Visualisierung:** Spinnennetzdiagramm mit 5 Achsen (eine je Kategorie), Fläche = Kaufstärke; optional zweite halbtransparente Fläche für den historischen Durchschnitt.
- *(Default, provisorisch)* Signal-Aggregation in der Datenzuführung: robuste z-Scores (gekappt ±3), Kategorie-Mittelung, horizontabhängige Gewichte, Sentiment mit Decay (Halbwertszeit 7–30 Tage) — zu kalibrieren im Simulationsmodus.
- Offen: Kalibrierung der Score-Schwellen je Anlageklasse; Behandlung fehlender Methodenscores (No-Evidence-No-Trade greift bei ganzen Kategorien, C-008).

## C-008 LLM-Grounding (Querschnitt, beschlossen v1.0) (← IDEA-016)

Grundprinzip: **«Das LLM darf denken, aber nicht behaupten und nicht handeln.»** Fünf Sicherungen:
1. **Grounding-Pflicht:** jede Zahl kommt als strukturierter Input aus Datenquellen/Finanz-Plugins; jede Kennzahl im Output trägt Quellen-ID + Timestamp.
2. **Strukturierter Output:** JSON nach festem Schema (Score je Kategorie 0–10, Fakten mit Quellen-IDs, Begründung); Schema-Validierung als erster Halluzinationsfilter.
3. **Zahlen-Cross-Check (deterministisch):** jede referenzierte Zahl wird gegen die Originalquelle geprüft; Abweichung über Toleranz → Analyse verworfen + geloggt.
4. **No-Evidence-No-Trade:** fehlt die Datengrundlage einer Kategorie, wird der Titel übersprungen — nie durch LLM-Schätzung ersetzt.
5. **LLM nie im Order-Pfad:** Buy-Signal, Sizing, Risiko-Gate, Order-Ausführung sind deterministische Module (harte Architektur-Regel).

Monitoring: Halluzinations-KPI aus dem Cross-Check; **> 2 % Faktenabweichung → Alarm**, LLM wird aus der Entscheidungskette genommen. Offen: Toleranzschwellen je Kennzahl-Typ, JSON-Schema-Detail.

## C-009 Dateneingang: Socket, Datenquellen, geteilte Abfrage (← IDEA-023, IDEA-009, IDEA-008)

- **Socket** = technische Anbindungsschicht: ein Adapter je Quelle, normalisiert in ein einheitliches internes Schema (Metadaten: Quelle, Timestamp, Anlageklassen-Tag 1–11, Qualitätsindikator); kapselt Auth und Rate-Limits. Abruffrequenzen: Polymarket/Whale Alert/Nansen 30–60 s · Reddit 15–30 min · SEC 2 h · FRED täglich.
- **12 Datenquellen in 5 Kategorien** (Equity Insider & Fundamentals · Retail Sentiment & Social · Blockchain & Crypto · ETFs & Fonds · Makro & Anleihen) mit dokumentierter Qualität, Frequenz, Kosten und Anlageklassen-Zuordnung. Reddit-Sentiment nur bei retail-getriebenen Klassen (Aktien, Krypto) — nicht bei Obligationen/FX.
- **Datenquellen-Abfrage** = zentrales, geteiltes Modul (DRY) mit einer Schnittstelle für drei Konsumenten (Suchkriteria, Depot-Suchkriterien, Research); liefert je Titel ein einheitliches Signal-Bündel inkl. Liquidität + Volatilität.
- *(Default, provisorisch)* Scheduler + leichte Message-Queue (Queue-of-Work, Token-Bucket je Quelle), Bronze/Silver/Gold-Schichtung der Rohdaten (Point-in-Time/Replay), Exponential Backoff, Dead-Letter-Queue, Recalculation-Window 2–3 Tage für revisionsbehaftete Quellen (FRED).
- Offen: einheitliches Titel-Datenschema; Caching-Strategie; Quellen für Immobilien/Rohstoffe.

## C-010 Kandidatensuche & Depot-Überwachung (← IDEA-024, IDEA-010)

- **Suchkriteria (neue Titel):** profilbasierte Filter **je Anlageklasse** (kein Einheitsfilter). *(Default, provisorisch)* RVOL > 2× als wichtigstes Kriterium («non-negotiable»), kombiniert mit Katalysator/News; Low-Float-, RSI-, Gap-Kriterien je Profil; Querschnitt: Liquiditäts-Mindestschwelle + Volatilitäts-Fenster; eventbasierter Scanner bevorzugt gegenüber periodischem Snapshot.
- **Depot-Suchkriterien (bestehende Titel):** sucht laufend Änderungen, die Exit-Regeln auslösen könnten. *(Default, provisorisch)* Keyword-/Ereignis-Filter («Insolvenz», «Hack», «Übernahme», «Gewinnwarnung», «Downgrade»), Marktkontext-Normierung (−10 % an einem −8 %-Markttag ≠ −10 % an flachem Tag), Alert-Fatigue-Leitplanke (> 10 Alerts/Tag = zu sensibel).
- Beide erhalten validierte Regeländerungen **nur** über das Validierungs-Gate (C-012).

## C-011 Analysepfade: Einstieg (Buy) und Wiederbewertung (Sell) (← IDEA-003, IDEA-002)

Zwei bewusst getrennte Pfade (Idea-Generation vs. Position-Monitoring):
- **Analyse neue Titel:** bewertet Kandidaten mit dem Framework (C-007); Buy-Signal bei Score ≥ 8 → an Position-Sizing.
- **Analyse bestehende Titel:** prüft **gegen die beim Kauf definierten Exit-Regeln** (kein «moving the goalposts»); Leitfrage: «Würden wir die Position heute kaufen, wenn wir sie nicht hielten?» Ausgabe: Sell-Signal mit Dringlichkeit **Hard-Exit** (These fundamental gebrochen: Hack, Betrug, Delisting, Insolvenz → sofort) oder **Soft-Exit** (Verschlechterung → gestaffelt möglich) → an Exit-Sizing.
- *(Default, provisorisch)* Drei Auslöser-Kategorien je Position: Thesis-Breakpoint, Drawdown-Trigger (z. B. 20 % vom Hoch/10 % vom Einstand UND Underperformance → Review), Time-Box; Stop-Typ je Strategie (Value: fundamentaler Stop; Momentum: ATR-Trailing 2.5–3×; Buy-and-Hold: weiter Stop 25–30 % oder keiner).
- Offen: Operationalisierung Thesis-Bruch; Einordnung Time-Box in Hard/Soft; ATR-Multiplikator je Volatilitätsklasse.

## C-012 Lernschleife: Research + zweistufiges Validierungs-Gate (← IDEA-020, IDEA-025)

**Stufe 2 (nach MVP), Design aber beschlossen (v1.1, 10.07.2026):**
- **Research** analysiert Tagesgewinner («warum verpasst?») und liefert **nur Hypothesen** — nie direkte Regeländerungen (Overfitting-Gefahr, Bailey & López de Prado 2014).
- **Validierungs-Gate, Stufe A (historisch):** Mindest-Stichprobe ≥ 100 Trades · Walk-Forward mit 30-Tage-Embargo · Walk-Forward-Effizienz ≥ 0.5 · Deflated Sharpe Ratio mit **Trial-Registry** (jede getestete Variante wird gezählt, Abgelehntes archiviert, nie gelöscht).
- **Stufe B (Paper-Bewährung):** PSR ≥ 95 % gegen Benchmark-Sharpe 0; **MinTRL** wird laufend berechnet und angezeigt (Sharpe 1.0 ≈ 3 Jahre, Sharpe 0.5 ≈ 11 Jahre Monatsdaten).
- **Ampel:** 🟢 beide Stufen bestanden → Regel in Suchkriteria · 🟡 A bestanden, B läuft → nur Paper-Modus · 🔴 durchgefallen → mit Begründung archiviert.
- Grundsatz: «Keine Regel geht ohne Zahlen durch.» Offen: Point-in-Time-Historie für nachrichtengetriebene Signale; Automatik vs. Freigabe-Vorschlag bei Grenzfällen.

## C-013 Sizing: Position-Sizing & Exit-Sizing (← IDEA-018, IDEA-013)

- **Position-Sizing (Mikro, «wie viel kaufen»):** *(Default, provisorisch)* Fractional Kelly (f* = (b·p − q)/b), Half-Kelly Standard, Quarter-Kelly für volatile Klassen (Krypto) und als Obergrenze gem. PoC; hartes Positions-Cap zusätzlich (1–2 % Risiko je Trade); Kelly erst scharf schalten, wenn ≥ 50–100 Trades im Simulationsmodus gesammelt sind — vorher konservative Fixed-Fractional-Regel. Pre-Trade-Kosten (Courtage + Spread + geschätzte Slippage) reduzieren oder verwerfen den Trade.
- **Exit-Sizing (Verkaufsseite, umgeht bewusst das Risikomanagement):** Dringlichkeit ist wichtigstes Kriterium (Hard → sofort alles, Market/Stop-Market; Soft → gestaffelt, Limit-Default). *(Default, provisorisch)* Limit deckt ≥ 95 % der Ausführungen, Market nur Notfall (Slippage-Tax 3–8 %/Jahr); TWAP für grosse Positionen relativ zum Volumen; Tranchen 3–4, zeit- oder ereignisbasiert.
- Offen: Score→Win-Wahrscheinlichkeit-Mapping für Kelly; Mindest-Ordergrösse (Mindestgebühr-Effekt); Korrelations-/Regime-Bewusstsein im Kelly (Multi-Asset-Kelly oder harte Caps — PoC P3).

## C-014 Strategie, Zeithorizont & Exit-Regeln beim Kauf (← IDEA-005, IDEA-006, IDEA-026)

- **18 Anlagestrategien in 4 Clustern** (Passiv/Regelbasiert → MVP · Aktiv-Fundamental → Stufe 2 · Aktiv-Technisch/Makro → Stufe 3 · Professionell/Algorithmisch → Stufe 4, nur qualifizierte Nutzer). **9 Zeithorizont-Stufen** (Hochfrequenz bis Generationell) mit Transaktionskosten-Relevanz und Break-Even-Anforderungen. Strategie und Zeithorizont sind **unabhängige Dimensionen**.
- **Beim Kauf** werden je Titel fixiert: Strategie, Zeithorizont, Exit-Regeln (Stop-Loss, Take-Profit, Thesis-Invalidierung, optional Time-Box) + die These selbst. Diese Attribute begleiten die Position bis zum Verkauf (beschlossen, extern bestätigt).
- *(Default, provisorisch)* Default-Exit-Set je Strategie/Klasse (ATR-basierte Stops statt fixer %, Tabelle aus der Notiz als Startpunkt).
- Offen: Strategie-Wahl je Titel (automatisch aus Signalquelle vs. Nutzerprofil); Zeithorizont global vs. je Position; Suitability-/Risikoprofil-Erhebung; FINMA-Frequenzgrenze.

## C-015 Depotstrategie & Risikomanagement (← IDEA-012, IDEA-021)

- **Depotstrategie (Makro-Regelwerk, nutzerkonfiguriert):** Grenzwerte für Branche/Sektor, Anlageklasse, Einzelposition, Cash-Quote. *(Default, provisorisch)* CFA-nahe Presets — Einzelposition 2 % (streng) bis 5–10 % (offensiv), Sektor max. 20 %, Klassen-Limits risikoprofilabhängig (z. B. Krypto 5–15 %), Cash ~5 %; drei Risikoprofile (konservativ/ausgewogen/offensiv) als Pakete; GICS als Branchen-Schema. Die widersprüchlichen Alt-Beispiele (10 %-Einzelposition, 40 % Krypto) sind durch diese Bandbreiten ersetzt; Finalisierung in der Spec.
- **Risikomanagement (nur beim Kauf, Portfolio-Wächter):** Drei-Wege-Entscheid **durchwinken / runtersizen (einfache Deckelung, kein Rück-Durchlauf) / blockieren**; prüft Klumpenrisiko, **Korrelation zu bestehenden Positionen (Stress-Korrelation!)**, Drawdown-Limits, portfolio-weiten Kelly-Cap *(Default, provisorisch: 20–30 % Gesamt-Exposure)*. **Verkäufe laufen bewusst daran vorbei** (Verkauf reduziert Risiko; verhindert Disposition-Effekt).
- Offen: Korrelations-Messung (Quelle, Zeitfenster); Warteliste-Mechanik bei Blockade; Gesamt-Drawdown-Kill-Switch-Schwelle.

## C-016 Ausführung: Kauf/Verkauf, Modus-Schalter, Handelsplattformen (← IDEA-015, IDEA-014)

- **Kauf- & Verkaufsmodul:** führt gebilligte Käufe (vom Risikomanagement) und Verkaufsaufträge (vom Exit-Sizing) aus. **Modus-Schalter «echt / simuliert»** — Paper-Trading mit Live-Daten und virtuellem Geld ersetzt separates Backtesting; derselbe Code-Pfad, nur anderer Endpunkt/Key. Modus global und je Anlageklasse überschreibbar. Misst **Arrival-Price-Slippage** je Trade (Post-Trade-TCA). Fehlerbehandlung (Teilfills, Rejects, Timeouts) ist Kernanforderung («häufigste Verlustquelle ist Logikfehler, nicht der Markt»).
- **Hybrid-Modus (Katalog a-4):** MVP im Paper-Modus **voll autonom**, Benachrichtigungen informativ; Bestätigungspflicht-Modus ist späteres Feature des hybriden Betriebs.
- **Handelsplattformen (Referenzdaten):** Plattform-Stammdaten je Anlageklasse (Courtage, Mindestgebühr, Spread) liefern erwartete Kosten an Sizing und Ausführung. **MVP-Broker: Interactive Brokers (Paper)** (Katalog a-1); Krypto-Anbindung (IBKR vs. Kraken) klärt die Spec-Phase. Vor dem Bau prüfen, welche Klassen wirklich API-handelbar sind.
- *(Default, provisorisch)* Mindest-Bewährung im Sim-Modus vor Echtgeld: 30–50 Trades / 3–6 Monate; Live-Start mit 10–20 % des Kapitals.
- Offen: Fill-/Slippage-Modell der Simulation; FINMA-Frequenzgrenze; CH-Steuern/Stempelabgabe bei US-Brokern.

## C-017 Depot & Reporting (← IDEA-011, IDEA-022)

- **Depotmodul = Wahrheit über den Bestand:** je Position Titel, Menge, Einstand, Bewertung, Anlageklasse, Branche (GICS), Strategie, Zeithorizont, Exit-Regeln; realisierter/unrealisierter G/V inkl. echter Kosten; Portfolio-Aggregate (Gewichtungen, Cash-Quote) als Basis der Risikoprüfung; **volle Transaktionshistorie** (Voraussetzung für Steuerauszug + Dashboard). *(Default, provisorisch)* Einstand-Methode: gleitender Durchschnitt als CH-Default, FIFO optional; FX-Attribution (Kapital- vs. Währungsgewinn); Arrival-Price/Fill je Trade für TCA.
- **Live-/Verlaufs-Ansicht (Depot-Dashboard):** reine Anzeige-Schicht (verändert keine Trading-Logik) — Depot live, je Titel Kauf-Historie und laufendes Plus/Minus; Live-Kurse via Socket (Cross-Cutting-Zugriff, keine separate Preisanbindung).
- **Steuerauszug CH:** eigenes Reporting-Modul (geparkt, C-004) — liest Historie aus dem Depotmodul.

## C-018 Plugin-Integration & Automatisierungsgrade (← IDEA-017)

Je Analyse-Methode ist dokumentiert, ob sie 🟢 AUTO (Plugin/Connector liefert Score-Basis), 🟡 TEIL (Rohdaten, Scoring manuell) oder 🔴 BUILD (Eigenbau) ist. Kern-Erkenntnis für die Umsetzung: **Technische Analyse (0×AUTO, 7×BUILD) und Risiko & Quantitativ (11×BUILD) sind Eigenbau-Pflicht** (Python: ta-lib/pandas-ta, scipy/numpy — Volatilität, Beta, Sharpe/Sortino, VaR, Max Drawdown, Monte Carlo); Fundamental/Qualitativ sind über Finanz-Plugins/Connectoren stark abgedeckt; Makro über FRED (kostenlos) + optional LSEG (Enterprise-Lizenz — Verfügbarkeit für Privatanleger **offen**, Phase-2-Risiko). Drei Phasen: (1) MVP mit vorhandenen Plugins + Freiquellen, (2) LSEG-Erweiterung, (3) Eigenbau-Skills.

## C-019 Betriebssicherung & Datenqualität (← IDEA-028, IDEA-019)

Pflichtbausteine ab MVP (PoC-Priorität 1–2):
- **Datenqualitäts-Layer:** Point-in-Time-Datenhaltung, Survivorship-Bias-Vermeidung, Corporate-Actions-Adjustierung, Datenvalidierung.
- **Betriebssicherung:** Kill-Switch («flatten & halt»), Heartbeat, Drawdown-Alerts, Secrets im Vault, getrennte Paper-/Live-Zugänge.
- **Simulations-Realismus:** eigenes Slippage-/Spread-Modell auf Paper-Fills (Paper-Fills sind sonst zu optimistisch).
- Später (Stufe 3/KI-Reife): Feature Store, Model Registry, Drift-Monitoring.

## C-020 Architekturprinzip (← IDEA-007, IDEA-028, IDEA-019)

- **Modularer Monolith** mit lose gekoppelten Modulen (klare Input/Output-Verträge je Modul, einzeln entwickel-/test-/austauschbar); entspricht dem LEAN-Referenzmuster (Universe Selection → Alpha → Portfolio Construction → Risk → Execution).
- **DRY:** Datenquellen-Abfrage als ein geteiltes Modul; Live-Kurs-Zugriff als Cross-Cutting-Service des Sockets.
- **16 Kernmodule** entlang des Datenflusses: Socket · Suchkriteria · Datenquellen-Abfrage · Research · Validierungs-Gate · Depot-Suchkriterien · Analyse neue Titel · Analyse bestehende Titel · Position-Sizing · Exit-Sizing · Anlagestrategie+Zeithorizont · Depotstrategie · Risikomanagement · Kauf-&-Verkaufsmodul · Handelsplattformen · Depotmodul — plus Anzeige-/Reporting-Schicht (C-017) und Querschnitte (C-008, C-019).
- Architektur extern validiert (QuantConnect/LEAN, Freqtrade, NautilusTrader, QuantStart): keine Grundsatz-Lücke; die identifizierten Praxis-Lücken sind in C-012/C-013/C-019 eingearbeitet.

## Scope-Übersicht

MVP (siehe C-005) → Stufe 2 (Lernschleife, Obligationen/Fonds/Immobilien, Bestätigungs-Modus) → Stufe 3 (Rohstoffe/Infrastruktur/FX/Derivate, LSEG, ML-Infrastruktur) → Live-Schaltung nur unter den Bedingungen aus C-003. Die Details je Capability stehen in `docs/specs/<feature>.md`.
