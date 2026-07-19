import { test, expect } from '@playwright/test';

/**
 * Covers (frontend-cockpit): AC23
 * @file Konfigurations-View — Playwright-Regression gegen den
 * Demo-Seed-Zustand (Story S-077).
 *
 * Verankert an den stabilen `data-testid`-Anchors aus `design.md` §7.9
 * (Anlageklassen-Toggle). Die 11 Anlageklassen sind statisches
 * Basis-Seed-Datum (Migration `b2bd709be080`, nicht Teil des Demo-Seeds)
 * — deshalb unabhängig von `SEED_DEMO` immer vorhanden. Kein
 * Depotstrategie-Preset ist aktiviert (kein Seed-Pfad dafür) → definierter
 * Empty-State.
 */

test.describe('Cockpit — Konfigurations-View (AC18)', () => {
  test('zeigt alle 11 Anlageklassen-Toggles mit Text + Schalterstellung', async ({ page }) => {
    await page.goto('/ui/konfiguration');

    const liste = page.getByTestId('anlageklassen-liste');
    await expect(liste).toBeVisible();
    await expect(liste.locator('[data-testid^="toggle-zeile-"]')).toHaveCount(11);

    for (const klasseId of Array.from({ length: 11 }, (_, i) => i + 1)) {
      const toggle = page.getByTestId(`toggle-ac-${klasseId}`);
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute('data-active', /true|false/);
    }

    // D3: Zustand steht zusätzlich als Text, nicht nur als Schalterstellung.
    await expect(liste.getByTestId('toggle-status').first()).toBeVisible();
  });

  test('Depotstrategie ohne aktives Preset zeigt den definierten Empty-State', async ({
    page,
  }) => {
    await page.goto('/ui/konfiguration');

    await expect(page.getByTestId('depotstrategie-empty')).toBeVisible();
    await expect(page.getByTestId('depotstrategie')).toHaveCount(0);
  });
});
