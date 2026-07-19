/* Depot-Verlauf-Chart (Story S-081, `docs/specs/frontend-cockpit.md`
 * AC33; design.md §8.2 "Chart-Container hat --min-height (kein
 * Layout-Sprung)").
 *
 * Chart-Technik: TradingView Lightweight Charts (Owner-Entscheidung
 * 2026-07-19, vendored unter `static/vendor/`, siehe `static/vendor
 * /README.md` für Lizenz-/Attribution-Pflicht — die eingebaute
 * TradingView-Attribution wird NICHT deaktiviert, keine `attributionLogo`-
 * Option gesetzt). Kein CDN, keine Build-Pipeline (ADR-012/013).
 *
 * Bewusst AUSSERHALB des `depot-live`-12s-Poll-Bereichs (`views/depot.
 * html`): dieses Skript lädt die Verlaufsdaten einmalig beim Seitenaufruf
 * per `fetch()` gegen denselben `GET /api/depot/verlauf`-Endpunkt, den
 * auch die JSON-Route/HTML-Route-Query-Funktion konsumiert (AC1) — kein
 * wiederholtes Chart-Neuzeichnen je Poll-Zyklus.
 *
 * Reduced-Motion (css/R03, §8.2 "keine animierte Einzeichnung"):
 * Lightweight Charts zeichnet per `setData()` sofort/ohne
 * Einzeichen-Animation — es gibt hier nichts abzuschalten, das Kriterium
 * ist ohne Zusatzcode erfüllt.
 *
 * Der Container wird nur gerendert, wenn der Server (`app.api.ui
 * .depot_view`) mindestens 2 Snapshots liefert (Empty-State sonst
 * server-seitig, `views/depot.html`) — dieses Skript findet in diesem
 * Fall also immer mindestens 2 Punkte vor. Schlägt der `fetch()` selbst
 * fehl (Netzwerkfehler), bleibt der Container leer (kein Fake-Wert) und
 * der Fehler wird nur geloggt — kein eigener Fehlertext, da dieser
 * Chart-Container kein AC19-Live-Poll-Bereich mit E1-Stale-Vertrag ist. */

(function () {
  "use strict";

  function toChartZeitpunkt(iso) {
    // "2026-07-19T08:00:00+00:00" -> "2026-07-19" (Business-Day-Format,
    // Lightweight Charts Area-Series `time`) — ein Snapshot pro
    // Kalendertag/Modus (→ BR-142), Zeitanteil ist hier irrelevant.
    return iso.slice(0, 10);
  }

  function tokenFarbe(name, fallback) {
    var wert = getComputedStyle(document.documentElement).getPropertyValue(name);
    return wert ? wert.trim() : fallback;
  }

  function initDepotVerlaufChart(container) {
    var url = container.dataset.verlaufUrl + "?mode=" + encodeURIComponent(container.dataset.mode);

    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("depot-verlauf-fetch-fehlgeschlagen");
        }
        return resp.json();
      })
      .then(function (daten) {
        var punkte = (daten.eintraege || []).map(function (eintrag) {
          return { time: toChartZeitpunkt(eintrag.zeitpunkt), value: Number(eintrag.portfolio_wert) };
        });
        if (punkte.length < 2) {
          return;
        }

        var accent = tokenFarbe("--accent", "#0969DA");
        var textFarbe = tokenFarbe("--text-1", "#1F2328");
        var achsenFarbe = tokenFarbe("--text-2", "#656D76");
        var gitterFarbe = tokenFarbe("--border", "#D0D7DE");

        var chart = LightweightCharts.createChart(container, {
          layout: { textColor: textFarbe, background: { type: "solid", color: "transparent" } },
          grid: {
            vertLines: { color: gitterFarbe },
            horzLines: { color: gitterFarbe },
          },
          rightPriceScale: { borderColor: gitterFarbe },
          timeScale: { borderColor: gitterFarbe },
          autoSize: true,
        });

        var serie = chart.addSeries(LightweightCharts.AreaSeries, {
          lineColor: accent,
          topColor: "color-mix(in oklab, " + accent + " 25%, transparent)",
          bottomColor: "color-mix(in oklab, " + accent + " 2%, transparent)",
          priceLineVisible: false,
        });
        serie.setData(punkte);
        chart.timeScale().fitContent();
        // `autoSize: true` (oben) übernimmt Grössenänderungen selbst
        // (ResizeObserver, Lightweight Charts v5) — kein eigener
        // resize-Listener nötig.
      })
      .catch(function (fehler) {
        // eslint-disable-next-line no-console
        console.error("Depot-Verlauf-Chart konnte nicht geladen werden.", fehler);
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var container = document.getElementById("depot-verlauf-chart");
    if (container && window.LightweightCharts) {
      initDepotVerlaufChart(container);
    }
  });
})();
