import { test, expect } from '@playwright/test';

/**
 * Covers (frontend-cockpit): AC23
 * @file System-Status-View — Playwright-Regression gegen den
 * Demo-Seed-Zustand (Story S-077).
 *
 * Verankert an den stabilen `data-testid`-Anchors aus `design.md` §7.2
 * (Ampel), §7.3 (Kill-Switch), §7.4 (Modus), §7.5 (Heartbeat/Drawdown/
 * Halluzinations-KPI) und §7.11 (Control-Bestätigungs-Dialoge). Demo-Seed
 * (`app.demo.lernschleife`, AC22): eine Gate-Ampel „gruen“ (Stufe A + B
 * bestanden). Frisch migrierte/geseedete DB, kein Kill-Switch ausgelöst
 * → Betriebszustand „normal“, Modus global „simuliert“ (Defaults,
 * `app.core.kill_switch`/`app.core.modus_override`); kein Demo-Heartbeat
 * registriert → definierter Leer-Zustand.
 */

test.describe('Cockpit — System-Status-View (AC17, Demo-Seed)', () => {
  test('zeigt die Gate-Ampel „gruen“ aus dem Demo-Seed', async ({ page }) => {
    await page.goto('/ui/system-status');

    await expect(page.getByTestId('statusleiste')).toBeVisible();

    const gateAmpel = page.getByTestId('gate-ampel');
    await expect(gateAmpel).toBeVisible();
    await expect(gateAmpel).toHaveAttribute('data-ampel-state', 'gruen');
    await expect(page.getByTestId('gate-ampel-zeitstempel')).toBeVisible();
  });

  test('zeigt Kill-Switch NORMAL, Modus SIMULIERT und den Heartbeat-Leerzustand', async ({
    page,
  }) => {
    await page.goto('/ui/system-status');

    await expect(page.getByTestId('status-killswitch')).toHaveAttribute(
      'data-betriebszustand',
      'normal'
    );
    await expect(page.getByTestId('killswitch-ausloesen-oeffnen')).toBeVisible();

    await expect(page.getByTestId('status-modus')).toHaveAttribute('data-modus', 'simuliert');

    await expect(page.getByTestId('status-drawdown')).toBeVisible();
    await expect(page.getByTestId('status-halluzination-kpi')).toBeVisible();

    await expect(page.getByTestId('heartbeat-leer')).toBeVisible();
  });

  test('Kill-Switch-Bestätigungsdialog (§7.11) ist im DOM verankert und modal', async ({
    page,
  }) => {
    await page.goto('/ui/system-status');

    const dialog = page.getByTestId('dialog-kill-switch-ausloesen');
    await expect(dialog).toBeAttached();
    await expect(dialog).toBeHidden();

    await page.getByTestId('killswitch-ausloesen-oeffnen').click();
    await expect(dialog).toBeVisible();
    await expect(page.getByTestId('dialog-kill-switch-grund')).toBeVisible();

    await page.getByTestId('dialog-kill-switch-abbrechen').click();
    await expect(dialog).toBeHidden();
  });
});
