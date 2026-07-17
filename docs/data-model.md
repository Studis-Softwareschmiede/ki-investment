db_dialect: postgres

# Datenmodell — ki-investment

> **Teil des Detailkonzepts (DB-Domäne).** Geschrieben vom `dba`, bindend für den `coder`. Der `coder` setzt es 1:1 in **alembic**-Migrationen um (Dialekt: PostgreSQL 17) — hier **kein SQL**, nur das Modell (Entitäten, Typen, Constraints, Indizes, Partitionierung, Retention).
>
> Quelle: `docs/concept.md` (C-001…C-020) + Original-Notizen (Depotmodul, Validierungs-Gate, Datenquellen, Datenquellen-Abfrage, Socket, LLM-Grounding, Anlageklassen, Handelsplattformen, Strategie/Zeithorizont). Typen sind **sprachneutral** beschrieben; die PostgreSQL-Idiome (Enum vs. CHECK, `TIMESTAMPTZ`, `NUMERIC`, `JSONB`, deklarative Partitionierung) wählt der `coder` beim Umsetzen.
>
> **BR-Namensraum:** Datenvalidierende Regeln dieses Modells starten bei **BR-100** (fortlaufend), um Kollisionen mit dem verhaltensbezogenen `architecture.md`-Katalog (BR-001…) zu vermeiden. Specs referenzieren via `(→ BR-NNN)`, Tests taggen `#BR-NNN`.
>
> **Mode-Isolation (Querschnitt):** Nahezu alle transaktionalen Entitäten tragen `mode ∈ {echt, simuliert}` (C-016 Modus-Schalter). `echt`- und `simuliert`-Daten werden in Aggregaten **nie** vermischt (→ BR-130). Der Paper-Modus ist MVP-Default (C-005).

---

## Konventionen

- **Primärschlüssel:** synthetische `UUID` (PG17: `gen_random_uuid()`; bei PG18-Upgrade `uuidv7()` für Index-Lokalität, `sql/R09`) — außer **fachlich fixe Referenz-IDs** (Anlageklasse 1–11, siehe `asset_class`).
- **Zeit:** alle Zeitstempel `TIMESTAMPTZ` (UTC), Basiswährung **CHF** (C-002).
- **Geld/Kurse:** `NUMERIC(20,8)` (exakt, nie Float) — deckt Krypto-Nachkommastellen.
- **Prozente/Scores:** `NUMERIC(6,3)`; Scores 0–10, Gewichte 0–100.
- **Enums:** als PostgreSQL-`ENUM`-Typ **oder** `TEXT + CHECK` — der `coder` entscheidet; das Modell nennt die zulässige Wertemenge.
- **Audit:** `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` auf allen Tabellen; `updated_at` nur auf mutierbaren.
- **Secrets:** API-Keys/OAuth-Tokens werden **nie** in DB-Spalten gespeichert (→ BR-126); nur ein `vault_ref` (Zeiger auf Secrets-Manager).
- **Kein Mandanten-Kontext / kein RLS:** Single-Owner-System (C-002, ein Nutzer = der Owner). RLS ist bewusst **nicht** Teil dieses Modells; wird Multi-User später eingeführt, ist RLS pro Tabelle nachzurüsten (Enforcement-Spalte `owner_id` + Policy) — als expliziter ADR-Punkt für die Spec-Phase vermerkt.

---

## ER-Überblick (Mermaid)

```mermaid
erDiagram
    asset_class ||--o{ analysis_method : "hat Methoden"
    asset_class ||--o{ category_weight : "gewichtet Kategorien"
    asset_class ||--o{ data_source_asset_class : "wird beliefert von"
    asset_class ||--o{ platform_asset_class : "handelbar auf"
    asset_class ||--o{ instrument : "klassifiziert"
    asset_class ||--o{ portfolio_class_limit : "begrenzt durch"
    asset_class ||--o{ rule_hypothesis : "Anlageklasse je Hypothese"

    data_source ||--o{ data_source_asset_class : "deckt ab"
    data_source ||--o{ market_data_bronze : "liefert roh"

    trading_platform ||--o{ platform_asset_class : "bepreist"

    instrument ||--o{ market_data_silver : "hat Signale (Ziel-Relation nach Folge-Story — instrument_id noch nicht umgesetzt, S-024-Präzisierung §2)"
    instrument ||--|| instrument_signal_bundle : "aktuelles Bündel"
    instrument ||--o{ analysis_result : "wird analysiert"
    instrument ||--o{ position : "gehalten als"

    analysis_result ||--o{ analysis_category_score : "Score je Kategorie"
    analysis_result ||--o{ analysis_fact : "geerdete Fakten"
    analysis_result ||--o{ hallucination_log : "Cross-Check"

    risk_profile ||--o{ portfolio_strategy : "prägt"
    portfolio_strategy ||--o{ portfolio_class_limit : "je Klasse"

    strategy_cluster ||--o{ strategy : "Cluster-Freischaltung"
    strategy ||--o{ position : "Strategie je Titel"
    time_horizon ||--o{ position : "Horizont je Titel"

    position ||--|| exit_rule : "beim Kauf fixiert"
    position ||--o{ order : "erzeugt"
    position ||--o{ transaction : "bucht"
    position ||--o{ risk_check_log : "geprüft durch"
    order ||--o{ trade_fill : "gefüllt durch"
    instrument ||--o{ depot_fill_dedup : "dedupliziert Fills für"
    market_data_bronze ||--o{ market_data_silver : "normalisiert zu"
    market_data_silver ||--o{ market_data_gold : "angereichert zu"

    portfolio_snapshot ||--o{ portfolio_weight : "gewichtet"

    rule_hypothesis ||--o{ trial_registry : "Varianten"
    trial_registry ||--o{ gate_result : "Gate-Ergebnis"
```

---

## 1 · Konfigurations- & Stammdaten

### `asset_class` — Anlageklasse (C-006, verbindliche Nummerierung 1–11)
| Feld | Typ | Constraint |
|---|---|---|
| id | SMALLINT | PK, **fix 1–11** (CHECK `id BETWEEN 1 AND 11`), keine synthetische UUID |
| name | TEXT | NOT NULL, UNIQUE |
| prio_stufe | TEXT | NOT NULL, CHECK ∈ {MVP, Stufe2, Stufe3} |
| aktiv | BOOLEAN | NOT NULL, DEFAULT (id ∈ {1,2,7} → true sonst false; C-005 MVP-Default Aktien+ETFs+Krypto) |
| retail_driven | BOOLEAN | NOT NULL, DEFAULT false (nur 1 Aktien, 7 Krypto → true; steuert Reddit-Sentiment, → BR-123) |

### `analysis_category` — 5 Analysekategorien (C-007)
| Feld | Typ | Constraint |
|---|---|---|
| code | TEXT | PK, CHECK ∈ {fundamental, technisch, qualitativ, makro, risiko_quant} |
| name | TEXT | NOT NULL |
| ist_risiko | BOOLEAN | NOT NULL, DEFAULT false (nur `risiko_quant` → true; Basis für Sanity-Cap BR-106) |

