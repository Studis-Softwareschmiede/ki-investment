import { test, expect } from '@playwright/test';

/**
 * Covers (frontend-cockpit): AC23
 * @file Depot-View — Playwright-Regression gegen den Demo-Seed-Zustand
 * (Story S-077).
 *
 * Verankert an den stabilen `data-testid`-Anchors aus `design.md` §7
 * (Statusleiste §7.2-§7.5, Nav, KPI-Tile §7.1, Datentabelle §7.6,
 * Klassen-Chip §2.4). Demo-Seed (`app.demo.depot`, AC22): drei offene
 * Paper-Positionen im Modus SIMULIERT (NESN, NOVN, CHSPI — NESN nach
 * einem Teilverkauf weiterhin offen). Die Depot-View zeigt Positionen nur
 * im per `?mode=`-Query-Parameter gewählten Modus (Default „echt“,
 * `app/api/ui.py::depot_view`) — alle Tests hier navigieren deshalb
 * explizit mit `?mode=simuliert`.
 */

test.describe('Cockpit — Depot-View (AC14/AC19, Demo-Seed)', () => {
  test('lädt die Shell (Statusleiste + Nav) und zeigt die KPI-Tiles', async ({ page }) => {
    await page.goto('/ui/depot?mode=simuliert');

    await expect(page.getByTestId('statusleiste')).toBeVisible();
    await expect(page.getByTestId('nav-main')).toBeVisible();
    await expect(page.getByTestId('nav-link-depot')).toHaveAttribute('aria-current', 'page');

    await expect(page.getByTestId('tile-portfolio-wert')).toBeVisible();
    await expect(page.getByTestId('tile-cash-quote')).toBeVisible();
    await expect(page.getByTestId('tile-realisierter-gv')).toBeVisible();
    await expect(page.getByTestId('tile-unrealisierter-gv')).toBeVisible();
  });

  test('zeigt die drei Demo-Positionen (NESN, NOVN, CHSPI) in der Datentabelle', async ({ page }) => {
    await page.goto('/ui/depot?mode=simuliert');

    const table = page.getByTestId('table-depot');
    await expect(table).toBeVisible();

    const rows = table.locator('tbody tr');
    await expect(rows).toHaveCount(3);

    await expect(table).toContainText('NESN');
    await expect(table).toContainText('NOVN');
    await expect(table).toContainText('CHSPI');

    // §2.4 Klassen-Chip: jede Zeile trägt einen Anlageklassen-Chip.
    await expect(table.getByTestId('klassen-chip')).toHaveCount(3);
  });

  test('Modus ECHT (keine Demo-Daten) zeigt den definierten Empty-State (E2)', async ({ page }) => {
    await page.goto('/ui/depot?mode=echt');

    await expect(page.getByTestId('depot-empty')).toBeVisible();
    await expect(page.getByTestId('table-depot')).toHaveCount(0);
  });
});
