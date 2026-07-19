---
id: frontend-cockpit
title: Betriebs-Cockpit-Frontend (server-gerenderte Anzeige-/Control-Plane)
status: active
version: 3
spec_format: use-case-2.0
area: depot
---

# Spec: Betriebs-Cockpit-Frontend (server-gerenderte Anzeige-/Control-Plane)  (`frontend-cockpit`)

> Konzept-Herkunft: (← C-017 Depot & Reporting · C-003 Betriebssicherheit · C-006 Toggles · C-007 Spinnennetz · C-016 Modus-Schalter · C-019 Betriebssicherung)
> Architektur-Bindung: `architecture.md` **§13** (Frontend/UI-Schicht) + ADR-012 (HTMX+Jinja2, keine SPA) / ADR-013 (vendored Assets, kein CDN) / ADR-014 (Demo-Seed). Design-Bindung: `docs/design.md` (§5 Shell, §7 Komponenten, §8 Charts, §9 A11y, §10 View-Blaupausen).

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig.
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).
> Diese Spec beschreibt **ausschliesslich die Anzeige-/Control-Plane** (§13.7, C-017) — sie verändert **keine** Trading-Logik. Geld ist `Decimal` (P7); die UI **zeigt** nur, rechnet nicht.

## Zweck

Das Betriebs-Cockpit ist die server-gerenderte Anzeige- und Control-Plane des Systems: ein nüchternes Betriebs-Terminal, das fünf Kern-Views (Depot/Portfolio · Kandidaten & Analyse-Scores · Order-/Trade-Historie · System-Status · Konfiguration/Toggles) über HTMX + Jinja2 in derselben FastAPI-App ausliefert. Jede View bezieht ihre Daten aus einer geteilten, **read-only** Query-Schicht (`app/api/queries/**`, ein Pydantic-View-DTO), die von einer JSON- **und** einer HTML-Route konsumiert wird (P4/DRY). Schreibende Betriebseingriffe (Toggle, Modus, Kill-Switch) laufen ausschliesslich über eine klar getrennte Control-Plane (`app/api/control.py`) gegen die `app/core/**`-Zustandsfunktionen — nie über die Anzeige-Schicht. Ein env-gateter, idempotenter Demo-Seed füllt alle Views ohne Live-Betrieb, ohne je eine Order auszulösen.

## Main Success Scenario   <!-- Betriebs-Blick + Statuswechsel -->

1. Der Betreiber öffnet eine Cockpit-View; die persistente Statusleiste zeigt ohne Scrollen Ampel, Kill-Switch-Zustand, Modus (SIMULIERT), Heartbeat, Drawdown und Halluzinations-KPI.
2. Die HTML-Route rendert das View-DTO, das die geteilte Query-Funktion aus den vorhandenen Lese-Ports (`PositionRepository`, `LivePriceProvider`, `app/core/**`, Score-/Kandidaten-Read-Modell) zusammengestellt hat — dieselbe Query speist die JSON-Route.
3. Live-Elemente (Ampel, Live-Kurse, Heartbeat, Drawdown, KPI) aktualisieren sich per HTMX-Polling gegen kleine Partial-Endpunkte, ohne Layout-Sprung und ohne Fokusverlust.
4. Der Betreiber löst einen Betriebseingriff aus (Klassen-Toggle, Kill-Switch, Modus): die schreibende Aktion läuft als HTMX-POST über die Control-Plane (`app/api/control.py`) gegen die `app/core/**`-Zustandsfunktion; das aktualisierte Status-Partial wird zurückgerendert.
5. Im Demo-Seed-Zustand (`SEED_DEMO`) zeigen alle Views plausible, deterministische Daten (Paper-Positionen `mode="simuliert"`, Kandidaten-Analysen mit 5 Kategorie-Scores, Trade-Historie mit Slippage/TCA, Gate-Ampel) — Playwright-testbar.

## Alternative Flows

### A1: Kritischer Betriebszustand (Kill-Switch HALTED / Live-Modus)
- Die Statusleiste wächst um ein **Vollbreite-Banner** mit maximaler visueller Priorität (D5); der Zustand wird als Wort angesagt (`aria-live`), nicht nur farblich.

### A2: Live-Modus im MVP gesperrt (→ BR-019)
- Das Segment „echt" des Modus-Umschalters ist hart gesperrt (`disabled`/`inert`, Schloss-Icon, `aria-label` „Live im MVP gesperrt"); Default und einzig aktiv ist SIMULIERT.

### A3: Deaktivierte Klasse mit offenen Positionen (→ BR-018)
- Der Klassen-Toggle-Eintrag trägt ein Warn-Band „inaktiv – Positionen bleiben überwacht" — kein neuer Kauf, aber Exits/Überwachung bleiben sichtbar aktiv.

### E1: Poll schlägt fehl / Wert veraltet
- Das Live-Element zeigt „veraltet (seit …)" (`--warn`, D3-Text) statt einen falschen Frischwert vorzutäuschen.

### E2: Keine Bewertung / keine Daten
- Nicht bewertbarer G/V (`unrealisierter_gv_gesamt = None`) wird als „—" (`--text-3`) gezeigt, nie als 0 oder Farbzustand; leere Tabellen tragen einen definierten Empty-State je Modus.