### `category_weight_version` — Versionsregister Kategoriegewichte (C-006, AC10; S-018, löst den S-004-Platzhalter ab)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| is_current | BOOLEAN | NOT NULL, DEFAULT true — Partial-UNIQUE-Index (`WHERE is_current`) erzwingt genau eine aktuell gültige Version (→ BR-133) |
| note | TEXT | optionale Änderungsnotiz (NFR „nachvollziehbar auditierbar") |

### `category_weight` — Kategoriegewicht je Anlageklasse (C-006, C-007; versioniert seit S-018/AC10)
| Feld | Typ | Constraint |
|---|---|---|
| asset_class_id | SMALLINT | FK → asset_class.id |
| category_code | TEXT | FK → analysis_category.code |
| config_version_id | UUID | FK → category_weight_version.id, NOT NULL |
| weight_pct | NUMERIC(6,3) | NOT NULL, CHECK `0 ≤ weight_pct ≤ 100` |
| — | — | PK (asset_class_id, category_code, config_version_id) · Σ je (Klasse, Version) = 100 (→ BR-101, jetzt versions-scope) |

> **S-018/AC10-Präzisierung:** die vormalige `config_version SMALLINT`-Tag-Spalte (S-004, reine Wert-Markierung ohne Historie, siehe Migration `2da446925bbc`) ist per Folge-Migration durch `config_version_id` (FK → `category_weight_version`) ersetzt — jede Änderung an den Gewichten legt eine **neue** `category_weight_version`-Zeile an; eine Version ist ein **vollständiger Snapshot** aller 11×5 Gewichte (append-only, alte Version bleibt unverändert erhalten, kein UPDATE bestehender Zeilen). „Aktuell gültig" = `category_weight_version.is_current = true`. Der deferred Σ=100-Constraint-Trigger (BR-101) prüft ab dieser Migration je `(asset_class_id, config_version_id)`, nicht mehr nur je `asset_class_id` (sonst würden mehrere Versionen gemeinsam summiert).

### `analysis_method_version` — Versionsregister Methodentabellen (C-006, C-018, AC10; S-018)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() |
| is_current | BOOLEAN | NOT NULL, DEFAULT true — Partial-UNIQUE-Index (`WHERE is_current`) erzwingt genau eine aktuell gültige Version (→ BR-133) |
| note | TEXT | optionale Änderungsnotiz |

> Versioniert unabhängig von `category_weight_version` (kein gemeinsamer Versionszähler über beide Konfig-Domänen — eine Methodentabellen-Änderung bumpt nicht automatisch die Kategoriegewicht-Version und umgekehrt). Eine künftige `analysis_result`-Zeile referenziert bei Bedarf beide IDs getrennt (Folge-Story, sobald `analysis_result` existiert, siehe §11).

### `analysis_method` — Methodentabelle je Klasse (C-006, C-007, C-018; versioniert seit S-018/AC10, Review-Hinweis AC11)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| asset_class_id | SMALLINT | FK → asset_class.id, NOT NULL |
| category_code | TEXT | FK → analysis_category.code, NOT NULL |
| config_version_id | UUID | FK → analysis_method_version.id, NOT NULL |
| code | TEXT | NOT NULL (z.B. F1, T1, Q1, M1, R1) |
| kurzbezeichnung | TEXT | NOT NULL |
| beschreibung | TEXT | |
| nutzen | TEXT | |
| ranking | SMALLINT | NOT NULL, CHECK `1 ≤ ranking ≤ 10` (fix je Klasse, quartalsweise Review; → BR-102) |
| automation_grade | TEXT | CHECK ∈ {AUTO, TEIL, BUILD} (C-018 Plugin-Integrationsgrad) |
| last_reviewed_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() — Basis des AC11-Quartals-Hinweises (→ BR-132); ein Review aktualisiert **nur** diesen Zeitstempel, `ranking` bleibt unverändert (kein automatisches Anpassen, Spec-Nicht-Ziel) |
| — | — | UNIQUE (asset_class_id, code, config_version_id) — append-only je Version |

> **Seed (S-018 Iteration 2 — vollständig):** die Seed-Migration (`8f183aee9753`) befüllt ALLE 11 Klassen × (bis zu) 5 Analysekategorien mit 190 Methoden-Zeilen, 1:1 transkribiert aus der Konzept-Quelle "KI Investment – Anlageklassen.md" (Obsidian-Vault, C-006/C-007/C-018) — `docs/specs/anlageklassen-config.md` (Verträge) selbst nennt weiterhin nur das Aktien/Fundamental-Beispiel, die vollständigen Listen liegen ausschliesslich in der Konzept-Quelle. Zwei dokumentierte Mapping-Sonderfälle (kein Erfinden, keine stille Annahme):
> - **Cash/Geldmarkt × Technisch:** die Konzept-Quelle führt dort keine Methodentabelle ("nicht anwendbar", 0 %-Gewicht laut AC8) — `(asset_class_id=3, category_code='technisch')` bleibt bewusst OHNE Seed-Zeilen; eine leere Methodentabelle für diese Kombination ist zulässig (kein Constraint verlangt ≥ 1 Zeile je (Klasse, Kategorie)).
> - **Aktive Fonds:** die Quelle führt "Performance / Quantitativ (30 %)" (Codes P1-P5) als erste Kategorie — gemappt auf den kanonischen `fundamental`-Slot (5 kanonische Kategorien gelten unverändert, AC6; 30 % = exakt das Aktive-Fonds-Fundamental-Gewicht aus AC8).
>
> Ranking-Werte werden beim Migrations-Laden gegen 1–10 validiert (`_baue_analysis_method_seed()`); ein Quell-Wert ausserhalb löst einen harten Abbruch aus (kein stiller Clamp).

### `data_source` — Datenquellen-Registry (C-009, 12 Quellen in 5 Kategorien)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| name | TEXT | NOT NULL, UNIQUE |
| kategorie | TEXT | CHECK ∈ {equity_fundamentals, retail_social, blockchain_crypto, etf_fonds, makro_anleihen} |
| qualitaet | TEXT | CHECK ∈ {niedrig, mittel, mittel_hoch, hoch, sehr_hoch} |
| frequenz_sekunden | INTEGER | NOT NULL (Abrufintervall, Socket-Scheduling; 30–86400) |
| kostenmodell | TEXT | (frei/free_tier/pro/institutionell) |
| kosten_monatlich_chf | NUMERIC(10,2) | DEFAULT 0 |
| zugangsart | TEXT | (REST/WebSocket/OAuth) |
| rate_limit | TEXT | (z.B. „10 req/sec") |
| vault_ref | TEXT | Zeiger auf Secret (kein Klartext-Key, → BR-126) |
| aktiv | BOOLEAN | NOT NULL, DEFAULT false (MVP: nur kostenlose Quellen aktiv) |

### `data_source_asset_class` — Quelle ↔ Anlageklasse (M:N, C-009 Abdeckung)
| Feld | Typ | Constraint |
|---|---|---|
| data_source_id | UUID | FK → data_source.id |
| asset_class_id | SMALLINT | FK → asset_class.id |
| — | — | PK (data_source_id, asset_class_id) |

### `trading_platform` — Handelsplattform-Stammdaten (C-016)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| name | TEXT | NOT NULL, UNIQUE (z.B. Interactive Brokers, Kraken) |
| gebuehrenmodell | TEXT | (fix/gestaffelt/prozentual) |
| mindestgebuehr_chf | NUMERIC(10,2) | DEFAULT 0 |
| api_handelbar | BOOLEAN | NOT NULL, DEFAULT true (nicht jede Klasse ist API-fähig — vor Bau prüfen) |
| vault_ref | TEXT | Broker-Credentials-Zeiger (→ BR-126) |
| paper_supported | BOOLEAN | NOT NULL, DEFAULT true (Modus-Schalter simuliert, C-016) |

### `platform_asset_class` — Plattform ↔ Klasse + Kosten (M:N, C-016)
| Feld | Typ | Constraint |
|---|---|---|
| platform_id | UUID | FK → trading_platform.id |
| asset_class_id | SMALLINT | FK → asset_class.id |
| courtage_pct | NUMERIC(6,4) | Courtage je Order (bekannt) |
| typ_spread_pct | NUMERIC(6,4) | typischer Spread (halb bekannt) |
| bevorzugt | BOOLEAN | DEFAULT false (bevorzugte Plattform je Klasse) |
| — | — | PK (platform_id, asset_class_id) |

> **Prozent-Konvention (S-017, AC10/AC11-Präzisierung):** `courtage_pct` und
> `typ_spread_pct` sind — analog `category_weight.weight_pct` — Prozent-Zahlen
> (z. B. `0.0500` = 0.05 %), **keine** Anteile 0–1. Konsumenten (z. B.
> `app.db.trading_platform.berechne_erwartete_kosten`) teilen den
> gespeicherten Wert vor der Multiplikation mit einem Order-Wert durch 100.
> Diese Story seedt bewusst KEINE konkreten Zeilen für `trading_platform`/
> `platform_asset_class` — weder Konzept noch Spec nennen belegte
> Courtage-/Spread-/Mindestgebühr-Zahlen für Interactive Brokers je
> Anlageklasse; die Referenzdaten sind Konfiguration und werden außerhalb
> dieser Story mit tatsächlich bekannten Konditionen befüllt (z. B. im
> Rahmen von S-046, der Broker-Adapter-Story).

### `instrument` — Titel / handelbares Instrument (C-007, C-017)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| symbol | TEXT | NOT NULL |
| name | TEXT | NOT NULL |
| asset_class_id | SMALLINT | FK → asset_class.id, NOT NULL |
| gics_sector | TEXT | (GICS-Branche; Pflicht für Depotstrategie-Prüfung → BR-128) |
| gics_industry | TEXT | |
| currency | TEXT | NOT NULL, CHECK 3-stelliger ISO-Code (FX-Attribution → BR-129) |
| liquiditaet | NUMERIC(20,8) | Liquiditätskennzahl (ADV/RVOL; aus Datenquellen-Abfrage) |
| volatilitaet | NUMERIC(10,6) | annualisierte Volatilität (Exit-Sizing, ATR-Klasse) |
| — | — | UNIQUE (symbol, asset_class_id) |

### `risk_profile` — Risikoprofil (C-015, 3 Presets)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| name | TEXT | NOT NULL, CHECK ∈ {konservativ, ausgewogen, offensiv} |

### `portfolio_strategy` — Depotstrategie / Makro-Grenzwerte (C-015)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| risk_profile_id | UUID | FK → risk_profile.id, NOT NULL |
| max_einzelposition_pct | NUMERIC(6,3) | NOT NULL, CHECK 0–100 (2 % streng … 5–10 % offensiv) |
| max_sektor_pct | NUMERIC(6,3) | NOT NULL (z.B. 20 %) |
| cash_quote_ziel_pct | NUMERIC(6,3) | NOT NULL (~5 %) |
| gesamt_exposure_cap_pct | NUMERIC(6,3) | NOT NULL (portfolio-weiter Kelly-Cap 20–30 %) |
| aktiv | BOOLEAN | NOT NULL, DEFAULT false (genau eine aktive → partieller Unique-Index) |

### `portfolio_class_limit` — Klassen-Limit je Depotstrategie (C-015)
| Feld | Typ | Constraint |
|---|---|---|
| portfolio_strategy_id | UUID | FK → portfolio_strategy.id |
| asset_class_id | SMALLINT | FK → asset_class.id |
| max_klasse_pct | NUMERIC(6,3) | NOT NULL (z.B. Krypto 5–15 %) |
| — | — | PK (portfolio_strategy_id, asset_class_id) |

### `strategy_cluster` — Strategie-Cluster + App-Stufen-Freischaltung (C-014, S-037-Präzisierung)
| Feld | Typ | Constraint |
|---|---|---|
| code | TEXT | PK, CHECK ∈ {passiv_regelbasiert, aktiv_fundamental, aktiv_technisch_makro, professionell_algo} |
| name | TEXT | NOT NULL, UNIQUE |
| freigeschaltet | BOOLEAN | NOT NULL, Spalten-Default `false`; die Differenzierung je Cluster (nur `passiv_regelbasiert` → `true`) erfolgt ausschliesslich über die Seed-INSERT-Werte, nicht über den Spalten-Default — **Konfigurationsdatum** (provisorischer, konfigurierbarer Default, zur Laufzeit per UPDATE änderbar ohne Code-/Migrations-Änderung), MVP-Seed deckt Spec-AC2 (nur Passiv/Regelbasiert freigeschaltet) |

> **S-037-Präzisierung:** `docs/specs/strategie-exit-regeln.md` AC2 verlangt eine "Cluster-Freischaltung je App-Stufe" als "Konfigurationsdatum (provisorischer, konfigurierbarer Default — NFR: zur Laufzeit konfigurierbar)". Die ursprüngliche Modellierung (nur `strategy.cluster` als CHECK-Wertemenge) bildete das nicht ab — analog zum bestehenden Boolean-Toggle-Muster (`asset_class.aktiv`, `data_source.aktiv`) wird die Freischaltung hier als eigene, laufzeit-updatebare Stammdatentabelle geführt statt als Codekonstante.

### `strategy` — Anlagestrategie (C-014, 18 Strategien / 4 Cluster)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| name | TEXT | NOT NULL, UNIQUE |
| cluster | TEXT | NOT NULL, FK → strategy_cluster.code (ersetzt die vormalige eigenständige CHECK-Wertemenge — Werte bleiben identisch: passiv_regelbasiert, aktiv_fundamental, aktiv_technisch_makro, professionell_algo) |
| stufe | TEXT | NOT NULL, CHECK ∈ {MVP, Stufe2, Stufe3, Stufe4} |

### `time_horizon` — Zeithorizont (C-014, 9 Stufen)
| Feld | Typ | Constraint |
|---|---|---|
| id | SMALLINT | PK, CHECK 1–9 (Hochfrequenz … Generationell) |
| name | TEXT | NOT NULL, UNIQUE |
| transaktionskosten_relevanz | TEXT | NOT NULL — Transaktionskosten-Relevanz je Stufe (z.B. KRITISCH, HOCH, MITTEL, NIEDRIG, MINIMAL), 1:1 aus Konzept-Notiz "KI Investment – Zeithorizonte" |
| break_even_anforderung | TEXT | NOT NULL — Break-Even-Anforderung je Stufe (z.B. "0,5–1 % pro Trade"), 1:1 aus derselben Notiz |

> **S-037-Präzisierung:** AC3 verlangt explizit zwei separate Attribute ("Transaktionskosten-Relevanz und Break-Even-Anforderung") statt des vormaligen einzelnen `break_even_hinweis`-Feldes — dieses Feld war noch in keiner Migration umgesetzt (greenfield), daher reine Präzisierung ohne Migrationspfad für einen bereits existierenden Spaltennamen.

### `exit_default_set` — Default-Exit-Set je Kategorie (C-014, S-038, provisorisch/konfigurierbar)
| Feld | Typ | Constraint |
|---|---|---|
| kategorie | TEXT | PK, CHECK ∈ {value_aktien, growth_momentum, index_buy_and_hold, krypto, daytrade_swing} — 5 Kategorien der Spec-Tabelle `docs/specs/strategie-exit-regeln.md` AC8 |
| stop_typ | TEXT | NOT NULL, CHECK ∈ {fundamental, atr_trailing, fix_pct, technisch, keiner} — bewusst eigenes Enum, nicht identisch mit `exit_rule.stop_typ` (siehe Spalten-Kommentar Modell) |
| stop_parameter_hinweis | TEXT | NOT NULL — Freitext-Beschreibung des Stop-Mechanismus je Kategorie |
| stop_parameter_pct | NUMERIC(6,3) | nur bei `stop_typ = fix_pct` gesetzt (aktuell nur `index_buy_and_hold`, Default 27.5 — Spannen-Mittelpunkt 25–30 %, AC8-Präzisierung) |
| take_profit_hinweis | TEXT | Freitext, kann `NULL` sein |
| time_box | INTERVAL | optional (nur `value_aktien` gesetzt: ~3 Jahre) |

> **S-038-Präzisierung:** Konfigurationsdatum analog `strategy_cluster` — zur Laufzeit per `UPDATE` änderbar (NFR "zur Laufzeit konfigurierbar"). Die Zuordnung Strategie/Anlageklasse/Zeithorizont → `kategorie` (inkl. generischem Fallback für Strategien ohne eigene Zeile) ist App-Logik (`app.db.exit_regel_ableitung.klassifiziere_exit_kategorie`), nicht Teil dieser Tabelle.

### `atr_multiplier_default` — ATR-Multiplikator je Volatilitätsklasse (C-014, S-038, provisorisch/konfigurierbar)
| Feld | Typ | Constraint |
|---|---|---|
| volatilitaetsklasse | TEXT | PK, CHECK ∈ {ruhig, volatil} |
| multiplikator | NUMERIC(5,2) | NOT NULL — angewandter Default-Wert (Spannen-Mittelpunkt: 2.25 ruhig, 3.5 volatil, AC9-Präzisierung) |
| multiplikator_min | NUMERIC(5,2) | NOT NULL — Referenzwert (Spec-Spanne, nicht Teil der Ableitungsrechnung) |
| multiplikator_max | NUMERIC(5,2) | NOT NULL — Referenzwert (Spec-Spanne, nicht Teil der Ableitungsrechnung) |

### `system_setting` — globale Systemeinstellungen (C-016)
| Feld | Typ | Constraint |
|---|---|---|
| key | TEXT | PK (z.B. `mode_global`) |
| value | JSONB | NOT NULL (`mode_global ∈ {echt, simuliert}`, per-Klasse-Override als Map) |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

---

## 2 · Marktdaten-Schichtung Bronze / Silver / Gold (C-009, C-019)

### `market_data_bronze` — immutable Rohdaten, Point-in-Time, Replay (C-009, C-019)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | Teil PK |
| data_source_id | UUID | FK → data_source.id, NOT NULL |
| source_event_id | TEXT | NOT NULL (stabile Event-ID der Quelle — Idempotenz, → BR-122) |
| asset_class_tag | SMALLINT | FK → asset_class.id (Metadaten-Tag 1–11) |
| symbol | TEXT | (falls titelbezogen) |
| payload | JSONB | NOT NULL (unveränderte Rohantwort) |
| quality_indicator | TEXT | (Socket-Qualitätsmetadatum) |
| observed_at | TIMESTAMPTZ | NOT NULL (fachlicher Zeitpunkt der Datenquelle, Point-in-Time) |
| ingested_at | TIMESTAMPTZ | NOT NULL DEFAULT now() (Aufnahmezeit — **Partitionsschlüssel**) |
| — | — | **PK (id, ingested_at)** · **append-only**, kein UPDATE/DELETE (→ BR-121) |

> **BR-122-Präzisierung (S-022, AC9/AC10):** `UNIQUE (data_source_id, source_event_id)` ist als
> **physischer** Index NICHT umsetzbar — er würde AC10 (rückwirkende Revision erzeugt eine
> zusätzliche Point-in-Time-Version statt Überschreiben) strukturell verhindern, und auf einer
> `RANGE`-partitionierten Tabelle müsste jeder Unique-Index zusätzlich den Partitionsschlüssel
> (`ingested_at`) enthalten — was die Duplikaterkennung selbst aushebeln würde (jede Zeile trägt
> ein frisches `ingested_at`). Idempotenz (AC9) + Versionierung (AC10) werden daher zweischichtig
> **verhaltensseitig** durchgesetzt statt über einen Unique-Constraint: App-Layer
> (`app/db/bronze.py::record_observation` — identischer Inhalt zur zuletzt bekannten Version
> derselben `(data_source_id, source_event_id)` → idempotenter No-Op; abweichender Inhalt → neue
> Zeile) sowie ein DB-seitiger BEFORE-INSERT-Trigger als zweite Sicherung (Migration
> `cfdd83ba9a2c_create_market_data_bronze_bronze_layer.py`), analog zum BR-101-Muster bei
> `category_weight`. `(data_source_id, source_event_id)` bleibt eine **logische**
> Ereignis-Identität über mehrere Versionen hinweg, kein physischer Unique-Key.
>
> **Nebenläufigkeits-Härtung (S-022, Iteration 2, empirisch gegen Postgres 17 gemessen):**
> unter READ COMMITTED sehen zwei parallele, noch nicht committete Transaktionen sich
> gegenseitig nicht — `record_observation()` erwirkt daher VOR der Lese-Prüfung eine
> `pg_advisory_xact_lock` je Ereignis-Identität, die konkurrierende Aufrufe serialisiert.
> Der DB-Trigger wirft bei einem trotzdem durchgeschlüpften Duplikat außerdem KEIN stilles
> `RETURN NULL` mehr (ORM-inkompatibel, siehe `.claude/lessons/coder.md`), sondern eine
> abfangbare Exception (SQLSTATE `unique_violation`), die `record_observation()` fängt und
> die massgebliche Zeile frisch nachlädt statt ein verwaistes ORM-Objekt zurückzugeben.

**Partitionierung:** deklarativ nach `RANGE (ingested_at)`, **monatliche** Partitionen (Zeitreihen, hohes Volumen). Partitionsschlüssel muss Teil von PK/Unique sein → daher `(id, ingested_at)`.

### `market_data_silver` — normalisierte, Corporate-Actions-adjustierte Werte (C-009, C-019; `docs/specs/datenqualitaet.md` AC3/AC6)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | Teil PK |
| bronze_id | UUID | Teil zusammengesetzter FK → `market_data_bronze(id, ingested_at)` — Referenz auf Bronze-Ursprung (Replay-Kette, Vertragsfeld `abgeleitet_aus: bronze_version`) |
| bronze_ingested_at | TIMESTAMPTZ | Teil derselben zusammengesetzten FK (Partitionsschlüssel-Pflicht bei FK auf partitionierte Tabelle) |
| data_source_id | UUID | FK → `data_source.id`, NOT NULL — denormalisiert aus der Bronze-Zeile (Iteration 2, Reviewer-Befund): `source_event_id` ist laut BR-122 nur gemeinsam mit `data_source_id` eine eindeutige Ereignis-Identität; ohne diese Spalte kann ein Rebuild/Delete-Scoping für eine Quelle silent Silver-Zeilen einer anderen Quelle löschen |
| source_event_id | TEXT | NOT NULL — Vertragsfeld `event_id`, aus der Bronze-Zeile übernommen (denormalisiert, vermeidet Partitions-übergreifenden Join für einfache Lookups) |
| symbol | TEXT | aus der Bronze-Zeile übernommen; fachlich nötig, um die passende Corporate-Actions-Historie je Titel zuzuordnen (AC6) — Ersatz für `instrument_id`, siehe Präzisierung unten |
| normalisierter_wert | NUMERIC(20,8) | NOT NULL — Vertragsfeld `normalisierter_wert` |
| einheit | TEXT | NOT NULL — Vertragsfeld `einheit` (AC3, einheitliches Format) |
| adjustierungs_info | JSONB | Vertragsfeld `adjustierungs_info` (AC6): JSON-Objekt mit angewandten Corporate-Actions (Typ, Wirksamkeitsdatum, Faktor je Aktion) + kumuliertem Faktor; `NULL`, wenn keine Adjustierung nötig war |
| observed_at | TIMESTAMPTZ | NOT NULL (Partitionsschlüssel, aus der Bronze-Zeile übernommen) |
| — | — | **PK (id, observed_at)**, RANGE-partitioniert monatlich. **UNIQUE (bronze_id, bronze_ingested_at, observed_at)** (`uq_market_data_silver_bronze_version`, Iteration 2): physisch möglich, weil `observed_at` für dieselbe Bronze-Version deterministisch identisch ist — schliesst zusammen mit einer App-seitigen Advisory-Lock (`app/db/silver.py`) die Nebenläufigkeits-Lücke bei `record_silver_observation()`. **Nicht** append-only (Unterschied zu Bronze/BR-121): bei einer rückwirkend gemeldeten Corporate Action wird die betroffene historische Reihe für Symbol/Quelle vollständig neu abgeleitet (bestehende Zeilen gelöscht, neu berechnete Zeilen eingefügt) — Bronze bleibt dabei unverändert (AC6-Edge-Case). |

> **Vertrag-Präzisierung (S-024, AC3/AC6):** Das ursprünglich hier notierte Schema
> (`instrument_id`, `signal_type`, `raw_value`, `z_score`, `decay_gewicht`) war auf die
> Sentiment-/Signal-Bündel-Nutzung der Datenquellen-Abfrage (`[[dateneingang]]`/S-021)
> zugeschnitten und deckte den in `docs/specs/datenqualitaet.md` definierten
> Silver-Datensatz-Vertrag (`{ event_id, normalisierter_wert, einheit, adjustierungs_info,
> abgeleitet_aus: bronze_version }`, AC3/AC6 — normalisierte, Corporate-Actions-
> adjustierte Werte) strukturell nicht ab (u.a. fehlten `einheit`/`adjustierungs_info`
> vollständig). Diese Story präzisiert die Tabelle auf den tatsächlichen Vertrag; die
> Signal-Bündel-Spalten (`signal_type`/`raw_value`/`z_score`/`decay_gewicht`) sind NICHT
> Teil von AC3/AC6 und werden hier nicht gebaut — eine Folge-Story für die
> Datenquellen-Abfrage-Signalaggregation kann sie bei Bedarf ergänzen (eigene Migration,
> gleiche Tabelle oder eigene Tabelle — DBA-Entscheidung zu diesem Zeitpunkt).
>
> **`instrument_id` bewusst (noch) nicht umgesetzt:** die `instrument`-Tabelle existiert
> in dieser Codebasis noch nicht (keine bisherige Story hat sie angelegt — `market_data_
> bronze` hat aus demselben Grund bereits `symbol`/`asset_class_tag` statt `instrument_id`
> verwendet, S-022). Silver folgt demselben, bereits etablierten Muster: `symbol` statt
> `instrument_id`. Eine physische FK auf eine nicht existierende Tabelle ist nicht baubar;
> das Nachrüsten von `instrument_id` (inkl. FK, sobald `instrument` existiert) ist eine
> Folge-Story (SPEC-LÜCKE, siehe Coder-Handoff S-024).

### `market_data_gold` — angereicherte Konsumenten-Werte (C-009, C-019; `docs/specs/datenqualitaet.md` AC4, S-051)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | Teil PK |
| silver_id | UUID | Teil zusammengesetzter FK → `market_data_silver(id, observed_at)` **ON DELETE CASCADE** (Iteration 2, DBA-Befund) — Referenz auf die Silver-Ableitung (Vertragsfeld `herkunft: silver_version`) |
| silver_observed_at | TIMESTAMPTZ | Teil derselben zusammengesetzten FK (Partitionsschlüssel-Pflicht bei FK auf partitionierte Tabelle) |
| data_source_id | UUID | FK → `data_source.id`, NOT NULL — denormalisiert aus der Silver-Zeile (analog `market_data_silver.data_source_id`, S-024-Präzisierung): Cross-Data-Source-Sicherheit für Rebuild-/Delete-Scoping |
| source_event_id | TEXT | NOT NULL — Vertragsfeld `event_id`, aus der Silver-Zeile übernommen |
| symbol | TEXT | aus der Silver-Zeile übernommen |
| angereicherter_wert | NUMERIC(20,8) | NOT NULL — Vertragsfeld `angereicherter_wert`; unverändert aus `market_data_silver.normalisierter_wert` übernommen (bereits normalisiert + Corporate-Actions-adjustiert, AC3/AC6) |
| qualitaetsindikator | TEXT | Vertragsfeld `qualitaetsindikator`; propagiert aus `market_data_bronze.quality_indicator` (Socket-Qualitätsmetadatum, in Silver bisher nicht exponiert) — bewusst KEINE Score-/Signal-Aggregation (z-Scores etc. sind laut Spec-Nicht-Ziel Sache der Analyse, nicht dieser Schicht) |
| observed_at | TIMESTAMPTZ | NOT NULL (Partitionsschlüssel, aus der Silver-Zeile übernommen) |
| computed_at | TIMESTAMPTZ | NOT NULL DEFAULT now() (Zeitpunkt der Gold-Ableitung, Audit) |
| — | — | **PK (id, observed_at)**, RANGE-partitioniert monatlich (analog Bronze/Silver). **UNIQUE (silver_id, silver_observed_at, observed_at)** (`uq_market_data_gold_silver_version`, `observed_at` redundant zu `silver_observed_at` — PostgreSQL verlangt den Partitionsschlüssel explizit in jedem Unique-Index auf einer `PARTITION BY RANGE`-Tabelle, empirisch gegen Postgres 17 verifiziert): genau ein Gold-Datensatz je Silver-Version (Idempotenz). **Nicht** append-only (analog Silver): bei einer Silver-Neuableitung (z.B. rückwirkende Corporate Action) wird die betroffene Gold-Reihe für Symbol/Quelle vollständig neu abgeleitet — Bronze/Silver bleiben dabei unverändert (AC4-Kern-Invariante). |

> **AC4-Kern-Invariante** ("keine Anreicherung verändert oder ersetzt die zugrunde liegenden Bronze-Rohdaten"): `market_data_gold` besitzt keine Schreibfunktion auf `market_data_bronze`/`market_data_silver` — die Ableitung ist rein lesend. **AC8-Anschluss** ("ungültige Datenpunkte erscheinen nicht in den Gold-Ergebnissen"): strukturell garantiert, da ein Gold-Datensatz nur aus einer tatsächlich persistierten Silver-Zeile abgeleitet werden kann und `app.db.silver.record_silver_observation` ungültige Bronze-Kandidaten bereits ablehnt (AC7/AC8-Gate) — es entsteht keine Silver-Zeile, aus der ein ungültiger Kandidat nach Gold gelangen könnte.
>
> **`ON DELETE CASCADE` (Iteration 2, DBA-Befund, Critical):** die FK von `silver_id`/`silver_observed_at` auf `market_data_silver` trug ursprünglich keine `ON DELETE`-Klausel (Postgres-Default `NO ACTION`) — `app.db.silver.rebuild_silver_series_for_symbol()` löscht bei jeder Corporate-Actions-Neuableitung ALLE bestehenden Silver-Zeilen für `(data_source_id, symbol)`; sobald mindestens eine davon bereits eine abgeleitete Gold-Zeile hatte, schlug dieses `DELETE` unter echtem Postgres mit einer Fremdschlüsselverletzung fehl (in SQLite-Tests unbemerkt, da `PRAGMA foreign_keys=ON` in den betroffenen Test-Fixtures fehlte). **Entscheidung:** `ON DELETE CASCADE` statt eines Vorab-Löschens innerhalb von `rebuild_silver_series_for_symbol()` — Gold-Zeilen haben laut AC4 keine eigenständige Existenz (reine Ableitung) und sind laut AC4-NFR jederzeit über `app.db.gold.rebuild_gold_series_for_symbol()` reproduzierbar; automatisches Mitlöschen bei einer Silver-Neuableitung ist damit konsistent zum bestehenden Silver-Design. Die Anschluss-Pflicht "nach einer Silver-Neuableitung Gold neu aufbauen" liegt bei der (noch nicht gebauten) Orchestrierungsschicht.
>
> **AC5 (Survivorship-bias-freies historisches Universum) — keine eigene Tabelle:** die Abfrage „welche Titel existierten zum Zeitpunkt X" (`app.db.universum.historisches_universum`) benötigt **keine** eigene Instrument-/Delisting-Tabelle — sie wird direkt über `market_data_silver.observed_at <= stand_zeitpunkt` beantwortet (Silver enthält nur valide, per AC7/AC8-Gate geprüfte Beobachtungen). Da Beobachtungen nie rückwirkend gelöscht werden (Bronze: BR-121 append-only; Silver: nur bei Corporate-Actions-Neuableitung ersetzt, nie entfernt), bleibt ein Symbol nach seiner letzten Beobachtung (Delisting) in einer späteren Universums-Abfrage weiterhin enthalten — kein „aktuell aktiv"-Filter, kein Survivorship-Bias. Ein explizites Delisting-Datum je Titel wäre erst mit einer künftigen `instrument`-Tabelle sinnvoll modellierbar (siehe `instrument_id`-Präzisierung bei `market_data_silver` oben) — außerhalb des Scopes dieser Story.

### `instrument_signal_bundle` — Gold: angereichertes Signal-Bündel je Titel (C-009, Datenquellen-Abfrage)
| Feld | Typ | Constraint |
|---|---|---|
| instrument_id | UUID | PK, FK → instrument.id (1:1, aktueller Stand) |
| signals | JSONB | NOT NULL (aggregiertes Bündel je Kategorie: z-Scores, Aktualität) |
| liquiditaet | NUMERIC(20,8) | |
| volatilitaet | NUMERIC(10,6) | |
| computed_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

---

## 3 · Analyse & LLM-Grounding (C-007, C-008)

### `analysis_result` — Analyse-Ergebnis (Buy- oder Sell-Pfad, C-007, C-011)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| instrument_id | UUID | FK → instrument.id, NOT NULL |
| analyse_typ | TEXT | CHECK ∈ {neue_titel, bestehende_titel} (zwei getrennte Pfade C-011) |
| asset_class_id | SMALLINT | FK → asset_class.id |
| gesamtscore | NUMERIC(6,3) | CHECK `0 ≤ gesamtscore ≤ 10` (→ BR-104) |
| signal_enum | TEXT | CHECK ∈ {KAUF, BEOBACHTEN, HALTEN, REDUZIEREN, VERKAUF} (Score-Schwellen → BR-105) |
| exit_urgency | TEXT | CHECK ∈ {hard_exit, soft_exit, none} (nur Sell-Pfad, C-011) |
| sanity_cap_applied | BOOLEAN | NOT NULL DEFAULT false (Risiko-Score < 3 → max HALTEN, → BR-106) |
| schema_valid | BOOLEAN | NOT NULL (JSON-Schema-Validierung bestanden, C-008 Sicherung 2) |
| llm_model | TEXT | verwendetes Modell (Audit) |
| mode | TEXT | CHECK ∈ {echt, simuliert} |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### `analysis_category_score` — Score je Kategorie (C-007)
| Feld | Typ | Constraint |
|---|---|---|
| analysis_result_id | UUID | FK → analysis_result.id (ON DELETE CASCADE) |
| category_code | TEXT | FK → analysis_category.code |
| score | NUMERIC(6,3) | CHECK `0 ≤ score ≤ 10` (→ BR-103) |
| evidence_present | BOOLEAN | NOT NULL (No-Evidence-No-Trade Basis, → BR-108) |
| — | — | PK (analysis_result_id, category_code) |

### `analysis_fact` — geerdete Fakten (LLM-Grounding-Vertrag, C-008 Sicherung 1+3)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| analysis_result_id | UUID | FK → analysis_result.id (ON DELETE CASCADE), NOT NULL |
| kennzahl | TEXT | NOT NULL |
| wert | NUMERIC(20,8) | NOT NULL |
| source_id | UUID | FK → data_source.id, **NOT NULL** (jede Zahl braucht Quelle, → BR-107) |
| source_timestamp | TIMESTAMPTZ | **NOT NULL** (Quellen-Timestamp, → BR-107) |
| cross_check_status | TEXT | CHECK ∈ {ok, abweichung, nicht_pruefbar} (C-008 Sicherung 3) |
| abweichung_pct | NUMERIC(8,4) | gemessene Abweichung zur Originalquelle |

### `hallucination_log` — Halluzinations-KPI-Log (C-008 Monitoring)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| analysis_result_id | UUID | FK → analysis_result.id |
| kennzahl | TEXT | NOT NULL |
| erwartet | NUMERIC(20,8) | (Originalquelle) |
| erhalten | NUMERIC(20,8) | (LLM-Output) |
| abweichung_pct | NUMERIC(8,4) | NOT NULL |
| ueber_toleranz | BOOLEAN | NOT NULL (→ Analyse verworfen, → BR-109) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

---

## 4 · Position, Order, Trade, Transaktion (C-013, C-014, C-016, C-017)

### `position` — gehaltene Position (C-014, C-017)

Präzisiert in S-053 (AC6): `einstand_fx_rate`, `fx_kapital_gv`,
`fx_waehrungs_gv` ergänzt — die Verträge-Sektion von `docs/specs/depot.md`
verlangt für die Position bereits `fx_kapital_gv`/`fx_waehrungs_gv`
(FX-Attribution), sie fehlten hier jedoch als Spalten;
`einstand_fx_rate` ist die zur Berechnung nötige Zusatzspalte (Ø-Einstands-
FX-Kurs, analog zu `einstand_preis`), in der ursprünglichen Verträge-Liste
nicht namentlich geführt (Feldname-Lücke, S-053 präzisiert). `fx_kapital_gv`/
`fx_waehrungs_gv` sind — wie `unrealisierter_gv` — reservierte Spalten ohne
Schreibpfad (Bewertungsschleife ist eigene, künftige Story); `einstand_fx_rate`
wird dagegen ab S-053 aktiv fortgeschrieben (Kauf/Nachkauf, → BR-129).

| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| instrument_id | UUID | FK → instrument.id, NOT NULL |
| asset_class_id | SMALLINT | FK → asset_class.id, NOT NULL |
| strategy_id | UUID | FK → strategy.id, NOT NULL (**beim Kauf fixiert**, C-014) |
| time_horizon_id | SMALLINT | FK → time_horizon.id, NOT NULL (beim Kauf fixiert) |
| these | TEXT | NOT NULL (Kaufthese; Leitfrage-Prüfung C-011) |
| menge | NUMERIC(20,8) | NOT NULL, CHECK ≥ 0 |
| einstand_preis | NUMERIC(20,8) | NOT NULL (Ø-Einstand) |
| einstand_methode | TEXT | NOT NULL, CHECK ∈ {gleitender_durchschnitt, fifo}, DEFAULT `gleitender_durchschnitt` (CH-Default, → BR-112) |
| realisierter_gv | NUMERIC(20,8) | NOT NULL DEFAULT 0 |
| unrealisierter_gv | NUMERIC(20,8) | (berechnet bei Bewertung) |
| einstand_fx_rate | NUMERIC(20,8) | Ø-Einstands-FX-Kurs (Kurs zur CHF-Basiswährung bei Einstand); NULL bei CHF-Positionen (→ AC6/BR-129) |
| fx_kapital_gv | NUMERIC(20,8) | unrealisierter Kapitalgewinn-Anteil in CHF (FX-Attribution, berechnet bei Bewertung — noch kein Schreibpfad, analog `unrealisierter_gv`, → AC6/BR-129) |
| fx_waehrungs_gv | NUMERIC(20,8) | unrealisierter Währungsgewinn-Anteil in CHF (FX-Attribution, berechnet bei Bewertung — noch kein Schreibpfad, analog `unrealisierter_gv`, → AC6/BR-129) |
| status | TEXT | CHECK ∈ {offen, geschlossen} |
| mode | TEXT | NOT NULL, CHECK ∈ {echt, simuliert} (→ BR-130) |
| opened_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| closed_at | TIMESTAMPTZ | |

### `exit_rule` — beim Kauf fixierte Exit-Regeln (C-011, C-014; unveränderlich → BR-111)
| Feld | Typ | Constraint |
|---|---|---|
| position_id | UUID | PK, FK → position.id (1:1) |
| stop_loss_pct | NUMERIC(6,3) | (z.B. −15 %) |
| take_profit_pct | NUMERIC(6,3) | (z.B. +30 %) |
| stop_typ | TEXT | CHECK ∈ {fix_pct, atr_trailing, fundamental, keiner} |
| atr_multiplikator | NUMERIC(5,2) | (2.5–3× je Volatilitätsklasse) |
| thesis_invalidation | TEXT | Bedingung des Thesis-Bruchs |
| time_box | INTERVAL | optionale Zeit-Box |
| — | — | **append-only nach Position-Open** — kein UPDATE (Disciplined-Exit, → BR-111) |

### `order` — Order (C-016)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| position_id | UUID | FK → position.id |
| instrument_id | UUID | FK → instrument.id, NOT NULL |
| platform_id | UUID | FK → trading_platform.id |
| richtung | TEXT | CHECK ∈ {buy, sell} |
| order_typ | TEXT | CHECK ∈ {market, limit, stop, stop_market, twap} |
| menge | NUMERIC(20,8) | NOT NULL, CHECK > 0 |
| limit_preis | NUMERIC(20,8) | (bei limit/stop) |
| arrival_price | NUMERIC(20,8) | NOT NULL (Kurs bei Signal — Slippage-Basis, C-016 TCA) |
| exit_urgency | TEXT | CHECK ∈ {hard, soft, none} (Exit-Sizing, C-013) |
| tranche_index | SMALLINT | (Tranche n von m, 3–4 Tranchen) |
| tranche_total | SMALLINT | |
| status | TEXT | CHECK ∈ {offen, teilfill, filled, rejected, timeout, cancelled} |
| mode | TEXT | NOT NULL, CHECK ∈ {echt, simuliert} (→ BR-113, BR-130) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### `trade_fill` — Ausführung / Teilfill (C-016 TCA)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| order_id | UUID | FK → order.id, NOT NULL |
| fill_preis | NUMERIC(20,8) | NOT NULL |
| fill_menge | NUMERIC(20,8) | NOT NULL, CHECK > 0 |
| courtage_chf | NUMERIC(20,8) | NOT NULL DEFAULT 0 |
| spread_kosten_chf | NUMERIC(20,8) | NOT NULL DEFAULT 0 |
| slippage_abs | NUMERIC(20,8) | NOT NULL (= fill_preis − arrival_price, Arrival-Price-Slippage, → BR-114) |
| executed_at | TIMESTAMPTZ | NOT NULL |

### `transaction` — volle Transaktionshistorie (C-017, Steuer + Dashboard; append-only → BR-115)

Präzisiert in S-035 (AC4/AC7): `waehrung`, `arrival_price`, `slippage_abs`
ergänzt — die Verträge-Sektion von `docs/specs/depot.md` verlangte diese
drei Felder für die Transaktionshistorie bereits (Tupel `{ trade_id,
titel_id, richtung, menge, fill_preis, arrival_price, slippage, kosten,
waehrung, zeitstempel }`), sie fehlten hier jedoch als Spalten.

`fx_rate`/`kapital_gv_chf`/`waehrungs_gv_chf` waren bereits vor S-053 als
Spalten angelegt (Migration `a1c4e7f2b930`, S-035), aber unbefüllt (NULL,
Docstring-Vermerk „das ist AC6/S-053, ausserhalb dieser Story"); S-053
(AC6) verdrahtet sie: `fx_rate` wird bei jedem Fremdwährungs-Fill (Kauf
UND Verkauf) aus `FillInput.fx_rate` übernommen, `kapital_gv_chf`/
`waehrungs_gv_chf` nur bei einem Fremdwährungs-**Verkauf** über
`app.domain.portfolio.fx_attribution.berechne_fx_split_realisiert`
gesetzt (kein G/V auf einen Kauf). Ergänzt ausserdem `fx_rate,
kapital_gv_chf, waehrungs_gv_chf` in der Verträge-Sektion von
`docs/specs/depot.md` (Transaktionshistorie-Tupel, das diese drei Felder
bislang nicht führte).

| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| position_id | UUID | FK → position.id, NULLable (ein Verkauf-Fill, der bei FIFO mehrere Lots verbraucht, ist keinem einzelnen Lot eindeutig zuordenbar — der Verträge-Vertrag der Historie selbst referenziert ohnehin nur `titel_id`, keine `position_id`) |
| instrument_id | UUID | FK → instrument.id, NOT NULL |
| typ | TEXT | CHECK ∈ {buy, sell, dividend, fee, fx_adjust} |
| menge | NUMERIC(20,8) | |
| preis | NUMERIC(20,8) | (Fill-Preis) |
| kosten_chf | NUMERIC(20,8) | NOT NULL DEFAULT 0 (echte Kosten, in Kostenbasis genettet) |
| waehrung | TEXT | NOT NULL, CHECK length = 3 (ISO-Code, AC4 — Handelswährung des Fills) |
| arrival_price | NUMERIC(20,8) | Kurs bei Signal/Order-Auslösung (nur bei typ ∈ {buy, sell} gesetzt — TCA-Basis, → AC7/BR-114) |
| slippage_abs | NUMERIC(20,8) | = preis − arrival_price (realisierte Slippage je Trade, TCA, → AC7/BR-114) |
| fx_rate | NUMERIC(20,8) | (Kurs zur Basiswährung) |
| kapital_gv_chf | NUMERIC(20,8) | (FX-Attribution: Kapitalgewinn, → BR-129) |
| waehrungs_gv_chf | NUMERIC(20,8) | (FX-Attribution: Währungsgewinn, → BR-129) |
| mode | TEXT | NOT NULL, CHECK ∈ {echt, simuliert} (→ BR-130) |
| booked_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| — | — | **append-only** — kein UPDATE/DELETE (Steuer-Auditpfad, → BR-115); S-035 setzt dies per Postgres-Trigger (`BEFORE UPDATE OR DELETE ... RAISE EXCEPTION`) durch, plus App-seitig dadurch, dass `PositionRepository` für diese Tabelle nur eine Schreib- (`schreibe_transaktion`, reines Insert) und eine Lese-Methode (`historie_je_titel`) anbietet — keine Update-/Delete-Methode existiert im Port |

### `depot_fill_dedup` — Idempotenz-Ledger für Fill-Zustellung (ADR-011, P8; nachgezogen S-016 DBA-Zweit-Review)
| Feld | Typ | Constraint |
|---|---|---|
| client_order_id | TEXT | PK (Dedup-Schlüssel aus der Order-Ausführung, ADR-011) |
| instrument_id | UUID | FK → instrument.id, NOT NULL |
| richtung | TEXT | CHECK ∈ {kauf, verkauf}, NOT NULL |
| verbucht_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| — | — | **Nur Dedup-Marker** — KEIN Ersatz für die volle append-only Transaktionshistorie (`transaction`, AC4/AC7 → S-035); S-035 kann bei Bedarf einen eigenen UNIQUE-Constraint direkt auf `transaction.client_order_id` einführen und diese Tabelle ablösen, das entscheidet die jeweilige Story |

### `risk_check_log` — Risikomanagement-Entscheid beim Kauf (C-015)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| position_id | UUID | FK → position.id (Kandidat/Order) |
| decision | TEXT | CHECK ∈ {durchwinken, runtersizen, blockieren} (Drei-Wege, C-015) |
| klumpenrisiko_pct | NUMERIC(6,3) | |
| stress_korrelation | NUMERIC(6,4) | (Korrelation zu Bestand) |
| begruendung | TEXT | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

---

## 5 · Depot-Aggregate (C-015, C-017)

> **S-036 (AC8/AC9)** liefert die Portfolio-Aggregate (Gewichtung je GICS-
> Branche/Anlageklasse, Cash-Quote) sowie den Depot-Stand/Titel-Strategie-
> Exit-Regeln-Output als **live berechnete Domain-Funktion** aus den
> offenen `position`-Zeilen (`app.domain.portfolio.portfolio_aggregate`),
> NICHT aus den beiden folgenden Tabellen — konsistent mit der NFR
> „Aggregate sind aus Positionen + Historie reproduzierbar (kein stiller
> Zustand ohne Herleitung)". `portfolio_snapshot`/`portfolio_weight`
> bleiben als Schema für eine spätere **Persistenz-/Historien-Story**
> (Zeitreihen-Trend fürs Dashboard) reserviert und sind von S-036 nicht
> migriert worden.

### `portfolio_snapshot` — Depot-Aggregat je Zeitpunkt
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| snapshot_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| total_value_chf | NUMERIC(20,8) | NOT NULL |
| cash_quote_pct | NUMERIC(6,3) | NOT NULL |
| mode | TEXT | NOT NULL, CHECK ∈ {echt, simuliert} (getrennte Aggregate, → BR-130) |

### `portfolio_weight` — Gewichtung je Dimension (Branche/Klasse)
| Feld | Typ | Constraint |
|---|---|---|
| snapshot_id | UUID | FK → portfolio_snapshot.id (ON DELETE CASCADE) |
| dimension | TEXT | CHECK ∈ {sektor, asset_class} |
| key | TEXT | (GICS-Sektor bzw. Klassen-ID als Text) |
| weight_pct | NUMERIC(6,3) | NOT NULL, CHECK 0–100 |
| — | — | PK (snapshot_id, dimension, key) |

---

## 6 · Lernschleife / Validierungs-Gate (Stufe 2, Datenmodell jetzt — C-012)

### `rule_hypothesis` — Regel-Hypothese aus Research (C-012, Spec `docs/specs/lernschleife.md` AC1/AC2, S-058)
> **Präzisierung (S-058):** die ursprüngliche Fassung dieser Tabelle führte nur `beschreibung`/`params`/`free_param_count` — das bildete den Spec-Vertrag „Hypothese (Research → Gate): `{ hypothese_id, beschreibung, marktlogik, evidenz{ anzahl_faelle, zeitraum, signalquelle, anlageklasse } }`" (Verträge-Abschnitt) noch nicht vollständig ab. Die AC1-Mindest-Evidenz-Protokoll-Felder (`anzahl_faelle`, `zeitraum_von`/`zeitraum_bis`, `signalquelle`, `asset_class_id`) sowie `marktlogik` (AC2) wurden ergänzt — beide Feldgruppen sind NOT NULL: eine Hypothese ohne vollständiges Protokoll bzw. ohne marktlogische Begründung wird von `app.domain.research.hypothesen_erzeugung.erzeuge_hypothesen` gar nicht erst als `Hypothese` gebaut und erreicht diese Tabelle nie (App-Filter, → BR-136).

| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| beschreibung | TEXT | NOT NULL |
| marktlogik | TEXT | NOT NULL (AC2 — marktlogische Erklärbarkeit; nur begründete Muster werden überhaupt persistiert) |
| anzahl_faelle | INTEGER | NOT NULL, CHECK > 0 (AC1 Mindest-Evidenz-Protokoll) |
| zeitraum_von | TIMESTAMPTZ | NOT NULL (AC1) |
| zeitraum_bis | TIMESTAMPTZ | NOT NULL (AC1), CHECK ≥ zeitraum_von |
| signalquelle | TEXT | NOT NULL (AC1) |
| asset_class_id | SMALLINT | FK → asset_class.id, NOT NULL (AC1 „Anlageklasse") |
| params | JSONB | NOT NULL (Regelparameter-Kandidat) |
| free_param_count | SMALLINT | NOT NULL (Overfit-Sanity: > 5–6 → Verdacht; Schwellenwert-Auswertung selbst ist Folge-Story) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### `trial_registry` — Trial-Registry: JEDE getestete Variante (C-012, **nie löschen** → BR-118)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| hypothesis_id | UUID | FK → rule_hypothesis.id, NOT NULL |
| variant_hash | TEXT | NOT NULL (Identität der Variante) |
| params | JSONB | NOT NULL |
| archived | BOOLEAN | NOT NULL DEFAULT false (abgelehnt → archiviert, **nie gelöscht** — DSR-Zählung, → BR-118) |
| tested_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| — | — | UNIQUE (hypothesis_id, variant_hash) · **append-only**, kein DELETE |

### `gate_result` — Gate-Ergebnis mit Ampel + Metriken (C-012)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| trial_id | UUID | FK → trial_registry.id, NOT NULL |
| stufe | TEXT | CHECK ∈ {A_historisch, B_paper} (zweistufig) |
| ampel | TEXT | CHECK ∈ {gruen, gelb, rot} (Ampel-Logik → BR-119) |
| sample_size | INTEGER | (Mindest-Stichprobe ≥ 100; < 30 nicht bewertet) |
| wfe | NUMERIC(6,4) | Walk-Forward-Effizienz (≥ 0.5 gefordert) |
| dsr | NUMERIC(8,4) | Deflated Sharpe Ratio |
| psr | NUMERIC(6,4) | Probabilistic Sharpe Ratio (≥ 0.95 in Stufe B) |
| min_trl | NUMERIC(8,2) | MinTRL Restlaufzeit (→ BR-120) |
| begruendung | TEXT | (bei rot: Archiv-Begründung) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

---

## 7 · Betrieb & Sicherung (C-019)

### `kill_switch_status` — Kill-Switch (Singleton, C-019)
| Feld | Typ | Constraint |
|---|---|---|
| id | SMALLINT | PK, CHECK `id = 1` (Singleton) |
| active | BOOLEAN | NOT NULL DEFAULT false (aktiv → „flatten & halt", keine neuen Orders → BR-127) |
| reason | TEXT | |
| activated_at | TIMESTAMPTZ | |

### `heartbeat` — Heartbeat je Komponente (C-019)
| Feld | Typ | Constraint |
|---|---|---|
| component | TEXT | PK (Modul-/Worker-Name) |
| last_beat_at | TIMESTAMPTZ | NOT NULL |
| status | TEXT | CHECK ∈ {ok, degraded, down} |

### `alert_log` — Alert-Log (C-008, C-010, C-015, C-019)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| typ | TEXT | CHECK ∈ {drawdown, hallucination_kpi, alert_fatigue, data_outage, kill_switch, dlq_backlog} |
| severity | TEXT | CHECK ∈ {info, warn, critical} |
| message | TEXT | NOT NULL |
| acknowledged | BOOLEAN | NOT NULL DEFAULT false |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

### `ingest_dead_letter` — Dead-Letter-Queue dauerhaft fehlschlagender Abrufe (C-009)
| Feld | Typ | Constraint |
|---|---|---|
| id | UUID | PK |
| data_source_id | UUID | FK → data_source.id |
| source_event_id | TEXT | |
| payload | JSONB | |
| fehler | TEXT | NOT NULL |
| retry_count | SMALLINT | NOT NULL DEFAULT 0 |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT now() |

---

## 8 · Indizes (auf jede FK- und Filterspalte, `sql/R05`)

| Tabelle | Index | Zweck |
|---|---|---|
| analysis_method | (asset_class_id, category_code, config_version_id) | Methodentabelle je Klasse/Kategorie/Version laden |
| analysis_method | (config_version_id) | Alle Methoden einer Version laden (Versions-Snapshot) |
| analysis_method_version | UNIQUE partiell `WHERE is_current` | genau eine aktuell gültige Methodentabellen-Version (→ BR-133) |
| category_weight | (config_version_id) | Alle Gewichte einer Version laden (Versions-Snapshot) |
| category_weight_version | UNIQUE partiell `WHERE is_current` | genau eine aktuell gültige Kategoriegewicht-Version (→ BR-133) |
| strategy | — (kein dedizierter Index auf `cluster`) | FK-Spalte `cluster` bewusst ohne Index: `strategy_cluster` hat nur 4 Zeilen, `strategy` nur 18 (S-037) — ein Full-Table-Scan auf `cluster` ist bei dieser Kardinalität günstiger als ein zusätzlicher Index (sql/R05-Ausnahme, analog `risk_profile`/`portfolio_class_limit`-Stammdatentabellen) |
| data_source_asset_class | (asset_class_id) | Quellen je Klasse (Datenquellen-Abfrage-Matching) |
| platform_asset_class | (asset_class_id) | Plattform-Kosten je Klasse |
| instrument | (asset_class_id), (symbol) | Klassenfilter + Symbol-Lookup |
| market_data_bronze | (data_source_id, ingested_at), (asset_class_tag, observed_at) | Replay + PIT je Klasse (je Partition) |
| market_data_bronze | (data_source_id, source_event_id) — **nicht** UNIQUE | Ereignis-Lookup für App-/DB-Layer-Idempotenz (→ BR-122-Präzisierung §2) |
| market_data_silver | (symbol, observed_at), (source_event_id), (bronze_id, bronze_ingested_at), (data_source_id, symbol) | Corporate-Actions-Adjustierung je Titel/Zeit, Event-Lookup, Bronze-Rückverfolgung, Quellen-korrektes Rebuild-/Delete-Scoping (Iteration 2) |
| market_data_gold | (symbol, observed_at), (source_event_id), (silver_id, silver_observed_at), (data_source_id, symbol) | Konsumenten-Lookup je Titel/Zeit, Event-Lookup, Silver-Rückverfolgung, Quellen-korrektes Rebuild-/Delete-Scoping (S-051) |
| analysis_result | (instrument_id, created_at), (analyse_typ), (mode) | Analyse-Historie, Pfad-/Mode-Filter |
| analysis_category_score | (analysis_result_id) | Scores je Analyse |
| analysis_fact | (analysis_result_id), (source_id) | Fakten je Analyse, Quellen-Join |
| hallucination_log | (created_at), (ueber_toleranz) | KPI-Berechnung (> 2 % → Alarm) |
| position | (instrument_id), (status), (mode), (asset_class_id) | Depot-/Risikoabfragen |
| order | (position_id), (status), (mode), (created_at) | offene Orders, TCA |
| trade_fill | (order_id), (executed_at) | Fills je Order |
| transaction | (position_id), (instrument_id), (booked_at), (mode) | Steuer-/Dashboard-Historie |
| risk_check_log | (position_id), (created_at) | Risiko-Audit |
| depot_fill_dedup | PK (client_order_id), (instrument_id) | Idempotenz-Lookup (ADR-011/BR-134) + Fills je Titel |
| portfolio_weight | (snapshot_id) | Gewichtungen je Snapshot |
| rule_hypothesis | (asset_class_id) | Hypothesen je Anlageklasse |
| trial_registry | (hypothesis_id), UNIQUE (hypothesis_id, variant_hash) | DSR-Zählung |
| gate_result | (trial_id), (ampel) | Gate-Auswertung |
| alert_log | (created_at), (typ, acknowledged) | offene Alerts |
| ingest_dead_letter | (data_source_id, created_at) | DLQ-Backlog-Monitoring |
| portfolio_strategy | partieller UNIQUE `WHERE aktiv` | genau eine aktive Depotstrategie |

---

## 9 · Partitionierung & Retention (Zeitreihen)

| Entität | Partitionierung | Retention |
|---|---|---|
| `market_data_bronze` | RANGE `ingested_at`, **monatlich** | Immutable (append-only). **Voll behalten** für Point-in-Time/Replay/Validierungs-Gate; Kalt-Archiv nach 24 Monaten (Detach + externes Objekt-Storage), nie im Betrieb löschen. Recalculation-Window 2–3 Tage für revisionsbehaftete Quellen (FRED) → **neue** Bronze-Zeilen, alte bleiben (PIT). |
| `market_data_silver` | RANGE `observed_at`, monatlich | 12–24 Monate online, danach Detach/Archiv (rekonstruierbar aus Bronze). |
| `market_data_gold` | RANGE `observed_at`, monatlich | 12–24 Monate online, danach Detach/Archiv (rekonstruierbar aus Bronze/Silver). |
| `hallucination_log` | — (moderat) | 24 Monate (KPI-Trend). |
| `heartbeat` | — (klein, upsert je Komponente) | Nur aktueller Stand; keine Historie. |
| `alert_log` | optional monatlich | 12 Monate; acknowledged nach 90 Tagen archivierbar. |
| `ingest_dead_letter` | — | 90 Tage nach Resolution. |
| `transaction` | (optional RANGE `booked_at` jährlich bei Volumen) | **Unbefristet** (Steuer-Auditpfad CH), nie löschen. |
| `trial_registry` / `gate_result` | — | **Unbefristet** (DSR-Zählung braucht alle je getesteten Varianten, → BR-118). |
| `portfolio_snapshot` / `portfolio_weight` | optional RANGE `snapshot_at` | 24 Monate feingranular, danach aggregiert. |

---

## 10 · Validierungs-Geschäftsregeln (BR-100er-Katalog)

> Datenvalidierende Regeln des Modells. **Enforcement-Layer** je Regel benannt (macht doppelte/fehlende Validierung sichtbar). „DB" = Constraint/Trigger, „App" = Applikationslogik.

| BR-ID | Feld / Entität | Regel | Enforced by (Layer) |
|---|---|---|---|
| BR-100 | asset_class.id | Genau 11 Klassen, id ∈ 1…11, fachlich fix (keine synthetische ID) | DB-CHECK |
| BR-101 | category_weight | Σ weight_pct je (asset_class, config_version) = 100 (±0.01) | App-Validierung + DB-Trigger/Deferred-Check |
| BR-102 | analysis_method.ranking | ranking ∈ 1…10 (fix je Klasse, quartalsweise Review) | DB-CHECK |
| BR-103 | analysis_category_score.score | score ∈ 0.0…10.0 | DB-CHECK |
| BR-104 | analysis_result.gesamtscore | gesamtscore ∈ 0.0…10.0 | DB-CHECK |
| BR-105 | analysis_result.signal_enum | signal_enum konsistent mit Score-Schwellen (≥8 KAUF · 6–7.9 BEOBACHTEN · 4–5.9 HALTEN · 2–3.9 REDUZIEREN · <2 VERKAUF) | App (deterministisches Modul) |
| BR-106 | analysis_result | Sanity-Cap: ist Risiko-Kategorie-Score < 3, ist signal_enum maximal HALTEN; sanity_cap_applied = true | App |
| BR-107 | analysis_fact | Jede Zahl trägt source_id **und** source_timestamp (NOT NULL) — LLM-Grounding-Pflicht | DB-NOT-NULL + App-Schema |
| BR-108 | analysis_category_score | No-Evidence-No-Trade: fehlt evidence_present in einer Kategorie, entsteht **kein** KAUF-Signal (Titel übersprungen), kein LLM-Schätzwert | App |
| BR-109 | hallucination_log / analysis_result | Faktenabweichung über Toleranz → Analyse verworfen (nicht in Order-Pfad) + geloggt | App + DB-Log |
| BR-110 | hallucination_log | Halluzinations-KPI (Anteil Analysen mit Abweichung) > 2 % → Alert + LLM aus Entscheidungskette | App (aggregierte Prüfung) |
| BR-111 | exit_rule | Beim Kauf fixiert; nach Position-Open **unveränderlich** (kein UPDATE) — Disziplinierte Exits | DB (kein Update-Grant / Trigger) + App |
| BR-112 | position.einstand_methode | Default gleitender Durchschnitt (CH), FIFO optional | DB-DEFAULT + CHECK |
| BR-113 | order.mode | mode ∈ {echt, simuliert}; muss zu Position-mode und globalem/Klassen-Modus passen | App + DB-CHECK |
| BR-114 | trade_fill.slippage_abs | slippage_abs = fill_preis − arrival_price je Fill gespeichert (TCA) | App |
| BR-115 | transaction | Append-only; kein UPDATE/DELETE (Steuer-Auditpfad) | DB (Trigger: `BEFORE UPDATE OR DELETE` löst Exception aus, S-035) + App (Port bietet keine Update-/Delete-Methode) |
| BR-116 | portfolio_weight | Σ weight_pct je (snapshot, dimension) = 100; cash_quote_pct konsistent | App |
| BR-117 | portfolio_strategy / portfolio_class_limit | Grenzwerte: Einzelposition/Sektor/Klasse/Cash innerhalb Profil-Bandbreiten; genau **eine** aktive Depotstrategie | App + partieller UNIQUE-Index |
| BR-118 | trial_registry | Append-only; jede getestete Variante bleibt (abgelehnte → archived=true), **nie löschen** — DSR-Validität | DB (kein Delete-Grant) + App |
| BR-119 | gate_result.ampel | 🟢 nur wenn Stufe A **und** B bestanden (sample ≥ 100, WFE ≥ 0.5, PSR ≥ 0.95); 🟡 A ok/B läuft; 🔴 durchgefallen | App |
| BR-120 | gate_result.min_trl | MinTRL bei jeder Auswertung berechnet und gespeichert/angezeigt | App |
| BR-121 | market_data_bronze | Immutable/append-only: kein UPDATE/DELETE innerhalb Online-Retention; Point-in-Time via observed_at | DB (BEFORE-UPDATE/DELETE-Trigger, S-022) + App |
| BR-122 | market_data_bronze | Idempotenz + AC10-Versionierung: identischer Inhalt zu (data_source_id, source_event_id) → No-Op, abweichender Inhalt → neue PIT-Version (kein physischer Unique-Index möglich, siehe §2-Präzisierung) | App (`app/db/bronze.py`) + DB-Trigger |
| BR-123 | data_source / asset_class | Reddit-Sentiment (retail_social) nur bei retail_driven-Klassen (Aktien 1, Krypto 7) — nicht Obligationen/FX | App (Quellen-Matching) |
| BR-124 | asset_class.aktiv | Inaktive Klasse → keine Datenabfrage, keine Analyse, keine Datenkosten (Toggle in allen Modulen) | App |
| BR-125 | asset_class.aktiv / position | Deaktivierte Klasse mit offenen Positionen: keine neuen Käufe, aber Überwachung + Exits bleiben aktiv | App |
| BR-126 | data_source / trading_platform | API-Keys/Credentials nie als Klartext in DB — nur vault_ref (Secrets-Manager) | App + Review |
| BR-127 | kill_switch_status | active = true → keine neuen Orders (flatten & halt) | App |
| BR-128 | instrument.gics_sector | Für Positionen handelbarer Klassen Pflicht (Depotstrategie-Sektorprüfung) | App |
| BR-129 | transaction | Bei currency ≠ CHF: kapital_gv_chf und waehrungs_gv_chf getrennt ausgewiesen (FX-Attribution) | App |
| BR-130 | mode (alle transaktionalen Entitäten) | echt- und simuliert-Daten in Aggregaten/Snapshots nie vermischt | App + Filter |
| BR-131 | (verschoben — Folge-Story) | Robuster z-Score gekappt auf ±3. `market_data_silver.z_score` war Teil des ursprünglichen (Signal-Bündel-)Zuschnitts der Tabelle; die S-024-Präzisierung (§2) hat diese Spalte entfernt, da sie nicht Teil des AC3/AC6-Silver-Datensatz-Vertrags ist — die Regel gilt für eine künftige Datenquellen-Abfrage-Signalaggregations-Story (z-Score-Feld dort neu einzuführen) | App (Folge-Story) |
| BR-132 | analysis_method.last_reviewed_at | Quartalshinweis (AC11): liegt `last_reviewed_at` ≥ ~1 Quartal (90 Tage) zurück, gilt die Methode als review-fällig (Erinnerung/Kennzeichnung) — **kein** automatisches Ändern von `ranking` | App (`app/db/analysis_method_review.py`) |
| BR-133 | category_weight_version / analysis_method_version | Genau eine Zeile mit `is_current = true` je Versionsregister (AC10) | DB (partieller UNIQUE-Index `WHERE is_current`) |
| BR-134 | depot_fill_dedup.client_order_id | Idempotenz: PK/UNIQUE auf `client_order_id` — ein Fill wird nie zweimal gegen den Bestand verbucht (ADR-011, P8, at-least-once). *(Beim Merge von F-011 von BR-132 auf BR-134 umnummeriert — BR-132/BR-133 waren parallel durch S-018 vergeben.)* | DB-UNIQUE + App |
| BR-135 | strategy.cluster / strategy_cluster.freigeschaltet | Eine Strategie-Zuordnung ausserhalb des freigeschalteten Clusters wird abgelehnt (MVP: nur passiv_regelbasiert); deterministisch, ohne LLM-Beteiligung (`docs/specs/strategie-exit-regeln.md` AC2/E2, S-037). *(Beim Merge von F-012 von BR-132 auf BR-135 umnummeriert.)* | App |
| BR-136 | rule_hypothesis | Mindest-Evidenz-Protokoll (`anzahl_faelle > 0`, `zeitraum_bis >= zeitraum_von`, `signalquelle`, `asset_class_id` alle Pflicht) UND marktlogische Begründung (`marktlogik` Pflicht) — ohne beides wird keine Hypothese ans Gate übergeben (`docs/specs/lernschleife.md` AC1/AC2, S-058) | DB-NOT NULL/CHECK + App (`app.domain.research.hypothesen_erzeugung.erzeuge_hypothesen`) |

---

## 11 · Migrations-Reihenfolge (alembic; harte Abhängigkeiten)

Der `coder` setzt in dieser Reihenfolge um (FK-Abhängigkeiten bestimmen sie):

1. **Stammdaten-Basis:** `asset_class`, `analysis_category`, `strategy_cluster` → `strategy`, `time_horizon`, `exit_default_set`, `atr_multiplier_default`, `risk_profile`, `system_setting`.
2. **Konfig mit FK auf Basis:** `category_weight_version` → `category_weight`, `analysis_method_version` → `analysis_method`, `data_source`, `data_source_asset_class`, `trading_platform`, `platform_asset_class`, `portfolio_strategy`, `portfolio_class_limit`. Die Versionsregister (`*_version`) haben keine FK-Abhängigkeit und werden jeweils vor der zugehörigen versionierten Tabelle angelegt.
3. **Instrument:** `instrument` (FK asset_class).
4. **Marktdaten (partitioniert):** `market_data_bronze` (+ Partitionen), `market_data_silver` (+ Partitionen), `market_data_gold` (+ Partitionen), `instrument_signal_bundle`.
5. **Analyse:** `analysis_result` → `analysis_category_score`, `analysis_fact`, `hallucination_log`. `analysis_result` referenziert bei Einführung zusätzlich `category_weight_version.id` und `analysis_method_version.id` (AC10 — welche Konfigurationsversion der Analyse zugrunde lag), sobald diese Story `analysis_result` anlegt.
6. **Trading:** `position` → `exit_rule`, `order` → `trade_fill`, `transaction`, `risk_check_log`, `depot_fill_dedup`.
7. **Aggregate:** `portfolio_snapshot` → `portfolio_weight`.
8. **Lernschleife:** `rule_hypothesis` → `trial_registry` → `gate_result`.
9. **Betrieb:** `kill_switch_status`, `heartbeat`, `alert_log`, `ingest_dead_letter`.
10. **Seed-Daten (separate Migration):** Anlageklassen 1–11, 5 Kategorien, Kategoriegewichte + Methodentabellen je Klasse (aus Anlageklassen-Notiz), Datenquellen-Registry (12 Quellen), 3 Risikoprofile, 9 Zeithorizonte, 18 Strategien, 5 Default-Exit-Set-Kategorien (S-038), 2 ATR-Multiplikator-Volatilitätsklassen (S-038). Idempotent seedbar (`ON CONFLICT DO NOTHING`).

> **Append-only-Durchsetzung (BR-111/115/118/121):** über entzogene UPDATE/DELETE-Grants auf App-Rolle **oder** BEFORE-UPDATE/DELETE-Trigger `RAISE EXCEPTION` — Wahl trifft der `coder` in der jeweiligen Migration; das Modell fordert nur die Invariante.

---

## Offene Punkte für die Spec-Phase (aus dem Konzept, hier bewusst nicht vorentschieden)

- Toleranzschwellen je Kennzahl-Typ für den Zahlen-Cross-Check (C-008) → beeinflusst `analysis_fact.cross_check_status`-Logik, nicht das Schema.
- Detail-JSON-Schema des LLM-Analyse-Outputs (C-008) → `signals`/`payload`-JSONB-Struktur.
- z-Score-Vergleichsgruppe (cross-sectional je Klasse?) und Sentiment-Decay-Halbwertszeit je Klasse (C-009).
- Multi-User/RLS (aktuell Single-Owner) → bei Einführung `owner_id` + Policies nachrüsten.
- Krypto-Broker-Anbindung (IBKR vs. Kraken) → beeinflusst `trading_platform`-Seed, nicht das Schema.
</content>
</invoke>
