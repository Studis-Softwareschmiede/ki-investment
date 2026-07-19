/* System-Status-Voll-View (Story S-075, `docs/specs/frontend-cockpit.md`
 * AC17). Eigenständiges, nicht-vendored First-Party-Skript (ADR-013 gilt
 * nur für Third-Party-Assets) — deklariert die kleine htmx-`json-enc`-
 * Erweiterung, die die Kill-Switch-Bestätigungs-Dialoge brauchen: der
 * `POST /api/control/kill-switch/ausloesen`-Endpunkt (S-074) erwartet
 * einen JSON-Body (`KillSwitchAusloesungsAnfrage`), htmx sendet Formulare
 * aber standardmässig `application/x-www-form-urlencoded` — diese
 * Erweiterung serialisiert die gesammelten Formularwerte stattdessen als
 * JSON (öffentliche htmx-Erweiterungs-API `htmx.defineExtension`, siehe
 * https://htmx.org/extensions/ "Writing Extensions").
 *
 * Muss NACH `vendor/htmx.min.js` geladen werden (Ausführungsreihenfolge im
 * DOM, `base.html` `{% block scripts %}` liegt bewusst hinter dem
 * htmx-Script-Tag) — kein Laufzeit-CDN (ADR-013), keine weitere
 * Drittanbieter-Bibliothek. */

htmx.defineExtension("json-enc", {
  onEvent: function (name, evt) {
    if (name === "htmx:configRequest") {
      evt.detail.headers["Content-Type"] = "application/json";
    }
  },
  encodeParameters: function (xhr, parameters) {
    xhr.overrideMimeType("text/json");
    return JSON.stringify(parameters);
  },
});
