# Vendored Assets (ADR-013 — kein CDN)

| Datei | Version | Quelle | SHA-256 |
|---|---|---|---|
| `htmx.min.js` | 2.0.10 | https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js (MIT) | `71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de` |

Kein CDN-Verweis zur Laufzeit (`docs/specs/frontend-cockpit.md` AC12) — die
Datei liegt statisch im Runtime-Image (`app/web/static/vendor/`, siehe
`Dockerfile` `COPY --from=build /app/app /app/app`). Aktualisierung: neue
Version manuell herunterladen, SHA-256 gegenprüfen, Tabelle nachziehen.

Chart-Lib (Zeitreihen, design.md §8/§12) ist **bewusst noch nicht**
vendored — die konkrete Lib-Datei-Freigabe ist laut
`docs/specs/frontend-cockpit.md` Nicht-Ziele ("Keine konkrete
Chart-Lib-Datei-Freigabe") noch offen (Owner/`designer`); sie kommt mit der
ersten View-Story, die einen Zeitreihen-Chart tatsächlich rendert.