### E3: Kandidat/Kategorie ohne Datengrundlage (→ BR-005)
- Fehlt die Datengrundlage einer Analysekategorie, wird sie als fehlend ausgewiesen (nie durch eine LLM-Schätzung ersetzt); die Detail-View zeigt den Sanity-Cap-Status (→ BR-008), wenn aktiv.

## Acceptance-Kriterien

**Query-/Read-Schicht + Boundary (§13.2/§13.7)**

- **AC1** — Jede Cockpit-View bezieht ihre Daten aus **einer** read-only Query-Funktion in `app/api/queries/**`, die ein Pydantic-View-DTO aus `app/contracts/**` liefert; dieselbe Query-Funktion wird von der HTML-Route (`app/api/ui.py`, rendert via Jinja2) **und** einer JSON-Route (`response_model=<DTO>`) konsumiert. Keine Route baut ihre Daten selbst zusammen (P4/DRY, §13.7-4).
- **AC2** — **UI-/Query-Boundary (Sicherheits-/Architektur-Invariante, prüfbar):** `app/api/ui.py` und `app/api/queries/**` importieren **nichts** aus `app/domain/sizing`, `app/domain/risikomanagement`, `app/domain/execution`, `app/orchestration/*_pipeline`, `app/orchestration/execution_service` und rufen **keinen** Depot-Schreibpfad auf; Query-Funktionen sind read-only (kein `session.add`/`commit`); Live-Kurse ausschliesslich über `LivePriceProvider` (P5). (§13.7-1/2, §4 UI-Boundary; grep/import-linter-prüfbar.)
- **AC3** — `GET /api/depot` (generalisiert das bestehende `GET /dashboard/depot`) liefert Bestand je Titel (Menge, Ø-Einstand, Live-Kurs, unrealisierter G/V, **Anlageklasse, Gewichtung** — AC14-Präzisierung, Story S-071, reine Projektion der ohnehin gelesenen Positionen), Portfolio-Aggregate (Branchen-/Klassen-Gewichtung, Cash-Quote, **Portfolio-Wert Kostenbasis**) und realisierten sowie **aggregierten unrealisierten** G/V; strikt modus-isoliert (→ BR-130). Quelle: `PositionRepository.alle_offenen_positionen`/`historie_je_titel`, Portfolio-Aggregate, `LivePriceProvider`.
- **AC4** — `GET /api/kandidaten` liefert die Liste bewerteter Kandidaten: Titel, Anlageklasse, Gesamtscore, abgeleitetes Signal (→ BR-007), die 5 Kategorie-Scores (Spinnennetz-Achsen, C-007) und `as_of`.
- **AC5** — `GET /api/kandidaten/{id}` liefert je Kandidat die Kategorie-Fakten inkl. **Quellen-ID + Timestamp** (→ BR-002), die Begründung und den Sanity-Cap-Status (→ BR-008). Fehlt die Grundlage einer Kategorie, wird sie als fehlend ausgewiesen, nie geschätzt (→ BR-005, deckt E3).
- **AC6** — `GET /api/trades` liefert die depotweite Fill-/Transaktionshistorie (Titel, Richtung, Menge, Fill-Preis, Arrival-Price, Slippage/TCA, Kosten, FX-Split, Zeit) mit Filtern `mode`/Titel/Zeitraum.
- **AC7** — **Read-Modell-Gap geschlossen:** Kandidaten-Analysen (5 Kategorie-Scores + Fakten) und die depotweite Trade-Historie werden als schlankes, HTTP-abfragbares **Read-Modell** (schlanke Read-Persistenz/Query) exponiert, das bisher nur als Domänen-Rechnung/Repository vorlag — **ohne** neues Order-Pfad-Verhalten (rein lesend). Die Query-Funktion ist der einzige Ort, an dem dieser Gap geschlossen wird (§13.3-Fussnote); Detail-Datenmodell → `dba`.
- **AC8** — `GET /api/system/status` liefert konsolidiert: Kill-Switch-Betriebszustand (→ BR-021), aktiven Modus je Anlageklasse (→ BR-019), Heartbeat, Drawdown, Halluzinations-KPI (→ BR-006) und die Gate-Ampel (→ BR-025). Quelle: `app/core/kill_switch`, `heartbeat`, `drawdown_monitor`, `hallucination_kpi`, Validierungs-Gate.
- **AC9** — `GET /api/config/anlageklassen` liefert die 11 Klassen mit Toggle-Zustand + Prio (→ C-006); `GET /api/config/depotstrategie` liefert die aktiven Depotstrategie-Grenzwerte/das Preset (C-015).
- **AC10** — Jede JSON-Read-Route trägt ein `response_model`-Pydantic-DTO (P2); HTML-Route und JSON-Route teilen dieselbe Query-Funktion (kein zweiter Datenzusammenbau, §13.7-4).

**Cockpit-Shell / Layout (§5 design)**

