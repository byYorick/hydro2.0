import { chromium } from '@playwright/test'
import fs from 'node:fs'

const BASE = process.env.BASE_URL ?? 'http://localhost:8080'
const EMAIL = process.env.SHOT_EMAIL ?? 'admin@example.com'
const PASSWORD = process.env.SHOT_PASSWORD ?? 'password'
const OUT = process.env.SHOT_DIR ?? '/tmp/hydro-shots'

const targets = JSON.parse(process.env.SHOT_TARGETS ?? '[]')

fs.mkdirSync(OUT, { recursive: true })

const browser = await chromium.launch()
const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
const page = await context.newPage()

await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(1500)
if (page.url().includes('/login')) {
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForTimeout(3000)
}
console.log('after login url:', page.url())

for (const target of targets) {
  const { path, name } = target
  try {
    await page.goto(`${BASE}${path}`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(target.wait ?? 3000)
    if (target.click) {
      for (const sel of target.click) {
        await page.click(sel, { timeout: 4000 }).catch((e) => console.log('click fail', sel, e.message))
        await page.waitForTimeout(1200)
      }
    }
    await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: target.fullPage ?? true })
    console.log('ok', name, page.url())
  } catch (error) {
    console.log('fail', name, error.message)
  }
}

await browser.close()
