# Vendored Assets (ADR-013 — kein CDN)

| Datei | Version | Quelle | SHA-256 |
|---|---|---|---|
| `htmx.min.js` | 2.0.10 | https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js (MIT) | `71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de` |
| `lightweight-charts.standalone.production.js` | 5.2.0 | npm `lightweight-charts@5.2.0` (`dist/lightweight-charts.standalone.production.js`), Apache-2.0 | `c0992580867c4912cc9385b3c2728315bcc1a76c7f1087dca908430fccdf31d7` |

Kein CDN-Verweis zur Laufzeit (`docs/specs/frontend-cockpit.md` AC12) — die
Dateien liegen statisch im Runtime-Image (`app/web/static/vendor/`, siehe
`Dockerfile` `COPY --from=build /app/app /app/app`). Aktualisierung: neue
Version manuell herunterladen, SHA-256 gegenprüfen, Tabelle nachziehen.

**`lightweight-charts.standalone.production.js` (Owner-Freigabe 2026-07-19,
Story S-081, `docs/specs/frontend-cockpit.md` AC33):** Zeitreihen-Chart-Lib
für den Depot-Verlauf-Chart — ersetzt die zuvor offene Owner-/designer-
Entscheidung (server-SVG-Default vs. uPlot-Empfehlung, `design.md` §8.2,
jetzt überholt für AC33, siehe Spec-Precisierung). **Lizenz-Pflicht
(Apache 2.0):** die Standalone-Datei bringt das TradingView-Attribution-Logo
im Chart standardmässig mit — es wird **nicht** deaktiviert
(`app/web/static/js/depot-verlauf.js` setzt keine `attributionLogo`-Option).
Bezogen via `npm install --no-save lightweight-charts@5.2.0` (kein
Projekt-Build — die Standalone-Datei wird einmalig kopiert, `node_modules/`
bleibt gitignored, keine Laufzeit-npm-Abhängigkeit).