- **AC11** — Die Shell ist eine feste 3-Zonen-Struktur (persistente, sticky **Statusleiste** oben; **Nav** mit den fünf Kern-Views; **Hauptbereich**), auf jeder View identisch (WCAG 3.2.3). Umsetzung als Jinja2-`base`-Layout + je-View-Templates + HTMX-Partials unter `app/web/templates/`; Statics unter `app/web/static/` via `StaticFiles`-Mount in `app/main.py`; `Jinja2Templates` auf `app/web/templates`. Neue direkte Runtime-Deps `jinja2` + `python-multipart` in `[project].dependencies`.
- **AC12** — **Asset-/Supply-Chain-Invariante (prüfbar):** Kein Cockpit-Template referenziert eine externe CDN-URL; `htmx.min.js`, die Chart-Lib und CSS/Design-Tokens liegen **vendored** unter `app/web/**` (im Runtime-Image, da der Dockerfile nur `/app/app` kopiert). (ADR-013, §13.7-3; grep-prüfbar: kein `//cdn`/`https://` auf JS/CSS in `app/web/templates/**`.)
- **AC13** — Die Statusleiste zeigt Ampel, Kill-Switch, Modus, Heartbeat, Drawdown und Halluzinations-KPI **ohne Scrollen** (D2); jeder Status trägt zusätzlich Text/Kürzel + Icon/Glyph (nie nur Farbe, D3). Landmarks: genau eine `<header>`/`<nav>`/`<main>` je Seite, Skip-Link zu `<main>`, ein `<h1>` je View (WCAG 2.4.1, §9).

**HTML-Views + Schlüssel-Komponenten (§7/§8/§10 design)**

- **AC14** — **Depot-View:** KPI-Tiles (Portfolio-Wert, Cash-Quote, realisierter/unrealisierter G/V mit Dreifach-Kodierung §2.3) + Depot-Datentabelle (§7.6: Titel + Klassen-Chip §2.4, Menge, Ø-Einstand, Live-Kurs, unrealisierter G/V, Gewichtung; „nicht bewertbar" = „—", deckt E2) + Empty-State je Modus. `data-testid` gemäss §7. **Der Depot-Verlauf-Chart (§8.2) ist aus dieser AC ausgelagert nach Story S-081 (→ AC32/AC33, `@trace frontend-cockpit#AC32`).** Grund: er verlangt ein noch nicht existierendes **Portfolio-Wert-Snapshot-Read-Modell** (Zeitreihen-Persistenz — der `LivePriceProvider` liefert nur den aktuellen Kurs, keine Snapshot-Historie) und die noch offene Zeitreihen-Chart-Lib-Freigabe (Owner/designer, Nicht-Ziele). Bis S-081 landet, rendert die Depot-View KPI-Tiles + Datentabelle + Empty-State **ohne** Verlaufs-Chart — AC14 gilt damit ohne Chart-Bestandteil als vollständig erfüllt.
- **AC15** — **Kandidaten-View:** Kandidaten-Tabelle (§7.6: Titel, Klassen-Chip, Gesamtscore + Signal-Badge §7.7, `as_of`) + Detail-Panel mit **Spinnennetz-SVG** (server-gerendertes inline-SVG nach §8.1-Geometrie: 5 Achsen ab oben im 72°-Abstand, feste Kategorie-Reihenfolge Fundamental/Technisch/Qualitativ/Makro/Risiko, radiale Skala 0–10, Kaufstärke-Polygon) + begleitende Kategorie-Score-**Werttabelle** (A11y-Pflicht, `role="img"` + `aria-label`) + Kategorie-Fakten (Quellen-ID/Timestamp) + Sanity-Cap-Hinweis (→ BR-008).
- **AC16** — **Trade-Historie-View:** dichte Datentabelle (§7.6: Titel, Richtung Kauf/Verkauf als Badge, Menge, Fill-Preis, Arrival-Price, **Slippage/TCA** mit Vorzeichen-Kodierung §2.3, Kosten, FX-Split, Zeit) + Filter (Modus/Titel/Zeitraum) als HTMX-Form → Tabellen-Partial-Swap; Slippage negativ hervorgehoben (Text + Farbe).
- **AC17** — **System-Status-View:** die Statusleisten-Komponenten als Voll-View — Ampel §7.2, Kill-Switch §7.3, Modus §7.4, Heartbeat/Drawdown/Halluzinations-KPI §7.5, Gate-Ampel (→ BR-025); kritische Zustände als Vollbreite-Banner §7.10 (deckt A1). Control-Aktionen laufen über Bestätigungs-Dialoge §7.11 (siehe AC20/AC21).
- **AC18** — **Konfigurations-View:** die 11 Anlageklassen-Toggles §7.9 (an/aus als Text + Schalterstellung, nicht nur Farbe) inkl. **BR-018-Warn-Band** „inaktiv – Positionen bleiben überwacht" bei deaktivierter Klasse mit offenen Positionen (deckt A3, → BR-018); Depotstrategie-Grenzwerte/Preset (Anzeige, Control optional via `app/api/control.py`).
- **AC19** — **Live-Update:** Live-Elemente (Ampel, Live-Kurse, Heartbeat, Drawdown, KPI) pollen mit `hx-trigger="every Ns"` gegen kleine Partial-Endpunkte, die dasselbe Partial neu rendern — kein Layout-Sprung, kein Fokusverlust; ein fehlgeschlagener Poll zeigt „veraltet (seit …)" statt eines falschen Frischwerts (deckt E1); `prefers-reduced-motion` schaltet Swap-Highlights ab (§8.3, css/R03).

