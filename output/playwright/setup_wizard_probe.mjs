import { chromium } from 'playwright';

const browser = await chromium.launch({
  headless: true,
  executablePath: '/snap/bin/chromium',
  args: ['--no-sandbox'],
});

const context = await browser.newContext();
const page = await context.newPage();

await page.goto('http://localhost:8080/login', { waitUntil: 'networkidle' });
await page.getByTestId('login-email').fill('agronomist@example.com');
await page.getByTestId('login-password').fill('password');
await page.getByTestId('login-submit').click();
await page.waitForTimeout(2000);

console.log('AFTER_LOGIN_URL:', page.url());

await page.goto('http://localhost:8080/setup/wizard', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

console.log('WIZARD_URL:', page.url());
console.log('WIZARD_TITLE:', await page.title());
console.log('WIZARD_TEXT_HEAD:', (await page.locator('body').innerText()).slice(0, 2500));

const testIds = await page.locator('[data-test], [data-testid]').evaluateAll((els) =>
  els.map((el) => ({
    tag: el.tagName,
    text: (el.textContent || '').trim().slice(0, 80),
    testId: el.getAttribute('data-testid') || el.getAttribute('data-test'),
    id: el.id || null,
  }))
);

console.log('TEST_IDS:', JSON.stringify(testIds, null, 2));

await browser.close();
