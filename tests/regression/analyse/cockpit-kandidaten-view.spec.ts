import { test, expect } from '@playwright/test';

/**
 * Covers (frontend-cockpit): AC23
 * @file Kandidaten-View — Playwright-Regression gegen den Demo-Seed-Zustand
 * (Story S-077).
 *
 * Verankert an den stabilen `data-testid`-Anchors aus `design.md` §7.6
 * (Datentabelle), §7.7 (Score-/Signal-Badge inkl. Sanity-Cap-Marker) und
 * §7.8/§8.1 (Spinnennetz-SVG + begleitende Werttabelle, A11y-Pflicht).
 * Demo-Seed (`app.demo.kandidaten`, AC22): drei Kandidaten (NESN, NOVN,
 * ROG) mit je 5 Kategorie-Scores, genau einer mit aktivem Sanity-Cap
 * (ROG, → BR-008).
 */

test.describe('Cockpit — Kandidaten-View (AC15, Demo-Seed)', () => {
  test('zeigt die drei Demo-Kandidaten mit Signal-Badge + Score-Meter', async ({ page }) => {
    await page.goto('/ui/kandidaten');

    const table = page.getByTestId('table-kandidaten');
    await expect(table).toBeVisible();
    await expect(table.locator('tbody tr')).toHaveCount(3);

    await expect(table.getByTestId('signal-badge')).toHaveCount(3);
    await expect(table.getByTestId('score-meter')).toHaveCount(3);

    // AC22 "mind. 1 Sanity-Cap-Fall" — hier genau der Demo-Kandidat ROG.
    await expect(
      table.locator('[data-testid="signal-badge"][data-sanity-capped="true"]')
    ).toHaveCount(1);
  });

  test('Klick auf einen Kandidaten öffnet das Detail-Panel mit Spinnennetz + Werttabelle', async ({
    page,
  }) => {
    await page.goto('/ui/kandidaten');

    await expect(page.getByTestId('kandidat-detail-leer')).toBeVisible();

    const rogRow = page.getByTestId('kandidat-row').filter({ hasText: 'ROG' });
    await rogRow.getByTestId('kandidat-open').click();

    const detail = page.getByTestId('kandidat-detail');
    await expect(detail.getByTestId('spinnennetz')).toBeVisible();
    await expect(detail.getByTestId('kategorie-werttabelle')).toBeVisible();
    await expect(detail.getByTestId('kategorie-fakten')).toBeVisible();

    // ROG ist der Demo-Sanity-Cap-Fall (→ BR-008).
    await expect(detail.getByTestId('sanity-cap-hinweis')).toHaveAttribute(
      'data-sanity-capped',
      'true'
    );
  });
});
