import { expect, test } from '@playwright/test'

// Exercise the current authority API with the browser's authenticated session.
// The former PID Settings/PID Logs tabs no longer represent the runtime contract.
for (const type of ['ph', 'ec']) {
  test.describe(`PID authority ${type}`, () => {
    let zoneId: number
    let endpoint: string
    test.beforeEach(async ({ page }) => {
      await page.goto('/testing/login?email=agronomist@example.com')
      await page.waitForSelector('#app[data-page]', { state: 'attached' })
      const response = await page.request.get('/api/zones')
      expect(response.ok()).toBeTruthy()
      const payload = await response.json()
      const zones = payload.data?.data ?? payload.data
      expect(zones.length, 'bootstrap must provide a zone').toBeGreaterThan(0)
      zoneId = Number(zones[0].id)
      endpoint = `/api/automation-configs/zone/${zoneId}/zone.pid.${type}`
    })

    test('loads a valid configuration from Laravel', async ({ page }) => {
      const response = await page.request.get(endpoint)
      expect(response.ok()).toBeTruthy()
      const body = await response.json()
      expect(body.data.namespace).toBe(`zone.pid.${type}`)
      expect(body.data.payload.dead_zone).toBeGreaterThanOrEqual(0)
      expect(body.data.payload.zone_coeffs.close.kp).toBeGreaterThanOrEqual(0)
    })

    test('persists a valid change and returns it on a new read', async ({ page }) => {
      const before = await (await page.request.get(endpoint)).json()
      const payload = { ...before.data.payload, max_integral: 21 }
      const xsrf = (await page.context().cookies()).find(cookie => cookie.name === 'XSRF-TOKEN')
      const response = await page.request.put(endpoint, {
        data: { payload },
        headers: xsrf ? { 'X-XSRF-TOKEN': decodeURIComponent(xsrf.value) } : {},
      })
      expect(response.ok(), await response.text()).toBeTruthy()
      const after = await (await page.request.get(endpoint)).json()
      expect(after.data.payload.max_integral).toBe(21)
    })

    test('rejects an invalid value without corrupting saved configuration', async ({ page }) => {
      const before = await (await page.request.get(endpoint)).json()
      const xsrf = (await page.context().cookies()).find(cookie => cookie.name === 'XSRF-TOKEN')
      const response = await page.request.put(endpoint, {
        data: { payload: { ...before.data.payload, dead_zone: -1 } },
        headers: xsrf ? { 'X-XSRF-TOKEN': decodeURIComponent(xsrf.value) } : {},
      })
      expect(response.status()).toBe(422)
      const after = await (await page.request.get(endpoint)).json()
      expect(after.data.payload).toEqual(before.data.payload)
    })
  })
}
