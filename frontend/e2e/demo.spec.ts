import { expect, test } from '@playwright/test';

// Runs only against a server started in demo mode (e.g. the Codespaces trial image): UH_E2E_DEMO=1
test.describe('demo mode', () => {
  test.skip(!process.env.UH_E2E_DEMO, 'set UH_E2E_DEMO=1 for a server running with ULTRAHOFS_DEMO_MODE=true');

  test('one-click demo login opens the platform', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByTestId('demo-box')).toBeVisible();
    await page.screenshot({ path: `${process.env.UH_SHOTS || 'test-results/screens'}/00-demo-login.png` });
    await page.getByTestId('demo-enter').click();
    await expect(page.getByText('实验 HOF 条目')).toBeVisible();
    await expect(page.locator('.ant-statistic-content-value').first()).not.toHaveText('—');
    await page.goto('/database');
    await expect(page.locator('.mol-card').first()).toBeVisible();
    await page.locator('.mol-card').first().click();
    await expect(page.locator('a[href^="https://doi.org/"]').first()).toBeVisible();
    await page.getByRole('tab', { name: '三维结构' }).click();
    await expect(page.locator('.viewer3d canvas').first()).toBeVisible();
  });
});
