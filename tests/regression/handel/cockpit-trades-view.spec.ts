import { test, expect } from '@playwright/test';

/**
 * Covers (frontend-cockpit): AC23
 * @file Trade-Historie-View — Playwright-Regression gegen den
 * Demo-Seed-Zustand (Story S-077).
 *
 * Verankert an den stabilen `data-testid`-Anchors aus `design.md` §7.6
 * (dichte Datentabelle, Richtungs-Badge, Slippage/TCA) und dem
 * HTMX-Filter-Formular (AC16). Demo-Seed (`app.demo.depot`, AC22): vier
 * Fills im Modus SIMULIERT (drei Käufe + ein Teilverkauf). Wie bei der
 * Depot-View ist der Default-Modus der View „echt“ (`app/api/ui.py
 * ::trades_view`) — alle Tests navigieren deshalb explizit mit
 * `?mode=simuliert`.
 *
 * BEKANNTER BEFUND (S-077-Selbsttest, ausserhalb dieser Story-Reichweite —
 * `app/api/ui.py`/`views/trades.html` gehören zu S-073/AC16, nicht zum
 * Hot-Spot dieser Story): das Filter-Formular sendet `von`/`bis` beim
 * Absenden IMMER als leere Query-Strings mit (native GET-Formular-
 * Serialisierung aller benannten Felder), aber `GET /ui/trades/tabelle`
 * (`von`/`bis`: `datetime | None`) lehnt einen leeren String mit HTTP 422
 * ab, statt ihn wie einen fehlenden Parameter (`None`) zu behandeln — jede
 * Filter-Absendung ohne ausgefüllte Datumsfelder (der naheliegendste
 * Bedienweg: nur Modus/Titel ändern) bricht dadurch. Reproduziert per
 * `curl "/ui/trades/tabelle?mode=echt&titel=&von=&bis="` → 422
 * `datetime_from_date_parsing`. Zweiter Test unten umgeht den defekten
 * Swap deshalb bewusst über direkte URL-Navigation (funktionierender Pfad,
 * von echten Nutzenden z. B. per Lesezeichen ebenfalls begehbar) statt
 * über das Formular — App-Code bleibt unangetastet (Hot-Spot-Disziplin);
 * der Fix gehört in ein eigenes Folge-Item gegen AC16.
 */

test.describe('Cockpit — Trade-Historie-View (AC16, Demo-Seed)', () => {
  test('zeigt die vier Demo-Trades (3 Käufe, 1 Verkauf) mit Richtungs-Badge', async ({ page }) => {
    await page.goto('/ui/trades?mode=simuliert');

    await expect(page.getByTestId('trades-filter-form')).toBeVisible();

    const table = page.getByTestId('table-trades');
    await expect(table).toBeVisible();
    await expect(table.locator('tbody tr')).toHaveCount(4);

    await expect(table.getByTestId('richtung-badge')).toHaveCount(4);
    await expect(
      table.locator('[data-testid="richtung-badge"][data-richtung="kauf"]')
    ).toHaveCount(3);
    await expect(
      table.locator('[data-testid="richtung-badge"][data-richtung="verkauf"]')
    ).toHaveCount(1);

    await expect(table.getByTestId('slippage')).toHaveCount(4);
  });

  test('Filter-Formular-Anker sind vorhanden und spiegeln den geladenen Modus', async ({
    page,
  }) => {
    await page.goto('/ui/trades?mode=simuliert');

    await expect(page.getByTestId('trades-filter-form')).toBeVisible();
    await expect(page.getByTestId('filter-mode')).toHaveValue('simuliert');
    await expect(page.getByTestId('filter-titel')).toBeVisible();
    await expect(page.getByTestId('filter-von')).toBeVisible();
    await expect(page.getByTestId('filter-bis')).toBeVisible();
    await expect(page.getByTestId('filter-submit')).toBeVisible();
  });

  test('Modus ECHT (keine Demo-Daten) zeigt den definierten Empty-State', async ({ page }) => {
    // Direkte Navigation statt Formular-Absendung — siehe "BEKANNTER
    // BEFUND" im Datei-Header (Formular-Swap mit leeren Datumsfeldern ist
    // aktuell defekt, ausserhalb des Hot-Spots dieser Story).
    await page.goto('/ui/trades?mode=echt');

    await expect(page.getByTestId('trades-empty')).toBeVisible();
    await expect(page.getByTestId('table-trades')).toHaveCount(0);
  });
});
