const { chromium } = require('playwright')

const BASE_URL = 'http://localhost:8080'
const EMAIL = 'agronomist@example.com'
const PASSWORD = 'password'

const ZONE_ID = 4
const PLANT_ID = 1
const RECIPE_ID = 1
const RECIPE_REVISION_ID = 1

const PUMP_CALIBRATIONS = [
  { node_channel_id: 13, component: 'ph_up', channel: 'pump_base' },
  { node_channel_id: 12, component: 'ph_down', channel: 'pump_acid' },
  { node_channel_id: 16, component: 'npk', channel: 'pump_a' },
  { node_channel_id: 17, component: 'calcium', channel: 'pump_b' },
  { node_channel_id: 18, component: 'magnesium', channel: 'pump_c' },
  { node_channel_id: 19, component: 'micro', channel: 'pump_d' },
]

const PID_CONFIGS = {
  ph: {
    target: 5.8,
    dead_zone: 0.05,
    close_zone: 0.3,
    far_zone: 1,
    zone_coeffs: {
      close: { kp: 5, ki: 0.05, kd: 0 },
      far: { kp: 8, ki: 0.02, kd: 0 },
    },
    max_output: 20,
    min_interval_ms: 90000,
    max_integral: 20,
  },
  ec: {
    target: 1.6,
    dead_zone: 0.1,
    close_zone: 0.5,
    far_zone: 1.5,
    zone_coeffs: {
      close: { kp: 30, ki: 0.3, kd: 0 },
      far: { kp: 50, ki: 0.1, kd: 0 },
    },
    max_output: 50,
    min_interval_ms: 120000,
    max_integral: 100,
  },
}

const PROCESS_CONFIG = {
  ec_gain_per_ml: 0.11,
  ph_up_gain_per_ml: 0.08,
  ph_down_gain_per_ml: 0.07,
  ph_per_ec_ml: -0.015,
  ec_per_ph_ml: 0.02,
  transport_delay_sec: 20,
  settle_sec: 45,
  confidence: 0.75,
}

async function login(page) {
  await page.goto('/login', { waitUntil: 'domcontentloaded' })
  await page.locator('#email').fill(EMAIL)
  await page.locator('#password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Войти в систему' }).click()
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 10000 }).catch(() => {})
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(500)
}

async function csrf(page) {
  return page.locator('meta[name="csrf-token"]').getAttribute('content')
}

function toLocalDatetimeLocal(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

async function apiJson(page, token, method, path, body) {
  return page.evaluate(async ({ token, method, path, body }) => {
    const response = await fetch(path, {
      method,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRF-TOKEN': token,
      },
      body: body ? JSON.stringify(body) : undefined,
    })

    const contentType = response.headers.get('content-type') || ''
    const payload = contentType.includes('application/json') ? await response.json() : await response.text()

    if (!response.ok) {
      throw new Error(`${method} ${path} failed: ${response.status} ${typeof payload === 'string' ? payload : JSON.stringify(payload)}`)
    }

    return payload
  }, { token, method, path, body })
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/snap/bin/chromium',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })

  const context = await browser.newContext({ baseURL: BASE_URL })
  const page = await context.newPage()

  await login(page)
  const token = await csrf(page)
  if (!token) {
    throw new Error('CSRF token not found')
  }

  for (const item of PUMP_CALIBRATIONS) {
    await apiJson(page, token, 'POST', `/api/zones/${ZONE_ID}/calibrate-pump`, {
      node_channel_id: item.node_channel_id,
      duration_sec: 10,
      actual_ml: 10,
      component: item.component,
      skip_run: true,
      manual_override: true,
    })
  }

  for (const type of ['ph', 'ec']) {
    await apiJson(page, token, 'PUT', `/api/zones/${ZONE_ID}/pid-configs/${type}`, {
      config: PID_CONFIGS[type],
    })
  }

  for (const mode of ['solution_fill', 'tank_recirc', 'irrigation', 'generic']) {
    await apiJson(page, token, 'PUT', `/api/zones/${ZONE_ID}/process-calibrations/${mode}`, PROCESS_CONFIG)
  }

  const healthBefore = await apiJson(page, token, 'GET', `/api/zones/${ZONE_ID}/health`)
  console.log('READINESS_BEFORE', JSON.stringify(healthBefore.readiness, null, 2))

  const startedAt = new Date().toISOString()
  const cycleResponse = await apiJson(page, token, 'POST', `/api/zones/${ZONE_ID}/grow-cycles`, {
    recipe_revision_id: RECIPE_REVISION_ID,
    plant_id: PLANT_ID,
    planting_at: startedAt,
    start_immediately: true,
    irrigation: {
      system_type: 'nft',
      interval_minutes: 30,
      duration_seconds: 120,
      irrigation_batch_l: 1,
    },
    phase_overrides: {
      ph_target: PID_CONFIGS.ph.target,
      ec_target: PID_CONFIGS.ec.target,
    },
    settings: {
      expected_harvest_at: '',
    },
  })

  console.log('CYCLE_RESPONSE', JSON.stringify(cycleResponse, null, 2))
  await page.goto(`/zones/${ZONE_ID}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  console.log('URL', page.url())
  console.log('TITLE', await page.title())
  console.log((await page.locator('body').innerText()).slice(0, 3500))

  await browser.close()
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
