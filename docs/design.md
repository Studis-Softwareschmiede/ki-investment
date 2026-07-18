# Design-System / UX-Vorgaben — ki-investment Betriebs-Cockpit

> **Bindend für `coder` und `requirement`.** Diese Datei ist das Design-System für die server-gerenderte
> Cockpit-UI (HTMX + Jinja2, `architecture.md` §13 / ADR-012/013/014). Sie legt Tokens, Layout, Komponenten,
> Charts und Accessibility fest; der `coder` setzt sie in CSS/Templates unter `app/web/**` um, der `reviewer`
> prüft Konformität (Kontrast/Fokus/Spacing/A11y) über die UI-Pack-Checklisten (`css`/`html`).
> Sie verletzt **keine** Architektur-Boundary: das Design betrifft ausschließlich die Anzeige-/Control-Plane
> (`app/api/ui.py`, `app/api/queries/**`, `app/api/control.py`), nie die Trading-Logik (C-017, §13.7).
>
> **Vorentscheidungen (nicht neu verhandelt):** Server-Rendering HTMX+Jinja2 (ADR-012), vendored Assets kein CDN
> (ADR-013), Demo-Seed für gefüllte Views (ADR-014). Geld ist `Decimal` (P7) — die UI **zeigt** nur, rechnet nicht.

---

## 1. Design-Prinzipien (Cockpit-Doktrin)

Das Cockpit ist ein **Betriebs-/Trading-Terminal**, kein Consumer-Produkt. Sechs bindende Leitsätze:

- **D1 — Nüchtern & informationsdicht.** Ziel ist Ablesbarkeit vieler Zahlen/Status auf einen Blick, nicht
  Marketing-Wirkung. Keine dekorativen Illustrationen, keine Verläufe/Schatten als Selbstzweck, kein Whitespace-
  Luxus. Dichte Tabellen, kompakte Tiles, ruhige Flächen.
- **D2 — Status ist die Hauptsprache.** Ampel (grün/gelb/rot), Kill-Switch, Modus (echt/simuliert), Heartbeat,
  Drawdown und Halluzinations-KPI sind jederzeit ohne Scrollen sichtbar (persistente Statusleiste, §6).
- **D3 — Status niemals nur über Farbe** (WCAG 1.4.1). Jeder Zustand trägt zusätzlich **Text/Kürzel**, ein **Icon/
  Glyph** und/oder ein **Muster/Vorzeichen**. Farbe ist Verstärkung, nie alleiniger Träger.
- **D4 — Zahlen-Klarheit.** Geldbeträge und Mengen in tabellarischen Ziffern (`tabular-nums`), rechtsbündig,
  feste Dezimalstellen, monospaced Geld-Font (§4). Vorzeichen (`+`/`−`) explizit bei G/V.
- **D5 — Sicherheitszustände sind unübersehbar.** Der reale (Live-)Modus, ein ausgelöster Kill-Switch oder ein
  roter Betriebszustand werden mit maximaler visueller Priorität dargestellt (Vollbreite-Banner, hoher Kontrast).
  Destruktive/scharfe Aktionen sind bestätigungspflichtig.
- **D6 — Dark-first, beide Themes.** Cockpit-typisch ist **Dark** der Default; **Light** ist gleichwertig
  gepflegt. Umsetzung über EIN Token-Set via `light-dark()` (`color-scheme: light dark`, css/R05) — keine
  doppelten Farbblöcke, kein Theme-Divergieren.

---

## 2. Farbsystem

Alle Farben liegen als **Design-Tokens** (CSS Custom Properties, css/R01) auf `:root`, ausgeprägt über
`light-dark(<light>, <dark>)`. Voraussetzung: `:root { color-scheme: light dark; }` (sonst greift `light-dark()`
nicht — css/R05). **Keine Magic-Farbwerte** in Templates/Komponenten-CSS; nur Token-Referenzen.

Notation unten: `--token: light-dark(LIGHT, DARK)`. Kontrastwerte sind **berechnet** (WCAG-Verfahren) gegen die
jeweils genannte Fläche; AA verlangt Body ≥ 4.5:1, Large/UI-Grafik ≥ 3:1.

### 2.1 Neutrale Flächen & Text

| Token | light | dark | Rolle |
|---|---|---|---|
| `--bg` | `#F6F8FA` | `#0E1116` | App-Hintergrund (unterste Ebene) |
| `--surface-1` | `#FFFFFF` | `#161B22` | Panels, Statusleiste |
| `--surface-2` | `#FFFFFF` | `#1C2129` | Tiles/Karten, Tabellen-Container |
| `--surface-3` | `#EFF2F5` | `#262C36` | Raised/Hover, Zebra-Zeile, aktive Tabs |
| `--border` | `#D0D7DE` | `#2D333B` | Trennlinien, Karten-/Tabellen-Rahmen |
| `--border-strong` | `#AFB8C1` | `#3D444D` | betonte Rahmen, Fokus-Umfeld |
| `--text-1` | `#1F2328` | `#E6EDF3` | Primärtext, Zahlen |
| `--text-2` | `#656D76` | `#9DA7B3` | Sekundärtext, Labels, Achsen |
| `--text-3` | `#8C959F` | `#6E7681` | Tertiär/deaktiviert, Platzhalter |

