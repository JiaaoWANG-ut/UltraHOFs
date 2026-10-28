import { expect, test, type Page } from '@playwright/test';

const USER = process.env.UH_E2E_USER || 'admin';
const PASS = process.env.UH_E2E_PASSWORD || '';
const SHOTS = process.env.UH_SHOTS || 'test-results/screens';
const TMA = 'OC(=O)c1cc(C(O)=O)cc(C(O)=O)c1';

async function login(page: Page) {
  await page.goto('/login');
  await expect(page.getByText('知声无界').first()).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/01-login.png` });
  await page.getByLabel('用户名').fill(USER);
  await page.getByLabel('密码').fill(PASS);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText('实验 HOF 条目')).toBeVisible();
}

test.describe.serial('UltraHOFs main flows', () => {
  test.skip(!PASS, 'set UH_E2E_PASSWORD');
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
    await login(page);
  });

  test('home shows database statistics', async () => {
    await expect(page.locator('.ant-statistic-content-value').first()).not.toHaveText('—');
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${SHOTS}/02-home.png`, fullPage: true });
  });

  test('database search and entry citation', async () => {
    await page.goto('/database?q=HOF&dim=2');
    await expect(page.locator('.mol-card').first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/03-database.png` });
    await page.locator('.mol-card').first().click();
    await expect(page.locator('a[href^="https://doi.org/"]').first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/04-entry.png`, fullPage: true });
    await page.getByRole('tab', { name: '三维结构' }).click();
    await expect(page.locator('.viewer3d canvas').first()).toBeVisible();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${SHOTS}/05-entry-3d.png` });
  });

  test('evaluate a molecule with precedent lookup', async () => {
    await page.goto(`/design/evaluate?smiles=${encodeURIComponent(TMA)}`);
    await expect(page.locator('.score-big')).toBeVisible();
    await expect(page.getByText('推荐拓扑')).toBeVisible();
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${SHOTS}/06-evaluate.png`, fullPage: true });
  });

  test('generate candidates', async () => {
    await page.goto('/design/generate');
    await page.getByRole('button', { name: '开始生成' }).click();
    await expect(page.locator('.mol-card').first()).toBeVisible({ timeout: 150_000 });
    await page.screenshot({ path: `${SHOTS}/07-generate.png` });
  });

  test('build a periodic structure, export CIF and submit relaxation', async () => {
    await page.goto(`/builder?node=${encodeURIComponent(TMA)}&net=hcb`);
    await expect(page.getByText('BB1')).toBeVisible();
    await page.getByTestId('build-btn').click();
    await expect(page.getByText('质量检查').first().or(page.locator('.ant-descriptions').first())).toBeVisible();
    await expect(page.locator('.viewer3d canvas').nth(1)).toBeVisible();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${SHOTS}/08-builder.png`, fullPage: true });
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'CIF (P1)' }).click()]);
    expect(download.suggestedFilename()).toMatch(/\.cif$/);
    await page.getByRole('button', { name: 'MACE-OFF24 结构优化' }).click();
    await page.getByLabel('steps (atoms)').fill('15');
    await page.getByLabel('steps (cell)').fill('5');
    await page.getByRole('button', { name: '提交优化任务' }).click();
    await expect(page).toHaveURL(/\/jobs/);
    await expect(page.locator('.ant-table-row').first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/09-jobs.png` });
  });

  test('two-component pair evaluation', async () => {
    await page.goto('/design/pairs');
    await page.getByRole('button', { name: '评估组合' }).first().click();
    await expect(page.getByText('配比').first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/10-pairs.png`, fullPage: true });
  });

  test('english interface switch', async () => {
    await page.goto('/');
    await page.getByRole('button', { name: 'English' }).click();
    await expect(page.getByText('Experimental HOF entries')).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/11-home-en.png` });
    await page.getByRole('button', { name: '中文' }).click();
  });
});