**Control-Plane (schreibend, getrennt — §13.7)**

- **AC20** — **Control-Boundary (Sicherheits-Invariante, prüfbar):** Alle schreibenden Betriebseingriffe — Klassen-Toggle (→ BR-017/BR-018), Modus-Schalter (→ BR-019), Kill-Switch auslösen/zurücksetzen (→ BR-021) — laufen **ausschliesslich** über POSTs in `app/api/control.py` gegen die `app/core/**`-Zustandsfunktionen bzw. Konfig-Schreibpfade, **nie** über die UI-/Query-Schicht und **nie** über Trading-Logik. HTMX rendert nach dem POST das aktualisierte Status-Partial zurück (§13.7-5).
- **AC21** — **MVP-Live-Sperre + Bestätigungspflicht (D5):** Das Segment „echt"/Live des Modus-Umschalters ist im MVP **hart gesperrt** (`disabled`/`inert`, Schloss-Icon, `aria-label` „Live im MVP gesperrt", `data-live-locked="true"`); Default und einzig aktiv ist SIMULIERT (deckt A2, → BR-019). Kill-Switch-Auslösung und -Reset (`HALTED → NORMAL`) sind **bestätigungspflichtig** über einen nativen modalen `<dialog>` mit Klartext-Konsequenz (deckt kein versehentlicher Betriebseingriff).

**Demo-/Seed-Modus (ADR-014)**

- **AC22** — Der Demo-Seed liegt in `app/demo/`, ist env-gated über `SEED_DEMO` (default **aus**, Produktion seedet nie versehentlich) und **idempotent** (Mehrfach-Ausführung = ein Zustand). Er füllt Bronze/Silver/Gold-Beispieldaten, einige Paper-Positionen (`mode="simuliert"`), Kandidaten-Analysen inkl. 5 Kategorie-Scores + Signal, Trade-Historie mit Slippage/TCA, eine Gate-Ampel und aktive/inaktive Klassen-Toggles. Er hält P7 (`Decimal`), schreibt über bestehende Repository-/Booking-Pfade oder klar markierte Fixture-Inserts und löst **keine** Order aus (kein Sizing-/Risiko-/Execution-Aufruf, → BR-001-neutral, §13.7-6). Der Demo-Zustand ist über `mode="simuliert"` von echten Daten unterscheidbar.

**Regression (§13.5)**

- **AC23** — Playwright-Regressionstests unter `tests/regression/**/*.spec.ts` decken die fünf gerenderten Cockpit-Views end-to-end gegen den Demo-Seed-Zustand ab und verankern sich an den stabilen `data-testid`/`data-*`-Attributen aus `design.md` §7/§8; Server-Rendering ändert daran nichts (Playwright ist Test-Toolchain, kein FE-Framework-Signal).

**Betriebs-Cockpit-Lücken (Konzept-Abgleich — MinTRL · Warteliste · Hybrid-Bestätigung; v2)**

> Diese drei ACs schliessen die im systematischen Abgleich Obsidian-Konzept ↔ Cockpit-Planung gefundenen Anzeige-Lücken. Sie sind **rein anzeigend/steuernd** (Anzeige-/Control-Plane, §13.7) und ändern **keine** Trading-Logik. Die zugehörigen **Backend-Write-Pfade** (Warteliste-Persistenz, Order-Anhalten für Bestätigung) sind bewusst **nicht** Teil dieser Spec (siehe Nicht-Ziele/Abhängigkeiten) — im MVP speist der Demo-Seed die Read-Modelle.

