/* Konfigurations-View (Story S-076, `docs/specs/frontend-cockpit.md`
 * AC18; design.md §7.9 Anlageklassen-Toggle "Interaktion").
 *
 * `POST /api/control/anlageklassen/{id}/toggle` (Story S-074, AC20) nimmt
 * `AnlageklassenToggleAnfrage` als JSON-Body entgegen
 * (`Content-Type: application/json`) — htmx (core, ohne die separate
 * `json-enc`-Erweiterung, die hier bewusst NICHT als weitere Third-Party-
 * Datei vendored wird, ADR-013) sendet Requests standardmässig als
 * `application/x-www-form-urlencoded`. Ein schlanker first-party
 * `fetch()`-Aufruf reicht deshalb aus statt einer zusätzlichen vendorten
 * Erweiterung: der Request trägt denselben `HX-Request: true`-Header, den
 * htmx selbst setzen würde (`app.api.control._ist_htmx_aufruf`), sodass
 * der Server bei Erfolg dieselbe Statusleisten-Partial-HTML liefert
 * (§13.7-5, `app.api.control._statusleiste_partial`) — Fehlerfälle
 * bleiben laut `app.api.control`-Vertrag immer JSON (hier ignoriert, nur
 * der Status-Code zählt).
 *
 * Kein CDN, keine externe Library (ADR-013/AC12) — reines, first-party
 * Vanilla-JS, view-scoped (Hot-Spot-Konvention: eigene Datei statt eines
 * geteilten Skripts). */

function konfigurationToggleAnlageklasse(input) {
  var zeile = input.closest("[data-testid^='toggle-zeile-']");
  var statusEl = zeile ? zeile.querySelector("[data-testid='toggle-status']") : null;
  var fehlerEl = zeile ? zeile.querySelector("[data-testid^='toggle-fehler-']") : null;
  var warnband = zeile ? zeile.querySelector("[data-testid^='warnband-ac-']") : null;
  var statusleiste = document.querySelector(".statusleiste");
  var neuAktiv = input.checked;

  fetch(input.dataset.toggleUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "HX-Request": "true" },
    body: JSON.stringify({ aktiv: neuAktiv }),
  })
    .then(function (resp) {
      if (!resp.ok) {
        throw new Error("konfiguration-toggle-fehlgeschlagen");
      }
      return resp.text();
    })
    .then(function (html) {
      input.setAttribute("data-active", neuAktiv ? "true" : "false");
      if (statusEl) {
        statusEl.textContent = neuAktiv ? "aktiv" : "inaktiv";
      }
      if (warnband) {
        warnband.hidden = neuAktiv;
      }
      if (fehlerEl) {
        fehlerEl.hidden = true;
      }
      if (statusleiste && html) {
        statusleiste.innerHTML = html;
      }
    })
    .catch(function () {
      input.checked = !neuAktiv;
      if (fehlerEl) {
        fehlerEl.hidden = false;
        fehlerEl.textContent = "Fehler beim Umschalten – bitte erneut versuchen.";
      }
    });
}
