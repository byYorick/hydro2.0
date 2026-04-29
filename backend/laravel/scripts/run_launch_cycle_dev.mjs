/**
 * E2E: /launch — теплица, зона, культура, рецепт (API), ноды, калибровки, запуск цикла.
 * Требует: docker dev stack, chromium, psql к hydro_dev, ExtendedGrowStagesSeeder (шаблоны фаз).
 *
 * Запуск (с хоста):
 *   cd backend/laravel && node scripts/run_launch_cycle_dev.mjs
 *
 * Переменные: BASE_URL, DB_NAME, LOGIN_EMAIL, LOGIN_PASSWORD
 */
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url))
const APP_ROOT = path.resolve(SCRIPT_DIR, '..')
process.chdir(APP_ROOT)

const BASE_URL = process.env.BASE_URL || 'http://localhost:8080'
const LOGIN_EMAIL = process.env.LOGIN_EMAIL || 'agronomist@example.com'
const LOGIN_PASSWORD = process.env.LOGIN_PASSWORD || 'password'
const TS = new Date().toISOString().replace(/[:.]/g, '-')
const DB_NAME = process.env.DB_NAME || 'hydro_dev'
const STAGE_TEMPLATE_ID = Number(process.env.STAGE_TEMPLATE_ID || '1')

function detectChromiumExecutable() {
  const candidates = [
    process.env.CHROMIUM_EXECUTABLE,
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
    '/usr/bin/google-chrome',
  ].filter(Boolean)
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  return undefined
}

function run(cmd, args) {
  return execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
}

function psqlJson(sql) {
  return run('psql', [
    '-h', process.env.PGHOST || 'localhost',
    '-U', process.env.PGUSER || 'hydro',
    '-d', DB_NAME,
    '-t', '-A',
    '-c',
    `select coalesce(json_agg(t), '[]'::json) from (${sql}) t;`,
  ]).trim()
}

function queryRows(sql) {
  const raw = psqlJson(sql)
  if (!raw) return []
  try {
    return JSON.parse(raw)
  } catch {
    return []
  }
}

function psqlScalar(sql) {
  const rows = queryRows(sql)
  if (!rows.length) return ''
  const v = Object.values(rows[0] ?? {})[0]
  return v == null ? '' : String(v)
}

function sqlString(value) {
  return `'${String(value).replace(/'/g, "''")}'`
}

async function waitForText(page, text, timeout = 60000) {
  await page.waitForFunction(
    (needle) => document.body.innerText.includes(needle),
    text,
    { timeout },
  )
}

/** ShellCard внутри шага «Зона» (колонка слева): 0 — теплица, 1 — зона. */
function launchShellCards(page) {
  return page.locator('section.grid.gap-4.items-start > .flex.flex-col.gap-3 > section')
}

/** Колонка шага «Рецепт»: вложенные ShellCard по порядку. */
function recipeShellCards(page) {
  return page
    .locator('section.grid')
    .filter({
      has: page.locator('header .text-sm.font-semibold').getByText('Растение', { exact: true }),
    })
    .first()
    .locator('> .flex.flex-col.gap-3 > section')
}

async function ensureButtonEnabled(locator, timeout = 60000) {
  await locator.waitFor({ state: 'visible', timeout })
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const disabled = await locator.isDisabled().catch(() => true)
    if (!disabled) return
    await locator.page().waitForTimeout(250)
  }
}

async function selectByLabel(page, label, value) {
  await page.getByLabel(label).selectOption(String(value))
}