- **AC24** — **MinTRL-Restlaufzeit im System-Status-DTO:** Das `GET /api/system/status`-DTO (AC8) wird um die **MinTRL-Restlaufzeit** der laufenden Paper-Bewährung (Stufe B) erweitert — Feld `mintrl_restlaufzeit` (verbleibende Zeit bis statistische Signifikanz, als Klartext **und** maschinenlesbarer Wert/Einheit), bezogen aus dem **Stufe-B-Report des Validierungs-Gates** (→ `[[lernschleife]]`#AC9, → BR-025). Read-only: das Cockpit **zeigt** ausschliesslich den im Backend berechneten Wert (kein neuer Rechenpfad im Cockpit, Boundary AC2 gilt). Gibt es keine laufende 🟡-Bewährung (Stufe B nicht aktiv), ist der Wert `None`.
- **AC25** — **System-Status-View zeigt MinTRL-Restlaufzeit:** Neben der Gate-Ampel (AC17) zeigt die System-Status-View die MinTRL-Restlaufzeit als Klartext mit Einheit (z. B. „noch ≈ 2.7 Jahre bis statistisch signifikant") samt erklärendem Kurztext („🟢 heisst *noch nicht* statistisch bewiesen — MinTRL zeigt die verbleibende Bewährungszeit", → C-012/IDEA-025); fehlt der Wert (`None`), erscheint der definierte „—"-Empty-State, **nie** 0 oder ein Farbzustand (E2-Muster). Status nie nur über Farbe (D3); stabiles `data-testid` gemäss `design.md` §7.
- **AC26** — **Warteliste-Read-Modell + `GET /api/warteliste`:** Eine read-only Query-Funktion in `app/api/queries/**` + JSON-Route (`response_model`-DTO) liefert die vom Risikomanagement-Gate **blockierten Kauf-Kandidaten** als schlankes Read-Modell: je Eintrag Titel, Anlageklasse, geplante Grösse, **Blockade-Grund** (welche Prüfmatrix-Dimension: Klumpen-/Korrelations-/Drawdown-/Kelly-Cap-Limit, → `[[risikomanagement]]`#AC7/AC8/AC9) und **Zeitpunkt**; strikt modus-isoliert (→ BR-130). Boundary AC2 gilt: **kein** Import aus `app/domain/risikomanagement`, Daten ausschliesslich aus dem Read-Modell/Repository, **nie** per Gate-Direktaufruf. Detail-Datenmodell (Entität/Constraints/Index) → `dba`/`data-model.md`.
- **AC27** — **Warteliste-View:** Datentabelle (§7.6) mit Titel + Klassen-Chip (§2.4), geplanter Grösse, Blockade-Grund als Text/Badge und Zeitpunkt + definierter Empty-State „Keine blockierten Kandidaten im Modus SIMULIERT"; Status/Grund nie nur über Farbe (D3); stabile `data-testid` gemäss `design.md` §7. Rein lesend (kein Control-Element in dieser View).
- **AC28** — **Demo-Seed Warteliste:** Der Demo-Seed (AC22) füllt das Warteliste-Read-Modell mit deterministischen, order-freien Beispiel-Einträgen (idempotent, `mode="simuliert"`), sodass die Warteliste-View gefüllt und Playwright-testbar ist; **keine** Order-/Sizing-/Risiko-/Execution-Aufrufe (§13.7-6).
- **AC29** — **Offene-Entscheide-Read-Modell + `GET /api/entscheide/offen`:** Eine read-only Query-Funktion + JSON-Route (`response_model`-DTO) liefert die offenen, **bestätigungspflichtigen** Entscheide des Hybrid-Modus (Titel, Richtung Kauf/Verkauf, Grösse, vorgeschlagene Order, Frist/Ablauf, Begründung) als schlankes Read-Modell (→ C-016/IDEA-015/IDEA-027). Solange der autonome Paper-Modus aktiv ist (MVP-Default), ist die Liste **leer**. Boundary AC2 gilt (read-only, kein Execution-Import).
- **AC30** — **Offene-Entscheide-View + Bestätigen/Ablehnen (Control-Plane):** Die View zeigt offene Entscheide als Karten/Tabelle; **Bestätigen** und **Ablehnen** laufen als HTMX-POST **ausschliesslich** über `app/api/control.py` (Control-Boundary AC20) gegen den Entscheid-Zustand — **nie** über die UI-/Query-Schicht und **nie** direkt in die Execution-Logik; nach dem POST wird das aktualisierte Partial zurückgerendert. Jede Bestätigung ist über einen nativen modalen `<dialog>` mit Klartext-Konsequenz bestätigungspflichtig (analog AC21). **Die MVP-Live-Sperre (→ BR-019/AC21) bleibt unangetastet** — eine Bestätigung löst im MVP ausschliesslich simulierte Orders aus.
- **AC31** — **Hybrid-Flow feature-gated (post-MVP-Default aus):** Der Bestätigungs-Flow (AC29/AC30) ist über env/Konfig **feature-gated**, Default **aus** im MVP-Paper-Autonom-Betrieb (→ C-016 „Bestätigungspflicht-Modus ist späteres Feature des hybriden Betriebs"); ist er aus, zeigt die View einen definierten „autonom — keine offenen Entscheide"-Zustand und die Control-POSTs sind inaktiv/gesperrt. Bei aktivem Flag kann der Demo-Seed deterministische offene Entscheide order-frei füllen (AC22-konform).

**Depot-Verlauf-Chart — Portfolio-Wert-Snapshot-Read-Modell (ausgelagert aus AC14; Story S-081; v3)**

> Diese zwei ACs decken den aus AC14 herausgelösten **Depot-Verlauf-Chart** (§8.2) und das dafür erforderliche **Portfolio-Wert-Snapshot-Read-Modell** ab. Anders als die übrigen Read-Modelle (AC7, rein aus vorhandenen Rechnungen projiziert) braucht der Verlauf eine **über die Zeit aufgezeichnete Zeitreihe** — der `LivePriceProvider` (P5) liefert nur den aktuellen Kurs, keine Historie. Der Aufzeichnungs-Schreibpfad ist bewusst **kein** Order-/Trading-Pfad (rein operatives Telemetrie-Snapshot, → BR-001-neutral). Detail-Datenmodell (Entität/Constraints/Index/Retention) → `dba`/`data-model.md`.

- **AC32** — **Portfolio-Wert-Snapshot-Read-Modell + Aufzeichnung:** Der Portfolio-Gesamtwert (je Modus, → BR-130) wird als schlanke, append-only **Zeitreihen-Snapshot-Persistenz** aufgezeichnet (Zeitpunkt, Modus, Portfolio-Wert, optional Cash-Quote/Klassen-Split; `Decimal`, P7) und über eine read-only Query-Funktion in `app/api/queries/**` + JSON-Route `GET /api/depot/verlauf?mode=&von=&bis=` (`response_model`-DTO aus `app/contracts/**`) exponiert. **Aufzeichnungs-Mechanik = periodischer Snapshot-Job** (Scheduler, im Intervall) — **nicht** Write-on-Read: die Query-/UI-Schicht bleibt strikt read-only (Boundary AC2 gilt unverändert; ein Write-on-Read-Pfad würde AC2 verletzen). Der Snapshot-Job berechnet den Wert ausschliesslich aus vorhandenen Lese-Ports (`PositionRepository`, `LivePriceProvider`) und löst **keine** Order/Sizing/Risiko/Execution aus (§13.7-6). Existiert (noch) keine Historie, liefert die Query eine leere Reihe (deckt E2-Muster). Detail-Datenmodell (Tabelle/Migration/Retention/Index) → `dba` (db-pflichtig).
- **AC33** — **Depot-Verlauf-Chart in der Depot-View:** Die Depot-View zeigt den Portfolio-Verlauf als Zeitreihen-Chart (§8.2, Zeit auf X, Portfolio-Wert auf Y; End-Delta trägt §2.3-G/V-Kodierung, nicht nur Farbe → D3) aus dem Snapshot-Read-Modell (AC32). **Chart-Technik (Owner-Entscheidung 2026-07-19, bindend — ersetzt die zuvor offene Owner-/designer-Entscheidung dieser AC):** **TradingView Lightweight Charts** (vendored, Apache 2.0, Area-/Linien-Chart) unter `app/web/static/vendor/lightweight-charts.standalone.production.js` (Quelle/Version/SHA-256 in `app/web/static/vendor/README.md`, Muster S-064/S-064-Vorbild `htmx.min.js`). Der zuvor als Default gesetzte **server-SVG-Ansatz** (lib-frei, analog Spinnennetz §8.1) und die **uPlot-Empfehlung** (§8.2) gelten für den Depot-Verlauf-Chart damit als **überholt** (nicht gestrichen — beide bleiben als dokumentierte Historie/Alternative für künftige Zeitreihen-Charts außerhalb dieser AC, z. B. eine spätere Drawdown-Historie, die diese Owner-Entscheidung nicht automatisch erbt). Lizenz-Pflicht (Apache 2.0): die Standalone-Datei zeigt das TradingView-Attribution-Logo im Chart standardmäßig — es wird **nicht** deaktiviert. Leerer/kurzer Verlauf (< 2 Snapshots) → definierter Empty-State („Noch keine Verlaufsdaten — Aufzeichnung läuft"), nie ein Fake-Wert. Chart-Container mit fester `--min-height` (kein Layout-Sprung); `prefers-reduced-motion` schaltet die Einzeichen-Animation ab (§8.2/css R03) — die Lib zeichnet Daten per `setData` ohnehin ohne Einzeichen-Animation, das Kriterium ist damit ohne Zusatzcode erfüllt. Stabile `data-testid` gemäss `design.md` §7/§8. Ergänzend zum Chart selbst steht eine begleitende **Werte-Zusammenfassung** (Zeitraum, Anfangs-/Endwert, Veränderung — analog zur Spinnennetz-Werttabelle §8.1, A11y-Pflicht, kein Hover-only-Inhalt). Der Demo-Seed (AC22) füllt das Snapshot-Read-Modell deterministisch + order-frei, sodass der Chart gefüllt und Playwright-testbar ist.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace frontend-cockpit#AC<n>[,BR-NNN]`.

## Verträge

Jeder Read-Endpunkt = **Query-Funktion (read-only) + JSON-Route (`response_model`) + HTML-View** (§13.2). JSON-Pfade additiv unter `/api/**`; `GET /dashboard/depot` bleibt bestehen und wird von der Depot-View mitgenutzt/generalisiert.

| View | JSON-Read-Route | View-DTO (Inhalt) | Andockpunkt (bestehend) |
|---|---|---|---|
| Depot | `GET /api/depot?mode=` | Bestand je Titel + Portfolio-Aggregate + realisierter/unrealisierter G/V | `PositionRepository`, Portfolio-Aggregate, `LivePriceProvider` |
| Depot-Verlauf (v3, S-081) | `GET /api/depot/verlauf?mode=&von=&bis=` | Portfolio-Wert-Zeitreihe (Zeitpunkt, Modus, Wert, optional Cash/Klassen-Split) (AC32) | Portfolio-Wert-Snapshot-Read-Modell (AC32, Snapshot-Job); `PositionRepository`, `LivePriceProvider` |
| Kandidaten | `GET /api/kandidaten` | Liste: Titel, Klasse, Gesamtscore, Signal, 5 Kategorie-Scores, `as_of` | `domain/scoring`, Kandidaten-Analyse-Read-Modell (AC7) |
| ↳ Detail | `GET /api/kandidaten/{id}` | Kategorie-Fakten (Quellen-ID/Timestamp), Begründung, Sanity-Cap-Status | `domain/analysis_new`, LLM-Grounding-Output |
| Trades | `GET /api/trades?mode=&titel=&von=&bis=` | depotweite Fills/Transaktionen inkl. Slippage/TCA, FX-Split | `PositionRepository.historie_je_titel`, depotweites Historien-Read-Modell (AC7) |
| System-Status | `GET /api/system/status` | Kill-Switch, Modus je Klasse, Heartbeat, Drawdown, Halluz-KPI, Gate-Ampel, **MinTRL-Restlaufzeit** (AC24) | `app/core/**`, Validierungs-Gate (Stufe-B-Report, → `[[lernschleife]]`) |
| Konfiguration | `GET /api/config/anlageklassen` · `GET /api/config/depotstrategie` | 11 Klassen (Toggle + Prio) · Depotstrategie-Grenzwerte/Preset | `domain/assetclasses`, Konfig |
| Warteliste (v2) | `GET /api/warteliste?mode=` | blockierte Kauf-Kandidaten: Titel, Klasse, geplante Grösse, Blockade-Grund, Zeitpunkt (AC26) | Warteliste-Read-Modell (AC26); Blockade-Signal → `[[risikomanagement]]`#AC7 |
| Offene Entscheide (v2) | `GET /api/entscheide/offen` | bestätigungspflichtige Hybrid-Entscheide: Titel, Richtung, Grösse, Order, Frist, Begründung (AC29) | Entscheid-Read-Modell (AC29); feature-gated (AC31) |

**Control-Plane (POST, `app/api/control.py`):** Toggle je Klasse, Modus-Schalter (Live gesperrt), Kill-Switch auslösen/zurücksetzen, **Hybrid-Entscheid bestätigen/ablehnen** (feature-gated, AC30/AC31) → ausschliesslich `app/core/**`-Zustandsfunktionen (z. B. `kill_switch.ausloesen`/`freigeben`) bzw. Konfig-/Entscheid-Zustandspfade; Rückgabe = aktualisiertes Partial (HTML).

**Asset-/Template-Ort:** Templates `app/web/templates/`, Statics `app/web/static/` (inkl. `static/vendor/htmx.min.js`, `static/css/tokens.css`). **Kein CDN.**

## Edge-Cases & Fehlerverhalten

- Nicht bewertbarer G/V (`None`) → „—", nie 0/Farbe (E2).
- Fehlgeschlagener Poll → „veraltet (seit …)", kein Frischwert-Fake (E1).
- Leere Tabelle → definierter Empty-State je Modus (z. B. „Keine offenen Positionen im Modus SIMULIERT").
- Kandidat mit fehlender Kategorie-Datengrundlage → als fehlend ausgewiesen, nie geschätzt (→ BR-005, E3). **Spinnennetz-Präzisierung (AC15):** Achsen/Gitter/Labels bleiben immer vollständig gezeichnet; fehlt mindestens eine Kategorie, wird jedoch KEINE Kaufstärke-Fläche (Polygon) gezeichnet — ein fabrizierter Polygon-Punkt für eine fehlende Kategorie wäre selbst eine Schätzung. Die begleitende Werttabelle zeigt für die fehlende Kategorie „—" (E2-Muster).
- Kill-Switch `HALTED` / Live-Modus → Vollbreite-Banner mit maximaler Priorität (A1, D5).
- Keine laufende Stufe-B-Bewährung (`mintrl_restlaufzeit = None`) → MinTRL „—", nie 0/Farbe (AC25, E2-Muster).
- Leere Warteliste → definierter Empty-State „Keine blockierten Kandidaten im Modus SIMULIERT" (AC27).
- Hybrid-Flow feature-gated aus (MVP-Default) → „autonom — keine offenen Entscheide", Control-POSTs gesperrt (AC31).

## NFRs

- **Sicherheit/Boundary:** UI-/Query-Schicht ist rein lesend gegenüber der Domäne (AC2); schreibende Betriebseingriffe nur über die Control-Plane (AC20); Demo-Seed env-gated + order-frei (AC22). Diese drei sind harte, grep-/import-linter-prüfbare Review-Kriterien (§13.7).
- **Zugang (offen, §13.7):** Das Cockpit steuert Kill-Switch/Modus — ein Zugangsschutz (mind. einfacher Auth-Layer) ist vor jedem nicht-lokalen Deploy zu klären; im MVP local-only (nicht Teil dieser Spec, hier vermerkt).
- **A11y:** WCAG 2.2 AA (Kontrast berechnet, Status nie nur Farbe, sichtbarer Fokus, Tastaturbedienbarkeit, Live-Regionen) gemäss `design.md` §9.
- **Deploy:** ein Docker-Image, kein Node-Build; `uvicorn app.main:app` bleibt einzige Deploy-Einheit (§13.4).
- **Latenz:** Live-Update über HTMX-Polling (kein WebSocket, kein Sub-Sekunden-Bedarf, NFR §10 architecture).

## Nicht-Ziele

- **Kein SPA-/Node-Build** (ADR-012); keine hoch-interaktiven Client-Zustände (Drag&Drop/Offline).
- **Kein neues Order-/Sizing-/Risiko-/Execution-Verhalten** — die Anzeige-Schicht liest nur; das Read-Modell-Gap wird rein lesend geschlossen (AC7).
- **Kein Auth-Layer** im MVP (local-only, §13.7); kommt er, gilt WCAG 3.3.8.
- **Kein DB-Detailmodell** des Kandidaten-/Trade-/Warteliste-/Entscheid-Read-Modells hier — Entitäten/Constraints/Indizes → `dba`/`data-model.md`.
- **Keine allgemeine Chart-Lib-Datei-Freigabe über AC33 hinaus** — Spinnennetz bleibt server-SVG (keine Lib, §8.1). Für den **Depot-Verlauf-Chart** (AC33) ist die Chart-Lib-Frage seit Owner-Entscheidung 2026-07-19 (Story S-081) **geklärt: TradingView Lightweight Charts** (vendored, Apache 2.0) — die zuvor offene Owner-/designer-Entscheidung dieser AC ist damit beantwortet. Diese Freigabe gilt **nur für AC33**; für andere künftige Zeitreihen-Charts (z. B. eine spätere Drawdown-Historie-View) bleibt die Lib-Wahl weiterhin offen und ist nicht Teil dieser Story.
- **Kein Depot-Verlauf-Chart in dieser Spec-Version umgesetzt in AC14** — der Verlauf (§8.2) ist nach **Story S-081** (AC32/AC33) ausgelagert, weil er ein noch nicht existierendes Portfolio-Wert-Snapshot-Read-Modell (Zeitreihen-Persistenz) voraussetzt. AC14 gilt ohne Chart-Bestandteil als erfüllt.
- **Keine MinTRL-Berechnung** — das Cockpit zeigt nur den vom Validierungs-Gate (Stufe-B-Report) gelieferten Wert (AC24); die Berechnung selbst bleibt in `[[lernschleife]]`#AC9.
- **Keine Warteliste-Schreib-/Re-Prüf-Mechanik** — das Cockpit **zeigt** die Warteliste nur read-only (AC26/AC27). Das **Erfassen** blockierter Käufe im Order-Pfad und die Re-Prüf-/Ablauf-Mechanik bleiben offen und sind Backend-Scope (Risikomanagement/Handel, → `[[risikomanagement]]` „Offene Punkte"). Im MVP speist ausschliesslich der Demo-Seed das Read-Modell (AC28).
- **Keine Order-Anhalte-Mechanik für den Hybrid-Modus** — das tatsächliche Anhalten einer Order zur Bestätigung (Execution-Pause) ist post-MVP-Backend-Scope (Ausführung/Handel, → C-016 „späteres Feature"); diese Spec deckt nur die Cockpit-Anzeige-/Control-Fläche hinter dem Feature-Flag (AC29–AC31).

## Abhängigkeiten

- Depotmodul (`[[depot]]`) — `PositionRepository`, Portfolio-Aggregate, Transaktionshistorie (Depot-/Trade-View, AC3/AC6).
- Analyse-Framework (`[[analyse-framework]]`) + Analysepfade (`[[analyse-pipelines]]`) + LLM-Grounding (`[[llm-grounding]]`) — Kandidaten-Scores/Fakten (AC4/AC5).
- Betriebssicherung (`[[betriebssicherung]]`) — Kill-Switch/Heartbeat/Drawdown/Halluz-KPI (AC8/AC17/AC20).
- Anlageklassen-Konfiguration (`[[anlageklassen-config]]`) — Toggles/Prio/Depotstrategie (AC9/AC18).
- Lernschleife (`[[lernschleife]]`) — Gate-Ampel (AC8, → BR-025).
- Socket-Live-Kurs-Zugriff (`LivePriceProvider`, Cross-Cutting, P5) — Live-Kurse (AC3/AC14).
- Depotmodul + Scheduler (`[[depot]]` / `[[scheduler]]`) + `dba` — Portfolio-Wert-Snapshot-Read-Modell + periodischer Aufzeichnungs-Job (AC32/AC33, Story S-081). Zeitreihen-Chart-Lib für AC33 = TradingView Lightweight Charts (Owner-Entscheidung 2026-07-19, s. o.) — für andere künftige Zeitreihen-Charts weiterhin offen.
- Lernschleife (`[[lernschleife]]`) — MinTRL-Restlaufzeit aus dem Stufe-B-Report (AC24/AC25, → `[[lernschleife]]`#AC9). Kein neuer Rechenpfad im Cockpit.
- Risikomanagement (`[[risikomanagement]]`) — Blockade-Signal/Warteliste (AC26–AC28, → `[[risikomanagement]]`#AC7). **Offen (Backend-Scope):** Warteliste-Persistenz-/Write-Path (blockierte Käufe erfassen) — nicht Teil dieser Spec.
- Ausführung (`[[ausfuehrung-paper]]`) — Hybrid-Bestätigungs-Modus (AC29–AC31, → C-016). **Offen (post-MVP-Backend-Scope):** Order-Anhalte-Mechanik zur Bestätigung — nicht Teil dieser Spec.
- Geschäftsregeln: BR-001, BR-002, BR-005, BR-006, BR-007, BR-008, BR-017, BR-018, BR-019, BR-021, BR-022, BR-025, BR-130 (`architecture.md` / `data-model.md`).
- Architektur: §13 (ADR-012/013/014), §4 UI-Boundary. Design: `docs/design.md` §5/§7/§8/§9/§10.
