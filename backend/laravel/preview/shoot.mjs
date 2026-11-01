import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'

const outDir = '/opt/cursor/artifacts/screenshots'
await mkdir(outDir, { recursive: true })

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
await page.goto('http://127.0.0.1:4179', { waitUntil: 'networkidle' })

const screens = ['dashboard', 'zone', 'device', 'alerts', 'launch']
for (const theme of ['dark', 'light']) {
  await page.evaluate((value) => {
    document.documentElement.dataset.theme = value
    document.documentElement.style.colorScheme = value
  }, theme)
  await page.waitForTimeout(150)
  for (const screen of screens) {
    const target = page.locator(`[data-screen="${screen}"]`)
    await target.screenshot({ path: `${outDir}/${screen}-${theme}.png` })
  }
}

await browser.close()
console.log('screenshots written to', outDir)