**Berechnete Kontraste (dark):** `--text-1`↔`--bg` = **16.0:1**; `--text-2`↔`--bg` = **7.8:1**;
`--text-2`↔`--surface-2` ≈ **6.9:1** (alle ≥ AA). **Light:** `--text-1`(#1F2328)↔`--bg`(#F6F8FA) ≈ **15.3:1**;
`--text-2`(#656D76)↔`#FFFFFF` ≈ **5.1:1** (AA). `--text-3` ist **nur** für nicht-essenzielle/deaktivierte Zustände
(muss AA nicht als Body erfüllen, darf aber nie alleiniger Informationsträger sein — D3).

### 2.2 Semantische Status-/Ampel-Farben

Reserviert für **Betriebsstatus** (Ampel 🟢🟡🔴, Kill-Switch, Heartbeat, Gate). Zwei Ausprägungen je Semantik:
`*-fg` (Text/Icon auf neutraler Fläche) und `*-solid` (Füllung, dann Text `--on-solid`).

| Token | light | dark | Kontrast `-fg` vs. `--bg` |
|---|---|---|---|
| `--ok-fg` | `#1A7F37` | `#3FB950` | light 5.1:1 · dark 7.4:1 |
| `--ok-solid` | `#1A7F37` | `#238636` | Füllung (Text `--on-solid`) |
| `--warn-fg` | `#9A6700` | `#D29922` | light 4.9:1 · dark 7.5:1 |
| `--warn-solid` | `#9A6700` | `#9E6A03` | Füllung |
| `--danger-fg` | `#CF222E` | `#F85149` | light 5.4:1 · dark 5.6:1 |
| `--danger-solid` | `#CF222E` | `#DA3633` | Füllung |
| `--info-fg` | `#0969DA` | `#58A6FF` | light 4.6:1 · dark 6.4:1 |
| `--on-solid` | `#FFFFFF` | `#FFFFFF` | Text auf `*-solid`-Füllungen (≥ 4.5:1 geprüft je Solid) |

**D3-Pflicht:** Ampel-Zustände tragen **immer** zusätzlich Text + Form-Glyph:
🟢 = `●` + „AKTIV/GRÜN", 🟡 = `◐` + „PAPER/GELB", 🔴 = `▲` + „STOP/ROT". Nie nur der Farbpunkt.

### 2.3 Gewinn/Verlust (G/V) — nicht rein farbcodiert

G/V nutzt zwar grün/rot als Verstärkung, **darf aber nie allein daran erkennbar sein** (Rot-Grün-Schwäche, D3).
Verbindliche Dreifach-Kodierung je G/V-Wert:

- **Vorzeichen** `+` / `−` immer sichtbar (nie weggelassen, auch nicht bei 0 → `±0`),
- **Richtungs-Glyph** `▲` (Gewinn) / `▼` (Verlust) / `▬` (neutral) vor/nach dem Wert,
- **Farbe** `--gain` / `--loss` / `--text-2` als Verstärkung.

| Token | light | dark |
|---|---|---|
| `--gain` | `#1A7F37` | `#3FB950` |
| `--loss` | `#CF222E` | `#F85149` |

Bewusst identisch mit `--ok/--danger` (Gewinn=positiv=grün, Verlust=negativ=rot) — konsistente mentale Zuordnung.
**Nicht bewertbar** (`unrealisierter_gv_gesamt = None`, siehe `DepotDashboardResponse`): als `—` in `--text-3`,
nie als 0 oder als Farbzustand (kein Gewinn/Verlust-Signal vortäuschen).

### 2.4 Anlageklassen-Kodierung (11 Klassen, C-006)

Kategoriale Palette für die 11 Anlageklassen (Chips, Tabellen-Tags, Chart-Serien pro Klasse). **Reine Verstärkung**
— jede Klasse trägt **immer** ihr Kürzel als Text (D3); die Farbe ersetzt das Label nie. Bewusst **außerhalb** der
Status-Semantik-Töne (kein reines Ampel-Grün/Gelb/Rot in der Klassenpalette → keine Verwechslung Status↔Klasse).

| # | Klasse | Kürzel | `--ac-N` (dark, auf `--surface-2` als Chip mit Textlabel) |
|---|---|---|---|
| 1 | Aktien | `AKT` | `#4C9AFF` |
| 2 | ETFs | `ETF` | `#6EE7B7` |
| 3 | Cash/Geldmarkt | `CSH` | `#94A3B8` (neutral — Cash) |
| 4 | Obligationen | `OBL` | `#38BDF8` |
| 5 | Aktive Fonds | `FND` | `#A78BFA` |
| 6 | Immobilien | `IMM` | `#F0883E` |
| 7 | Kryptowährungen | `CRY` | `#F472B6` |
| 8 | Rohstoffe | `ROH` | `#E3B341` |
| 9 | Infrastrukturfonds | `INF` | `#818CF8` |
| 10 | FX | `FX` | `#2DD4BF` |
| 11 | Derivate | `DER` | `#C084FC` |

Chip-Umsetzung: Farbe erscheint als **Rand/Punkt** links des Kürzels, Chip-Fläche `--surface-3`, Text `--text-1`
(damit der Kontrast des **Labels** immer AA erfüllt, unabhängig vom Klassen-Farbton). Für Light-Theme dieselben
Hues, aber um ~1 Stufe abgedunkelt (via `color-mix(in oklab, <hue> 70%, black)` zulässig, css/R08) — Token-Paare
`--ac-1..--ac-11` als `light-dark()`.

### 2.5 Interaktion & Fokus

| Token | light | dark | Rolle |
|---|---|---|---|
| `--accent` | `#0969DA` | `#58A6FF` | Links, primäre Aktion, aktive Nav, Chart-Primärserie |
| `--accent-hover` | `#0550AE` | `#79C0FF` | Hover/Active |
| `--focus-ring` | `#0969DA` | `#58A6FF` | Fokus-Outline (2px solid + 2px offset) |
| `--selection` | `#DDF4FF` | `#193B5E` | Textauswahl/Zeilenauswahl-Hintergrund |

Fokus-Indikator (§9): `outline: 2px solid var(--focus-ring); outline-offset: 2px;` — **nie** `outline:none` ohne
gleichwertigen Ersatz. Der Ring erfüllt gegen `--bg` ≥ 3:1 (UI-Grafik-Kontrast).

---

## 3. Typografie

Zahlen-/tabellenlastig. **Keine vendorspezifische Font-Datei zwingend** (Offline-first, ADR-013) — System-Stacks
zuerst; wird ein Font vendored, liegt er als WOFF2 unter `app/web/static/fonts/` (kein CDN).

- **UI-Sans** (`--font-ui`): `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`
- **Mono/Numerik** (`--font-mono`): `ui-monospace, "SF Mono", "Cascadia Mono", "Segoe UI Mono", Consolas, "Liberation Mono", monospace`

**Zahlen-Regeln (bindend):**
- Geldbeträge, Mengen, Kurse, Scores, G/V, Slippage → `--font-mono` **oder** `font-variant-numeric: tabular-nums`
  (mind. tabellarische Ziffern), **rechtsbündig** in Tabellen, feste Dezimalstellen (Geld 2, Kurse ≤ 4, Score 1,
  Prozent 1–2). Dezimalpunkte richten dadurch vertikal aus.
- Geldbeträge tragen Währung als kontextuelles Suffix/Header (`CHF`), nicht je Zelle wiederholt wenn spaltenweit.
- `as_of`/Timestamps in Mono, ISO-nah, `--text-2`.

**Type-Scale** (Basis `--fs-base` 0.875rem = 14px; `:root` bleibt 16px, damit Browser-Zoom/rem sauber skalieren):

| Token | Größe | Zeilenhöhe | Verwendung |
|---|---|---|---|
| `--fs-2xl` | 2.5rem / 40px | 1.1 | Hero-KPI (z. B. großer Portfolio-Wert, Drawdown-%) |
| `--fs-xl` | 1.75rem / 28px | 1.15 | Tile-Hauptwert |
| `--fs-lg` | 1.25rem / 20px | 1.25 | Sektionsüberschrift, sekundärer Tile-Wert |
| `--fs-md` | 1rem / 16px | 1.4 | View-Titel, Fließtext-Absätze |
| `--fs-base` | 0.875rem / 14px | 1.5 | Body, Standard-Tabellenzelle, Buttons |
| `--fs-sm` | 0.8125rem / 13px | 1.45 | dichte Tabellen, Meta, Chip-Text |
| `--fs-xs` | 0.75rem / 12px | 1.4 | Labels, Achsenbeschriftung, Badges |

Gewichte: 400 (Body), 500 (Labels/Tabellen-Header/Buttons), 600 (Tile-Werte/Überschriften). Keine Weights < 400
(dünne Fonts auf dunkel = schlechter Kontrast). Überschriften optional `text-wrap: balance` (css/R11, ≤ 6 Zeilen).

---

## 4. Spacing, Radius, Elevation, Motion

**Spacing-Skala** (4px-Basis, css/R01 — keine Werte außerhalb der Skala, sonst reviewer-**Important**):

`--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16 · `--space-5` 24 · `--space-6` 32 ·
`--space-8` 48 · `--space-10` 64 (px). Cockpit nutzt vorwiegend 4/8/12/16; 24+ nur für Sektions-/Shell-Abstände.
Tabellen-Zellpadding dicht: `--space-1` vertikal / `--space-3` horizontal.

**Radius:** `--radius-sm` 4px (Chips/Badges/Inputs) · `--radius-md` 8px (Tiles/Karten/Tabellen-Container) ·
`--radius-full` 999px (Ampelpunkt, Pills). Cockpit bleibt eckig-nüchtern — keine großen Radien.

**Elevation:** flach. Trennung primär über `--border` + Flächenwechsel (`--surface-1/2/3`), **nicht** über große
Schatten. Höchstens `--shadow-1` (`0 1px 2px rgb(0 0 0 / .12)`) für Overlays/Popover/Toast und `--shadow-2`
(`0 8px 24px rgb(0 0 0 / .24)`) für Modals/Dialoge. In Dark bewusst sparsam.

**Motion:** kurz und funktional. `--motion-fast` 120ms, `--motion-base` 200ms, Easing `ease-out`. Nur State-
Feedback (Toggle, Hover, Toast-Ein/Ausblenden, Partial-Swap-Highlight). **Pflicht:** unter
`@media (prefers-reduced-motion: reduce)` alle nicht-essenziellen Transitions/Animationen abschalten (css/R03) —
inkl. HTMX-Swap-Highlights und View-Transitions (falls css/R10 genutzt: `::view-transition-old/new` → `animation:none`).

---

## 5. Layout — Cockpit-Shell

Feste 3-Zonen-Shell, auf jeder View identisch (Konsistenz = WCAG 3.2.3/3.2.6 Consistent Navigation/Help):

```
┌───────────────────────────────────────────────────────────────┐
│  A) STATUSLEISTE (persistent, oben, voll breit, sticky)        │
│     [Ampel] [Kill-Switch] [Modus echt/SIMULIERT] [Heartbeat]   │
│     [Drawdown] [Halluz-KPI]            [Theme] [as_of/Uhr]      │
├──────────┬────────────────────────────────────────────────────┤
│ B) NAV   │  C) VIEW-INHALT (Hauptbereich, scrollbar)           │
│ (seite/  │     <main> — View-Titel + Inhalt der Kern-View      │
│  oben)   │                                                     │
│ Depot    │                                                     │
│ Kandidat.│                                                     │
│ Trades   │                                                     │
│ System   │                                                     │
│ Konfig   │                                                     │
└──────────┴────────────────────────────────────────────────────┘
```

- **A) Statusleiste** — `<header role="banner">`, sticky top, `--surface-1`, immer sichtbar (D2). Enthält die
  Betriebs-Status-Indikatoren (§7.2–7.5) links, Utility (Theme-Toggle, `as_of`) rechts. Wird per HTMX-Polling
  aktualisiert (§8). Bei kritischem Zustand (Kill-Switch HALTED / Live-Modus) wächst sie um ein **Vollbreite-
  Banner** darunter (D5).
- **B) Navigation** — `<nav aria-label="Hauptnavigation">`, fünf Kern-Views (Depot · Kandidaten · Trades · System ·
  Konfiguration). Desktop: schmale Seitenspalte (max. 200px) mit Icon+Label; ab `< 900px`: horizontale Topbar /
  Off-Canvas via `<dialog>`/`popover` (html/R04). Aktiver Eintrag mit `aria-current="page"` + `--accent`-Marker
  (nicht nur Farbe: zusätzlich linker Balken/Fettung, D3).
- **C) Hauptbereich** — `<main>` (genau eine Landmark, Skip-Link „Zum Inhalt" davor, WCAG 2.4.1). Grid der View
  (§10). Ein `<h1>` je View (View-Titel).

**Grid:** CSS Grid für die Shell (`grid-template: "status status" auto / auto 1fr`), Content-Grids je View mit
`repeat(auto-fill, minmax(…, 1fr))` für Tile-Reihen. Komponenten, die im Content **und** in schmalen Panels
vorkommen (z. B. Status-Tile), nutzen `@container`-Queries statt Viewport-`@media` (css/R04; Eltern
`container-type: inline-size`) — so reagiert das Tile auf seinen Platz, nicht auf den Viewport.

---

## 6. Breakpoints & Responsive

Mobile-first (`@media (min-width: …)`, css/R02). Das Cockpit ist **desktop-primär** (Terminal), aber auf Tablet
bedienbar und auf Phone lesbar (Read-only-Notfallblick auf Status).

| Breakpoint | Bereich | Verhalten |
|---|---|---|
| Basis (< 600px, Phone) | 1-spaltig | Nav als Topbar/Off-Canvas; Tiles gestapelt; breite Tabellen → horizontal scrollbar in `overflow-x:auto`-Wrapper **mit** sichtbarem Scroll-Hinweis + sticky erster Spalte (Titel). Charts volle Breite, min-height gewahrt. |
| `--bp-md` 600px (Tablet) | 2-spaltig Tiles | Nav-Topbar bleibt; Tabellen zeigen Kernspalten, Sekundärspalten einklappbar. |
| `--bp-lg` 900px (Laptop) | Nav-Seitenspalte erscheint | Volles Tabellen-Set; Tile-Grid 2–3 Spalten. |
| `--bp-xl` 1280px (Desktop) | Cockpit-Vollbild | Tile-Grid 3–4 Spalten; Kandidaten-Liste + Spinnennetz-Detail nebeneinander. |

**Regeln:** Keine Information geht responsive verloren — Sekundärspalten werden eingeklappt/aufklappbar
(`<details>`, html/R07), nicht entfernt. Tabellen nie abschneiden ohne Scroll-Zugang. Touch-Targets siehe §9.

---

## 7. Komponenten-Katalog (bindend)

Jede Komponente: **Anatomie · Zustände · A11y · Test-Anker**. Test-Anker sind stabile `data-testid`/`data-*`-
Attribute für Playwright (§13.5) — der `coder` setzt sie exakt so. Alle Komponenten server-gerendert (Jinja-
Partial), HTMX-swappbar.

### 7.1 KPI-/Status-Tile
- **Anatomie:** `<article class="tile">` mit Label (`--fs-xs`, `--text-2`, oben), Hauptwert (`--fs-xl`, `--font-mono`,
  `--text-1`), optional Delta-Zeile (G/V-Kodierung §2.3) und Mini-Sparkline (§8.2).
- **Zustände:** normal · positiv/negativ (Delta) · Warn/Kritisch (Rand `--warn-fg`/`--danger-fg` + Icon) · leer
  („—", `--text-3`, kein Nullwert vortäuschen).
- **A11y:** Label programmatisch mit Wert verknüpft; Delta-Vorzeichen+Glyph im Text (nicht nur Farbe).
- **Anker:** `data-testid="tile-<kennzahl>"`, Wert in `<span data-value>`.

### 7.2 Ampel-Indikator (Betriebs-/Gate-Status, BR-025)
- **Anatomie:** `●/◐/▲`-Form-Glyph (`--radius-full` Punkt) + Textlabel + Kurzbegründung. Drei Zustände 🟢/🟡/🔴.
- **Dreifach-Kodierung (D3):** Farbe (`--ok/--warn/--danger-fg`) **+** unterschiedliche Form (Kreis/Halbkreis/
  Dreieck) **+** Text („GRÜN – Regel aktiv" / „GELB – nur Paper" / „ROT – archiviert").
- **A11y:** `role="status"` mit `aria-label`, das den Zustand als Wort nennt.
- **Anker:** `data-testid="ampel"`, `data-ampel-state="gruen|gelb|rot"`.

### 7.3 Kill-Switch-Control (BR-021)
- **Anatomie:** persistenter Bereich in der Statusleiste: aktueller **Betriebszustand**
  (`NORMAL · HALT_ANGEFORDERT · FLATTEN · HALTED`) als Badge + primärer Aktionsbutton.
- **Interaktion (D5):** Auslösen ist **bestätigungspflichtig** — Button öffnet ein natives `<dialog>` (modal, via
  `command`/`commandfor` html/R08; Fokus-/A11y-Management durch Browser) mit klartext Konsequenz („storniert offene
  Orders, stellt glatt, sperrt Käufe"). Bestätigung → HTMX-POST an `app/api/control.py`. **Reset** (`HALTED →
  NORMAL`) ist eine separate, ebenfalls bestätigte manuelle Aktion (nie automatisch).
- **Zustände:** `NORMAL` neutraler Button „Kill-Switch auslösen" (`--danger-fg` Rand); `HALTED` → Vollbreite-Banner
  `--danger-solid` + `--on-solid`, Button wird „System zurücksetzen".
- **A11y:** Button ≥ 44px Höhe; Dialog fokusfängt; Zustandswechsel via `aria-live="assertive"` angesagt.
- **Anker:** `data-testid="killswitch"`, `data-betriebszustand="normal|halt_angefordert|flatten|halted"`.

### 7.4 Modus-Umschalter echt/simuliert (BR-019, Sicherheits-Kennzeichnung)
- **Anatomie:** Segmentierter Schalter `[ SIMULIERT | echt ]` in der Statusleiste, plus persistenter Modus-Badge.
- **MVP-Sperre (bindend, D5):** „echt"/Live ist **hart gesperrt** — das Segment „echt" ist `disabled`/`inert`
  (html/R05: Bereich klar als inaktiv gekennzeichnet) mit **Schloss-Icon** 🔒 und Tooltip/`aria-label`
  „Live im MVP gesperrt (BR-019)". Default und einzig aktiv: **SIMULIERT**.
- **Kennzeichnung:** Im simulierten Modus trägt das Cockpit einen dezenten, aber **dauerhaften** Modus-Badge
  „SIMULIERT" (`--warn-fg`, diagonal-gestreiftes Musterband als zusätzliches Nicht-Farb-Signal). Würde je „echt"
  aktiv (Post-MVP), ersetzt ein **rotes Vollbreite-LIVE-Banner** (`--danger-solid`) den dezenten Badge — realer
  Geldeinsatz ist nie mit simuliert verwechselbar.
- **A11y:** `role="radiogroup"`, gesperrtes Segment `aria-disabled="true"`; Moduswechsel `aria-live`.
- **Anker:** `data-testid="modus-switch"`, `data-modus="simuliert|echt"`, `data-live-locked="true|false"`.

### 7.5 Betriebs-Metriken (Heartbeat / Drawdown / Halluzinations-KPI, BR-006/BR-022)
- **Heartbeat:** „Puls"-Anzeige mit Zeitstempel des letzten Herzschlags + Alter (`vor Ns`). Zustand OK/verspätet/
  ausgefallen via §2.2-Farbe **+** Text („OK" / „verspätet 45s" / „AUSGEFALLEN"). Ausfall → Warn/Danger-Eskalation.
- **Drawdown:** Prozentwert (`--font-mono`, Vorzeichen `−`), Fortschritts-Balken relativ zur Kill-Switch-Schwelle;
  bei Schwellen-Nähe `--warn`, bei Überschreitung `--danger` + Text „Schwelle überschritten".
- **Halluzinations-KPI (BR-006):** Faktenabweichungs-% gegen die 2%-Grenze; > 2% → `--danger` + Badge „LLM
  DEAKTIVIERT" (der Zustand aus §6-LLM-Kette wird als Wort gezeigt, nicht nur Farbe).
- **Anker:** `data-testid="heartbeat|drawdown|halluzination-kpi"`, jeweils `data-state` + `data-value`.

### 7.6 Datentabelle (dicht, sortierbar)
- **Anatomie:** `<table>` mit `<caption>` (screenreader-Titel), `<thead>` sticky, `<th scope="col">`. Numerik-
  Spalten rechtsbündig + `--font-mono`/`tabular-nums`. Zebra über `--surface-3` (nicht als alleiniger Zeilen-
  Trenner — dünne `--border` bleibt). Dichtes Padding (§4).
- **Sortierung:** clientnah über sortierbare Header-Buttons **oder** HTMX-Request mit Sortier-Query, der dasselbe
  Tabellen-Partial neu rendert. Sortier-Header ist `<button>` im `<th>` mit `aria-sort="ascending|descending|none"`
  + Richtungs-Glyph `▲/▼` (nicht nur Farbe).
- **Zeilen-Status:** semantische Zustände (z. B. Position `IN_WIEDERBEWERTUNG`, `EXIT_ANGESTOSSEN`) als Text-Badge
  in eigener Spalte, nie nur Zeilen-Einfärbung.
- **Empty/No-Data:** eigener leerer Zustand („Keine offenen Positionen im Modus SIMULIERT") statt leerer Tabelle.
- **Responsive:** horizontaler Scroll-Wrapper mit sticky erster Spalte (§6).
- **Anker:** `data-testid="table-<view>"`, sortierbarer Header `data-sort-key`, Zeile `data-row-id`.

### 7.7 Score-/Signal-Badge (C-007 / BR-007)
- **Score 0–10:** `--font-mono`, eine Dezimalstelle, plus horizontaler 0–10-Mini-Meter. Farbe folgt der Signal-
  schwelle, aber **das Signalwort ist führend**.
- **Signal-Badge (BR-007-Schwellen):** `KAUF (≥8)` · `BEOBACHTEN (6–7.9)` · `HALTEN (4–5.9)` · `REDUZIEREN
  (2–3.9)` · `VERKAUF (<2)` — als Text-Pill mit abgestufter Farbe (KAUF `--ok`, BEOBACHTEN `--info`, HALTEN
  neutral `--text-2`, REDUZIEREN `--warn`, VERKAUF `--danger`) **und** Wortlaut. **Sanity-Cap (BR-008):** ist der
  Deckel aktiv, trägt das Badge einen Zusatz-Marker „⛨ gedeckelt (Risiko<3)" — der Nutzer sieht, dass das Signal
  nicht dem rechnerischen Score folgt.
- **Anker:** `data-testid="signal-badge"`, `data-signal="kauf|beobachten|halten|reduzieren|verkauf"`,
  `data-sanity-capped="true|false"`.

### 7.8 Spinnennetz / Radar (5 Analysekategorien, C-007) — siehe §8.1 für die volle Chart-Spec.

### 7.9 Anlageklassen-Toggle (BR-017/BR-018)
- **Anatomie:** Liste der 11 Klassen (Klassen-Chip §2.4 + Prio) mit **Toggle-Switch** je Klasse (an/aus).
- **Zustände:** an (`--accent`) / aus (`--text-3`) — Zustand zusätzlich als Text „aktiv/inaktiv" + Schalter-Stellung
  (nicht nur Farbe). **Sonderzustand BR-018:** ist eine Klasse **aus, hält aber offene Positionen**, zeigt der
  Eintrag ein Warn-Badge „inaktiv – Positionen bleiben überwacht" (`--warn-fg`), damit klar ist: kein neuer Kauf,
  aber Exits laufen. Diese Kennzeichnung ist bindend (verhindert die „blind gewordene Position", C-006).
- **Interaktion:** Toggle = HTMX-POST an `app/api/control.py` → rendert die Zeile/Statusleiste neu.
- **A11y:** natives `<input type="checkbox" role="switch">` mit `<label>`; Schalter ≥ 44px Trefferfläche;
  `aria-describedby` auf das BR-018-Warnband.
- **Anker:** `data-testid="toggle-ac-<N>"`, `data-active="true|false"`, `data-has-open-positions="true|false"`.

### 7.10 Toast / Alert / Banner (Benachrichtigungen, Hybrid-Modus C-016)
- **Drei Ebenen:** (a) **Banner** (Vollbreite, persistent) für Betriebs-Kritisches (Kill-Switch HALTED, Live-Modus,
  LLM deaktiviert); (b) **Inline-Alert** in einer View (`role="alert"` für Fehler, `role="status"` für Info);
  (c) **Toast** (transient, oben rechts, auto-dismiss ~6s, aber pausierend bei Hover/Fokus, WCAG 2.2.1) für
  informative Ereignis-Benachrichtigungen (neuer Kandidat, Fill).
- **Semantik-Farbe + Icon + Text** (D3); Fehler-Toasts sind **nicht** auto-dismiss (müssen quittierbar sein).
- **A11y:** Live-Regionen (`aria-live`), Fokus wird bei kritischem Banner nicht gestohlen, aber angesagt.
- **Anker:** `data-testid="toast|banner|alert"`, `data-severity="info|success|warn|danger"`.

### 7.11 Control-Bestätigungs-Dialog
- Alle schreibenden Control-Aktionen (Kill-Switch, Modus, ggf. destruktive Toggles mit offenen Positionen) laufen
  über ein natives modales `<dialog>` (html/R08 `command`/`commandfor`) mit Klartext-Konsequenz + Abbrechen/
  Bestätigen. Bestätigen löst den HTMX-POST aus. Verhindert versehentliche Betriebseingriffe (D5).

---

## 8. Charts & Datenvisualisierung (dataviz-Vorgaben)

Konsistenter Chart-Stil über alle Views. **Empfehlung zur Chart-Lib-Wahl (§12 architecture, Freigabe designer):**

- **Spinnennetz/Radar wird als server-gerendertes inline-SVG** in Jinja gebaut — **keine JS-Lib nötig**. Begründung:
  das Radar ist eine deterministische Projektion von 5 Score-Werten auf ein Polygon; SVG ist Playwright-testbar
  (DOM-Anker), HTMX-partial-swappbar, offline, ohne Bundle. Das ist der schlankste, robusteste Weg und passt exakt
  zu ADR-012/013.
- **Zeitreihen** (Depot-Verlauf, Drawdown-Historie, Sparklines) über **eine kleine vendored Canvas-Lib**
  (Empfehlung: **uPlot**, MIT, ~50 KB min, kein Build) unter `app/web/static/vendor/`. Alternativ ebenfalls
  server-SVG für einfache Sparklines. Keine schwergewichtige Lib (kein ECharts/D3-Vollbundle).

Gemeinsame Chart-Tokens: Achsen/Gitter `--border`, Achsentext `--text-2` (`--fs-xs`), Primärserie `--accent`,
Flächen halbtransparent (`color-mix(in oklab, <serie> 25%, transparent)`, css/R08). Legende immer vorhanden, mit
Text (nie Farbe allein → D3). Chart-Container hat `--min-height` (kein Layout-Sprung beim Polling-Swap).

### 8.1 Spinnennetz / Radar (C-007) — verbindliche Geometrie

- **5 Achsen**, je eine Analysekategorie, im Uhrzeigersinn ab **oben (−90°)**, Winkelabstand **72°**:
  Achse i (0..4) → `θ_i = −90° + i·72°`. Reihenfolge fix: **Fundamental, Technisch, Qualitativ, Makro,
  Risiko & Quantitativ** (C-007-Reihenfolge, für Wiedererkennbarkeit **immer identisch**).
- **Radiale Skala 0–10**: Score s auf Radius `r = R · s/10` (R = Außenradius). Gitterringe bei **2/4/6/8/10** als
  `--border`-Polygone; Achsenlinien vom Zentrum nach außen; Achsenlabel (Kategorie-Name, `--fs-xs`, `--text-2`)
  außerhalb des 10er-Rings, plus Kategorie-Score als Zahl.
- **Kaufstärke-Fläche** = Polygon der 5 Punkte, Füllung `color-mix(in oklab, var(--accent) 25%, transparent)`,
  Kontur `--accent` 2px. **Optionale zweite Fläche** (historischer Durchschnitt, C-007): halbtransparent in
  `--text-2` (unterscheidbar durch **gestrichelte** Kontur → Nicht-Farb-Signal), unter der Primärfläche.
- **Sanity-Cap-Hinweis (BR-008):** ist der Risiko-Achsen-Score < 3, wird diese Achse zusätzlich mit `--warn`-Marker
  hervorgehoben und der Cap-Zustand im begleitenden Signal-Badge (§7.7) genannt.
- **A11y (Pflicht):** Das SVG ist **nicht** die einzige Quelle — direkt daneben/darunter steht eine **Werttabelle**
  der 5 Kategorie-Scores (Text). Das SVG trägt `role="img"` + `aria-label` „Analyse <Titel>: Fundamental x,
  Technisch y, …". Farben tragen nie allein Bedeutung (die Zahlen stehen an den Achsen). Kein Hover-only-Inhalt.
- **Anker:** `data-testid="spinnennetz"`, Polygon `data-series="aktuell|historie"`, je Achse
  `data-kategorie="fundamental|technisch|qualitativ|makro|risiko"` `data-score`.

### 8.2 Sparklines / Verlauf
- Sparkline im Tile (Höhe ~28px, keine Achsen, nur Trendlinie + optional letzter Punkt). Vollverlauf (Depot/
  Drawdown) mit Achsen, Zeit als X. Positiv/Negativ-Segmente nicht nur farblich (End-Delta trägt §2.3-Kodierung).
- Reduced-Motion: keine animierte Einzeichnung; direkt gezeichnet (css/R03).

### 8.3 Live-Update via HTMX-Polling (§13.2)
- Live-Elemente (Ampel, Live-Kurse, Heartbeat, Drawdown, Halluzinations-KPI) pollen mit `hx-trigger="every Ns"`
  gegen kleine Partial-Endpunkte, die dasselbe Partial neu rendern. **Empfohlene Intervalle:** Statusleiste/Ampel
  ~5–10s, Live-Kurse/Depot ~10–15s, langsame KPIs ~30–60s. Kein WebSocket (kein Sub-Sekunden-Bedarf, NFR §10).
- **Swap-UX:** Beim Partial-Swap kein Layout-Sprung (feste Höhen/`min-height`), kein Fokusverlust (Fokus in einem
  gepollten Container bleibt erhalten oder Polling pausiert bei Fokus/offenem Menü). Aktualisierte Werte optional
  kurz mit `--motion-fast`-Highlight (reduced-motion aus). Ladeindikator dezent über `.htmx-indicator`.
- **Fehler-/Stale-Zustand:** schlägt ein Poll fehl, zeigt das Element „veraltet (seit …)" statt einen falschen
  Frischwert vorzutäuschen (`--warn`, D3-Text). `aria-live="polite"` für sich ändernde Statuswerte.

---

## 9. Accessibility (WCAG 2.2 AA — bindend, reviewer-prüfbar)

- **Kontrast:** Body ≥ 4.5:1, Large-Text/UI-Grafik/Fokusring ≥ 3:1 — **berechnet**, nicht geschätzt (css-Checklist:
  Verstoß = Critical). Alle Tokens in §2 sind so gewählt (Werte dort). Neue Farbpaare berechnet der `coder`/prüft
  der `reviewer`.
- **Status nie nur über Farbe** (1.4.1): jede semantische Farbe trägt Text + Icon/Form/Vorzeichen (D3). Gilt für
  Ampel, G/V, Signal-Badges, Toggles, Zeilen-Status, Chart-Serien.
- **Fokus:** sichtbarer Fokus-Ring auf **jedem** interaktiven Element (`--focus-ring`, 2px + 2px offset); nie
  `outline:none` ohne Ersatz. **2.4.11 Focus Not Obscured:** sticky Statusleiste/Header dürfen fokussierte Elemente
  nicht verdecken (`scroll-margin-top` einplanen).
- **Tastatur:** alle Aktionen ohne Maus bedienbar (Toggles, Sortierung, Kill-Switch, Modus, Dialoge, Off-Canvas-Nav).
  Native Elemente bevorzugt (`<button>`, `<input type=checkbox role=switch>`, `<dialog>`, `<details>`) — bringen
  Tastatur/Fokus/A11y gratis (html/R04/R07/R08). Logische Tab-Reihenfolge; Skip-Link zu `<main>`.
- **Touch-/Klick-Targets:** primäre Controls (Kill-Switch, Modus-Switch, Klassen-Toggles, Nav-Einträge, Buttons)
  **≥ 44×44px**. Dichte Tabellen-Zeilenaktionen dürfen **≥ 24×24px** (WCAG 2.2 SC 2.5.8 Minimum) sein, **wenn**
  ausreichend Abstand besteht (Spacing-Exception) — sonst ebenfalls 44px. Cockpit-Default: 44px, Tabellen-inline 24px+Abstand.
- **Bewegung:** `prefers-reduced-motion: reduce` schaltet nicht-essenzielle Animation/Transition/Chart-Animation/
  View-Transitions ab (css/R03; §4/§8.2).
- **Live-Regionen:** HTMX-aktualisierte Statuswerte in `aria-live="polite"`, kritische Betriebszustandswechsel
  (Kill-Switch, Live) in `aria-live="assertive"`/`role="alert"`.
- **Formulare/Controls:** jedes Control ein `<label>`; Zustände (`aria-pressed`/`aria-checked`/`aria-sort`/
  `aria-current`/`aria-disabled`) korrekt gesetzt. Fehlermeldungen textlich, nicht nur farblich.
- **Semantik/Landmarks:** eine `<header>`, `<nav>`, `<main>` je Seite; ein `<h1>` je View, korrekte Heading-Hierarchie
  (html/R01). Tabellen mit `<caption>`/`scope`.
- **Consistent Help/Nav (2.4.5/3.2.3/3.2.6):** Nav und Statusleiste an gleicher Stelle über alle Views.
- **Zoom/Reflow (1.4.10):** bis 200% Zoom nutzbar, kein horizontaler Body-Scroll außer bei bewusst scrollbaren
  Tabellen-Wrappern; `rem`-basierte Größen (§3).

---

## 10. View-Blaupausen (für `requirement` — Story-Ableitung)

Mapping der fünf Kern-Views (`architecture.md` §13.3) auf Komponenten. Jede View: HTML-Route (`app/api/ui.py`) +
JSON-Route + geteilte Query (§13.2). `requirement` schneidet je View/Komponente Stories; jede Komponente oben ist
benannt und wiederverwendbar.

- **Depot / Portfolio** (`GET /api/depot`, generalisiert `GET /dashboard/depot`): KPI-Tiles (Portfolio-Wert,
  Cash-Quote, realisierter/unrealisierter G/V §2.3) · Depot-Datentabelle (§7.6: Titel+Klassen-Chip §2.4, Menge,
  Einstand, Live-Kurs, unrealisierter G/V, Gewichtung; „nicht bewertbar"=`—`) · Depot-Verlauf-Chart (§8.2) ·
  Modus-abhängig (echt/simuliert isoliert, BR-130). Empty-State je Modus.
- **Kandidaten & Analyse-Scores** (`GET /api/kandidaten` + Detail): Kandidaten-Tabelle (§7.6: Titel, Klassen-Chip,
  Gesamtscore §7.7, Signal-Badge §7.7, `as_of`) · Detail-Panel mit **Spinnennetz §8.1** + Kategorie-Score-Tabelle +
  Kategorie-Fakten inkl. Quellen-ID/Timestamp (BR-002) + Sanity-Cap-Hinweis (BR-008). Desktop: Liste links,
  Spinnennetz rechts (`--bp-xl`).
- **Order-/Trade-Historie** (`GET /api/trades`): dichte Datentabelle (§7.6: Titel, Richtung Kauf/Verkauf als Badge,
  Menge, Fill-Preis, Arrival-Price, **Slippage/TCA** mit Vorzeichen-Kodierung §2.3, Kosten, FX-Split, Zeit) ·
  Filter (Modus/Titel/Zeitraum) als HTMX-Form → Tabellen-Partial-Swap. Slippage negativ hervorgehoben (Text+Farbe).
- **System-Status** (`GET /api/system/status`): die Statusleisten-Komponenten als Voll-View — Ampel §7.2,
  Kill-Switch §7.3, Modus §7.4, Heartbeat/Drawdown/Halluzinations-KPI §7.5, Gate-Ampel (BR-025). Control-Aktionen
  über Bestätigungs-Dialoge §7.11. Kritische Zustände als Banner §7.10.
- **Konfiguration / Toggles** (`GET /api/config/anlageklassen` · `…/depotstrategie`): 11 Anlageklassen-Toggles §7.9
  (inkl. BR-018-Warnband) · Depotstrategie-Grenzwerte/Preset (read + ggf. Control). Schreibaktionen ausschließlich
  über `app/api/control.py` (§13.7).

---

## 11. Umsetzungshinweise für den `coder` (Token-/Datei-Konvention)

- **Ort:** ein `tokens.css` (Custom Properties: Farben/Spacing/Radius/Typo/Motion) + komponentenweise CSS unter
  `app/web/static/css/`; vendored `htmx.min.js` + `uplot`(o. ä.) unter `app/web/static/vendor/`. **Kein CDN**
  (ADR-013, grep-prüfbar). Templates unter `app/web/templates/` (base-Layout + je View + Partials).
- **Theme:** `:root { color-scheme: light dark; }` + alle Farb-Tokens via `light-dark(<light>,<dark>)` (css/R05).
  Optionaler manueller Theme-Toggle setzt `color-scheme` explizit (light/dark) auf `<html>` und persistiert die
  Wahl; ohne Toggle folgt es dem System.
- **Keine Inline-Styles** (html/R02); keine Werte außerhalb der Skalen (§4). Native Elemente vor JS-Nachbauten
  (html/R04/R07/R08). CSS Nesting nativ erlaubt (css/R07; `&` bei Pseudo-Klassen zwingend).
- **Test-Anker:** die `data-testid`/`data-*` aus §7/§8 sind bindend (Playwright-Regression §13.5).
- **Charts:** Spinnennetz als server-SVG (§8.1-Geometrie); Zeitreihen via vendored Canvas-Lib oder server-SVG.
- **Demo-Seed (ADR-014):** Design gilt gegen den Seed-Zustand; jede Komponente hat einen definierten Empty-State
  (kein blindes Leerrendern).

---

## 12. Annahmen & offene Punkte (dokumentiert, Owner-Delegation)

- **Chart-Lib:** Spinnennetz server-SVG (keine Lib); Zeitreihen-Empfehlung **uPlot** (MIT, klein) — finale Freigabe
  der konkreten Lib-Datei mit dem Owner/Spec (§12 architecture). Falls Zeitreihen simpel bleiben: auch server-SVG.
- **Font:** System-Stacks (kein Vendoring nötig). Wird ein UI-Font gewünscht (z. B. Inter), als WOFF2 vendored
  (kein CDN) — bis dahin `system-ui`.
- **Auth/Zugang:** Design behandelt keine Login-Optik (MVP local-only, §13.7 architecture offen). Kommt ein
  Auth-Layer, gilt WCAG 3.3.8 Accessible Authentication (kein reiner Cognitive-Test) — dann hier ergänzen.
- **Light-Theme Klassen-Hues:** in §2.4 als abgedunkelte Varianten skizziert; exakte Light-Werte kalibriert der
  `coder` gegen AA-Label-Kontrast (Label-Text bleibt `--text-1`, daher unkritisch).
- **Genaue Polling-Intervalle** (§8.3) sind Startwerte; final abhängig von Last/Datenfrequenz (C-009).