async function waitForNodeOptions(page, labels, timeout = 60000) {
  await page.waitForFunction(
    (targetLabels) => {
      const sections = Array.from(document.querySelectorAll('label'))
      return targetLabels.every((labelText) => {
        const labelEl = sections.find((el) => (el.textContent || '').includes(labelText))
        const select = labelEl ? labelEl.querySelector('select') : null
        return Boolean(select && select.options.length > 1)
      })
    },
    labels,
    { timeout },
  )
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: detectChromiumExecutable(),
    args: ['--no-sandbox'],
  })
  const context = await browser.newContext({ viewport: { width: 1600, height: 2200 } })
  const page = await context.newPage()
  page.setDefaultTimeout(120000)

  const greenhouseName = `Теплица launch ${TS}`
  const zoneName = `Зона launch ${TS}`
  const plantName = `Культура launch ${TS}`
  const recipeName = `Рецепт launch ${TS}`

  const created = { zoneId: null, plantId: null, recipeId: null, recipeRevisionId: null }

  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
    const loginResult = await page.evaluate(async ({ email, password }) => {
      const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
      const headers = { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' }
      if (csrf) headers['X-CSRF-TOKEN'] = csrf
      const body = new URLSearchParams({ email, password, remember: 'on' })
      const response = await fetch('/login', { method: 'POST', credentials: 'include', headers, body })
      return { status: response.status, ok: response.ok, url: response.url }
    }, { email: LOGIN_EMAIL, password: LOGIN_PASSWORD })
    console.log('LOGIN_RESULT:', JSON.stringify(loginResult))
    if (!loginResult.ok) throw new Error(`Login failed: ${JSON.stringify(loginResult)}`)

    await page.goto(`${BASE_URL}/launch`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-test="launch-manifest-skeleton"]').waitFor({ state: 'detached', timeout: 120000 }).catch(() => {})
    await waitForText(page, 'Теплица', 120000)

    const ghCard = launchShellCards(page).nth(0)
    await ghCard.getByRole('button', { name: '+ Создать' }).click()
    await ghCard.getByPlaceholder('Berry').fill(greenhouseName)
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/api/greenhouses')),
      ghCard.getByRole('button', { name: 'Создать теплицу' }).click(),
    ])
    await waitForText(page, greenhouseName, 60000)

    const zoneCard = launchShellCards(page).nth(1)
    await zoneCard.getByRole('button', { name: '+ Создать' }).click()
    await zoneCard.getByPlaceholder('Zone A').fill(zoneName)
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/api/zones')),
      zoneCard.getByRole('button', { name: 'Создать зону' }).click(),
    ])
    await waitForText(page, zoneName, 60000)

    const zoneId = Number(psqlScalar(`select id from zones where name = ${sqlString(zoneName)} order by id desc limit 1`))
    if (!zoneId) throw new Error('zoneId not found')
    created.zoneId = zoneId
    console.log('ZONE_ID:', zoneId)

    await page.waitForTimeout(1500)
    // После выбора зоны manifest может скрыть шаг «Зона» и сразу открыть «Рецепт».
    const recipeHeader = page.locator('header .text-sm.font-semibold').filter({ hasText: 'Растение' }).first()
    if (!(await recipeHeader.isVisible().catch(() => false))) {
      const next1 = page.getByRole('button', { name: 'Дальше →' })
      await ensureButtonEnabled(next1, 60000)
      await next1.click()
    }
    await waitForText(page, 'Растение', 60000)

    const plantCard = recipeShellCards(page).nth(0)
    await plantCard.getByRole('button', { name: '+ Создать' }).click()
    await plantCard.getByPlaceholder('Томат').fill(plantName)
    await Promise.all([
      page.waitForResponse((r) => r.request().method() === 'POST' && r.url().includes('/api/plants')),
      plantCard.getByRole('button', { name: 'Создать растение' }).click(),
    ])
    await waitForText(page, plantName, 60000)

    const plantId = Number(psqlScalar(`select id from plants where name = ${sqlString(plantName)} order by id desc limit 1`))
    if (!plantId) throw new Error('plantId not found')
    created.plantId = plantId

    const apiRecipe = await page.evaluate(
      async ({ plantId, recipeName, stageTemplateId }) => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
        if (csrf) headers['X-CSRF-TOKEN'] = csrf

        const r1 = await fetch('/api/recipes', {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify({ name: recipeName, plant_id: plantId, description: 'run_launch_cycle_dev' }),
        })
        const j1 = await r1.json().catch(() => null)
        if (!r1.ok) return { ok: false, step: 'recipes', status: r1.status, j1 }
        const recipeId = j1?.data?.id
        const r2 = await fetch(`/api/recipes/${recipeId}/revisions`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify({}),
        })
        const j2 = await r2.json().catch(() => null)
        if (!r2.ok) return { ok: false, step: 'revisions', status: r2.status, j2 }
        const revisionId = j2?.data?.id

        const phaseBody = {
          name: 'Фаза 1',
          phase_index: 0,
          stage_template_id: stageTemplateId,
          ph_target: 6.0,
          ph_min: 5.5,
          ph_max: 6.5,
          ec_target: 1.4,
          ec_min: 1.0,
          ec_max: 2.0,
          irrigation_mode: 'RECIRC',
          irrigation_interval_sec: 3600,
          irrigation_duration_sec: 120,
          progress_model: 'TIME',
          duration_days: 30,
        }
        const r3 = await fetch(`/api/recipe-revisions/${revisionId}/phases`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify(phaseBody),
        })
        const j3 = await r3.json().catch(() => null)
        if (!r3.ok) return { ok: false, step: 'phase', status: r3.status, j3 }

        const r4 = await fetch(`/api/recipe-revisions/${revisionId}/publish`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify({}),
        })
        const j4 = await r4.json().catch(() => null)
        if (!r4.ok) return { ok: false, step: 'publish', status: r4.status, j4 }

        return { ok: true, recipeId, revisionId }
      },
      { plantId, recipeName, stageTemplateId: STAGE_TEMPLATE_ID },
    )
    console.log('API_RECIPE_RESULT:', JSON.stringify(apiRecipe))
    if (!apiRecipe.ok) throw new Error(`Recipe API failed: ${JSON.stringify(apiRecipe)}`)
    created.recipeId = apiRecipe.recipeId
    created.recipeRevisionId = apiRecipe.revisionId

    const recipeCard = recipeShellCards(page).nth(1)
    await recipeCard.getByRole('button', { name: '↻ Обновить' }).click()
    await page.waitForTimeout(800)
    await page.getByLabel('Рецепт и ревизия').selectOption(String(apiRecipe.recipeId))
    await page.waitForTimeout(500)

    const dateCard = recipeShellCards(page).nth(2)
    await dateCard.getByRole('button', { name: 'Сейчас' }).click()

    const next2 = page.getByRole('button', { name: 'Дальше →' })
    await ensureButtonEnabled(next2)
    await next2.click()
    await waitForText(page, 'Автоматика', 60000).catch(() => waitForText(page, 'Узел полива', 60000))

    const nodeRows = queryRows(`
      select uid, id, zone_id from nodes
      where uid in ('nd-test-irrig-1', 'nd-test-ph-1', 'nd-test-ec-1')
      order by uid
    `)
    const nodeIdsByUid = new Map()
    for (const row of nodeRows) {
      if (row.uid && row.id) nodeIdsByUid.set(String(row.uid), Number(row.id))
    }
    const irrigationNodeId = nodeIdsByUid.get('nd-test-irrig-1')
    const phNodeId = nodeIdsByUid.get('nd-test-ph-1')
    const ecNodeId = nodeIdsByUid.get('nd-test-ec-1')
    if (!irrigationNodeId || !phNodeId || !ecNodeId) {
      throw new Error(`Ноды не найдены: ${JSON.stringify([...nodeIdsByUid])}`)
    }

    const nodesToDetach = nodeRows.filter((n) => n.zone_id != null && n.zone_id !== '')
    if (nodesToDetach.length) {
      await page.evaluate(async ({ nodes }) => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
        if (csrf) headers['X-CSRF-TOKEN'] = csrf
        for (const node of nodes) {
          await fetch(`/api/nodes/${node.id}/detach`, { method: 'POST', credentials: 'include', headers })
        }
      }, { nodes: nodesToDetach })
    }

    const bindingResult = await page.evaluate(
      async ({ zoneId, irrigationNodeId, phNodeId, ecNodeId }) => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
        if (csrf) headers['X-CSRF-TOKEN'] = csrf
        const payload = {
          zone_id: zoneId,
          assignments: {
            irrigation: irrigationNodeId,
            ph_correction: phNodeId,
            ec_correction: ecNodeId,
            accumulation: irrigationNodeId,
            climate: null,
            light: null,
            co2_sensor: null,
            co2_actuator: null,
            root_vent_actuator: null,
          },
          selected_node_ids: [irrigationNodeId, phNodeId, ecNodeId],
        }
        const v = await fetch('/api/setup-wizard/validate-devices', {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify(payload),
        })
        const a = await fetch('/api/setup-wizard/apply-device-bindings', {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify(payload),
        })
        return {
          validate: { status: v.status, body: await v.json().catch(() => null) },
          apply: { status: a.status, body: await a.json().catch(() => null) },
        }
      },
      { zoneId, irrigationNodeId, phNodeId, ecNodeId },
    )
    console.log('BINDING_RESULT:', JSON.stringify(bindingResult))
    if (bindingResult.apply.status >= 400) throw new Error(`apply-device-bindings failed: ${JSON.stringify(bindingResult)}`)

    // В dev без MQTT config_report узлы не получают zone_id — UI не строит select по привязкам.
    // Промоутим тестовые ноды в зону (только для локального dev-скрипта).
    run('psql', [
      '-h', process.env.PGHOST || 'localhost',
      '-U', process.env.PGUSER || 'hydro',
      '-d', DB_NAME,
      '-c',
      `update nodes set zone_id = ${zoneId}, pending_zone_id = null, lifecycle_state = 'ASSIGNED_TO_ZONE', updated_at = now()
       where uid in ('nd-test-irrig-1','nd-test-ph-1','nd-test-ec-1');`,
    ])

    await page.getByRole('button', { name: '↻ Обновить ноды' }).click().catch(() => page.getByRole('button', { name: 'Обновить ноды' }).click())
    await page.waitForResponse((r) => r.request().method() === 'GET' && r.url().includes('/api/nodes')).catch(() => {})
    await page.getByRole('button', { name: '↻ Перечитать всё' }).click().catch(() => {})
    await page.waitForTimeout(2000)

    const hasIrrigationSelect = await page.getByLabel('Узел полива').isVisible().catch(() => false)
    if (hasIrrigationSelect) {
      await waitForNodeOptions(page, ['Узел полива', 'Узел коррекции pH', 'Узел коррекции EC']).catch(() => {})
      await selectByLabel(page, 'Узел полива', irrigationNodeId)
      await selectByLabel(page, 'Узел коррекции pH', phNodeId)
      await selectByLabel(page, 'Узел коррекции EC', ecNodeId)
      await page.waitForTimeout(400)
    }

    const toCalibration = page.getByRole('button', { name: 'Дальше →' })
    await ensureButtonEnabled(toCalibration, 120000)
    await toCalibration.click()
    await page.waitForTimeout(2000)

    const health = await page.evaluate(async (zoneId) => {
      const r = await fetch(`/api/zones/${zoneId}/health`)
      return r.json()
    }, zoneId)
    console.log('HEALTH_AFTER_AUTOMATION:', JSON.stringify(health))
    if (health?.data?.readiness?.dispatch_enabled === false) {
      const rt = await page.evaluate(async () => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
        if (csrf) headers['X-CSRF-TOKEN'] = csrf
        const r = await fetch('/api/automation-configs/system/0/system.runtime', {
          method: 'PUT',
          credentials: 'include',
          headers,
          body: JSON.stringify({
            payload: { 'automation_engine.grow_cycle_start_dispatch_enabled': true },
          }),
        })
        return { status: r.status, body: await r.json().catch(() => null) }
      })
      console.log('RUNTIME_ENABLE:', JSON.stringify(rt))
    }

    for (const [type, namespace, config] of [
      [
        'ph',
        'zone.pid.ph',
        {
          dead_zone: 0.05,
          close_zone: 0.3,
          far_zone: 1.0,
          zone_coeffs: { close: { kp: 5, ki: 0.05, kd: 0 }, far: { kp: 8, ki: 0.02, kd: 0 } },
          max_integral: 20,
        },
      ],
      [
        'ec',
        'zone.pid.ec',
        {
          dead_zone: 0.1,
          close_zone: 0.5,
          far_zone: 1.5,
          zone_coeffs: { close: { kp: 30, ki: 0.3, kd: 0 }, far: { kp: 50, ki: 0.1, kd: 0 } },
          max_integral: 100,
        },
      ],
    ]) {
      const pidRes = await page.evaluate(
        async ({ zoneId, namespace, configPayload, pidLabel }) => {
          const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
          const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
          if (csrf) headers['X-CSRF-TOKEN'] = csrf
          const r = await fetch(`/api/automation-configs/zone/${zoneId}/${namespace}`, {
            method: 'PUT',
            credentials: 'include',
            headers,
            body: JSON.stringify({ payload: configPayload }),
          })
          return { pidLabel, status: r.status, ok: r.ok, body: await r.json().catch(() => null) }
        },
        { zoneId, namespace, configPayload: config, pidLabel: type },
      )
      console.log(`PID_${type}:`, JSON.stringify(pidRes))
    }

    await page.getByTestId('process-calibration-save').click().catch(() => {})
    await page.waitForTimeout(1200)

    const pumpSnap = await page.evaluate(async (zoneId) => {
      const r = await fetch(`/api/zones/${zoneId}/pump-calibrations`, { credentials: 'include' })
      return { ok: r.ok, body: await r.json().catch(() => null) }
    }, zoneId)
    const channelIdByComponent = new Map(
      (pumpSnap.body?.data ?? []).map((item) => [item.component, item.node_channel_id]),
    )

    const transportRows = queryRows(`
      select cb.role::text as role, nc.id::bigint as channel_id
      from channel_bindings cb
      join node_channels nc on nc.id = cb.node_channel_id
      join infrastructure_instances ii on ii.id = cb.infrastructure_instance_id
      where ii.owner_type = 'zone' and ii.owner_id = ${zoneId}
        and cb.role in ('pump_main', 'drain')
    `)
    for (const row of transportRows) {
      const ch = Number(row.channel_id)
      if (!ch) continue
      const tr = await page.evaluate(
        async ({ zoneId, channelId }) => {
          const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
          const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
          if (csrf) headers['X-CSRF-TOKEN'] = csrf
          const r = await fetch(`/api/zones/${zoneId}/calibrate-pump`, {
            method: 'POST',
            credentials: 'include',
            headers,
            body: JSON.stringify({
              node_channel_id: channelId,
              duration_sec: 20,
              actual_ml: 20,
              skip_run: true,
              manual_override: true,
            }),
          })
          return { ok: r.ok, status: r.status, body: await r.json().catch(() => null) }
        },
        { zoneId, channelId: ch },
      )
      console.log(`PUMP_TRANSPORT_${row.role}:`, JSON.stringify(tr))
    }

    for (const component of ['ph_down', 'ph_up', 'npk', 'calcium', 'magnesium', 'micro']) {
      const channelId = channelIdByComponent.get(component)
      if (!channelId) continue
      const cal = await page.evaluate(
        async ({ zoneId, component, channelId }) => {
          const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
          const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
          if (csrf) headers['X-CSRF-TOKEN'] = csrf
          const r = await fetch(`/api/zones/${zoneId}/calibrate-pump`, {
            method: 'POST',
            credentials: 'include',
            headers,
            body: JSON.stringify({
              node_channel_id: channelId,
              component,
              duration_sec: 20,
              actual_ml: 20,
              skip_run: true,
              manual_override: true,
            }),
          })
          return { component, ok: r.ok, status: r.status, body: await r.json().catch(() => null) }
        },
        { zoneId, component, channelId },
      )
      console.log(`PUMP_${component}:`, JSON.stringify(cal))
    }

    while (await page.getByRole('button', { name: 'Дальше →' }).isVisible().catch(() => false)) {
      const b = page.getByRole('button', { name: 'Дальше →' })
      const dis = await b.isDisabled().catch(() => true)
      if (dis) break
      await b.click()
      await page.waitForTimeout(600)
    }

    // Клиентский manifest Launch может оставаться устаревшим после API-калибровок.
    // Запуск цикла через тот же endpoint, что и UI (POST /api/zones/{id}/grow-cycles).
    const launchApi = await page.evaluate(
      async ({ zoneId, recipeRevisionId, plantId }) => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
        if (csrf) headers['X-CSRF-TOKEN'] = csrf
        const r = await fetch(`/api/zones/${zoneId}/grow-cycles`, {
          method: 'POST',
          credentials: 'include',
          headers,
          body: JSON.stringify({
            recipe_revision_id: recipeRevisionId,
            plant_id: plantId,
            planting_at: new Date().toISOString(),
            start_immediately: true,
          }),
        })
        return { status: r.status, ok: r.ok, body: await r.json().catch(() => null) }
      },
      {
        zoneId,
        recipeRevisionId: created.recipeRevisionId,
        plantId: created.plantId,
      },
    )
    console.log('LAUNCH_API:', JSON.stringify(launchApi))
    if (!launchApi.ok) {
      throw new Error(`POST grow-cycles failed: ${JSON.stringify(launchApi)}`)
    }
    await page.waitForTimeout(2000)

    let cycleRow = ''
    for (let i = 0; i < 24; i += 1) {
      cycleRow = psqlScalar(`
        select id::text from grow_cycles where zone_id = ${zoneId} order by id desc limit 1
      `)
      if (cycleRow) break
      await page.waitForTimeout(2000)
    }
    console.log('GROW_CYCLE_ID:', cycleRow || 'none')
    if (!cycleRow) throw new Error('Grow cycle not created')

    const alerts = queryRows(
      `select id, code, type, status, severity, details::text as details from alerts where zone_id = ${zoneId} order by id desc limit 8`,
    )
    console.log('ALERTS:', JSON.stringify(alerts, null, 2))
  } catch (e) {
    console.error('SCRIPT_ERROR:', e)
    console.error('URL:', page.url())
    console.error('BODY:', (await page.locator('body').innerText().catch(() => '')).slice(0, 4000))
    process.exitCode = 1
  } finally {
    await browser.close()
  }
}

await main()
