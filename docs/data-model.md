# Datenmodell — ki-investment

> Teil des Detailkonzepts (**DB-Domäne**, nur bei `profile.domains` enthält `sql`). Geschrieben vom `dba`. Der `coder` setzt es 1:1 in Migrationen um (via `sql`-Pack) — hier KEIN SQL, nur das Modell.

## Entitäten
<Entität · Felder (Typ, NOT NULL / UNIQUE / CHECK) · Primärschlüssel.>

## Validierungs-Geschäftsregeln (BR-NNN)
<Datenbezogene Geschäftsregeln (Formate, Wertebereiche, Pflichtfelder) — gleicher `BR-NNN`-Namensraum wie `architecture.md` (fortlaufend über beide Dateien). Jede Regel nennt explizit die **durchsetzende Schicht** (Enforcement) — das verhindert doppelte/fehlende Validierung und macht den Audit-Pfad sichtbar. Specs referenzieren via `(→ BR-NNN)`, Tests taggen via `#BR-NNN`.>

| BR-ID | Feld / Entität | Regel | Enforced by (Layer) |
|---|---|---|---|
| BR-NNN | <Entität.Feld> | <z.B. „genau 10 Ziffern"> | <z.B. DB-CHECK + App-Validierung> |
| BR-NNN | <…> | <…> | <DB-Constraint \| App/Form \| beide> |

## Beziehungen
<Fremdschlüssel, Kardinalitäten.>

## Indizes
<Auf jede Filter-/FK-Spalte.>

## RLS / Zugriffskonzept
<Bei Mandantenfähigkeit: Tenant-Filter (`auth.uid()`), SECURITY-DEFINER-Grenzen, `search_path`.>

## Migrations-Reihenfolge
<Reihenfolge + harte Abhängigkeiten.>
