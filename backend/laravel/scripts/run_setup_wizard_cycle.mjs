import { execFileSync } from 'node:child_process'
import { chromium } from 'playwright'

const BASE_URL = 'http://localhost:8080'
const LOGIN_EMAIL = 'agronomist@example.com'
const LOGIN_PASSWORD = 'password'
const TS = new Date().toISOString().replace(/[:.]/g, '-')

function run(cmd, args) {
  return execFileSync(cmd, args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
}

function sqlString(value) {
  return `'${String(value).replace(/'/g, "''")}'`
}

function psqlScalar(sql) {
  return run('docker', [
    'exec',
    'backend-db-1',
    'psql',
    '-U',
    'hydro',
    '-d',
    'hydro_dev',
    '-t',
    '-A',
    '-c',
    sql,
  ]).trim()
}

function psqlRows(sql) {
  return run('docker', [
    'exec',
    'backend-db-1',
    'psql',
    '-U',
    'hydro',
    '-d',
    'hydro_dev',
    '-t',
    '-A',
    '-F',
    '|',
    '-c',
    sql,
  ]).trim()
}

async function waitForText(page, text, timeout = 30000) {
  await page.waitForFunction(
    (needle) => document.body.innerText.includes(needle),
    text,
    { timeout }
  )
}

async function waitForNodeOptions(page, labels, timeout = 30000) {
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
    { timeout }
  )
}

async function selectByLabel(page, label, value) {
  const locator = page.getByLabel(label)
  await locator.selectOption(String(value))
}

async function ensureButtonEnabled(locator, timeout = 30000) {
  await locator.waitFor({ state: 'visible', timeout })
  await locator.waitFor({ state: 'attached', timeout })
  await locator.evaluate((el) => {
    if (el instanceof HTMLButtonElement && el.disabled) {
      throw new Error(`Button is disabled: ${el.textContent || ''}`)
    }
  })
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/snap/bin/chromium',
    args: ['--no-sandbox'],
  })

  const context = await browser.newContext({
    viewport: { width: 1600, height: 2200 },
  })
  const page = await context.newPage()
  page.setDefaultTimeout(120000)
  page.setDefaultNavigationTimeout(120000)
  const created = {
    greenhouseId: null,
    zoneId: null,
    plantId: null,
    recipeId: null,
    recipeRevisionId: null,
  }

  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' })
    const loginResult = await page.evaluate(async ({ email, password }) => {
      const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
      const headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-Requested-With': 'XMLHttpRequest',
      }

      if (csrf) {
        headers['X-CSRF-TOKEN'] = csrf
      }

      const body = new URLSearchParams({
        email,
        password,
        remember: 'on',
      })

      const response = await fetch('/login', {
        method: 'POST',
        credentials: 'include',
        headers,
        body,
      })

      return {
        status: response.status,
        ok: response.ok,
        url: response.url,
      }
    }, { email: LOGIN_EMAIL, password: LOGIN_PASSWORD })
    console.log('LOGIN_RESULT:', JSON.stringify(loginResult, null, 2))
    await page.waitForTimeout(1000)

    await page.goto(`${BASE_URL}/setup/wizard`, { waitUntil: 'domcontentloaded' })
    await waitForText(page, 'Мастер настройки системы')

    const greenhouseName = `Теплица автотест ${TS}`
    const zoneName = `Зона автотест ${TS}`
    const plantName = `Культура автотест ${TS}`

    const greenhouseSection = page.locator('section').filter({ hasText: 'Выберите теплицу' }).first()
    await page.locator('[data-test="toggle-greenhouse-create"]').click()
    await page.getByPlaceholder('Название теплицы').fill(greenhouseName)

    const greenhouseTypeSelect = greenhouseSection.locator('select').first()
    const greenhouseTypeCount = await greenhouseTypeSelect.locator('option').count()
    if (greenhouseTypeCount > 1) {
      await greenhouseTypeSelect.selectOption({ index: 1 })
    }

    const createGreenhouseButton = page.getByRole('button', { name: 'Создать теплицу' })
    await ensureButtonEnabled(createGreenhouseButton)
    await Promise.all([
      page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/greenhouses')),
      createGreenhouseButton.click(),
    ])
    await waitForText(page, greenhouseName)

    const greenhouseChoiceText = await greenhouseSection.innerText()
    const greenhouseIdMatch = greenhouseChoiceText.match(/Выбрано:[\s\S]*?\n([\s\S]*?)\n/)
    console.log('GREENHOUSE_SECTION_SNIPPET:', greenhouseChoiceText.slice(0, 800))
    console.log('GREENHOUSE_ID_MATCH:', greenhouseIdMatch?.[1] || 'n/a')

    const zoneSection = page.locator('section').filter({ hasText: 'Выберите зону' }).first()
    await page.locator('[data-test="toggle-zone-create"]').click()
    await page.getByPlaceholder('Название зоны').fill(zoneName)
    await page.getByRole('button', { name: 'Создать зону' }).click()
    await waitForText(page, zoneName)

    const plantSection = page.locator('section').filter({ hasText: 'Рецепт по выбранной культуре' }).first()
    await plantSection.getByRole('button', { name: 'Создать' }).click()
    await page.locator('#plant-name').fill(plantName)
    await page.locator('#plant-species').fill('Lactuca sativa')
    await page.locator('#plant-variety').fill('Autotest')
    await page.locator('#plant-system').selectOption('drip')
    await page.getByRole('button', { name: 'Далее' }).click()
    await page.getByRole('button', { name: 'Создать культуру и рецепт' }).click()
    await waitForText(page, 'Используется рецепт:')

    const pageTextAfterPlant = await page.locator('body').innerText()
    const recipeNameMatch = pageTextAfterPlant.match(/Используется рецепт:\s*([^\n]+)/)
    const recipeName = recipeNameMatch?.[1]?.trim()
    if (!recipeName) {
      throw new Error('Не удалось определить имя созданного рецепта из страницы')
    }
    console.log('RECIPE_NAME:', recipeName)

    const zoneIdLookup = psqlScalar(`select id from zones where name = ${sqlString(zoneName)} order by id desc limit 1;`)
    if (!zoneIdLookup) {
      throw new Error(`Не удалось определить zoneId по имени зоны: ${zoneName}`)
    }
    created.zoneId = Number(zoneIdLookup)

    const plantIdLookup = psqlScalar(`select id from plants where name = ${sqlString(plantName)} order by id desc limit 1;`)
    if (!plantIdLookup) {
      throw new Error(`Не удалось определить plantId по имени культуры: ${plantName}`)
    }
    created.plantId = Number(plantIdLookup)

    const recipeLookup = psqlRows(`
      select
        r.id,
        (
          select rr.id
          from recipe_revisions rr
          where rr.recipe_id = r.id and rr.status = 'PUBLISHED'
          order by rr.revision_number desc
          limit 1
        ) as published_revision_id
      from recipes r
      where r.name = ${sqlString(recipeName)}
      order by r.id desc
      limit 1;
    `)
    const recipeRow = recipeLookup.split('\n').map((line) => line.trim()).find(Boolean)
    if (!recipeRow) {
      throw new Error(`Не удалось определить recipeId по имени культуры: ${plantName}`)
    }
    const [recipeIdValue, revisionIdValue] = recipeRow.split('|')
    created.recipeId = Number(recipeIdValue)
    created.recipeRevisionId = revisionIdValue ? Number(revisionIdValue) : null

    const nodeLookup = psqlRows(`
      select uid, id
      from nodes
      where uid in ('nd-test-irrig-1', 'nd-test-ph-1', 'nd-test-ec-1')
      order by uid
    `)
    const nodeIdsByUid = new Map()
    for (const line of nodeLookup.split('\n').map((item) => item.trim()).filter(Boolean)) {
      const [uid, id] = line.split('|')
      if (uid && id) {
        nodeIdsByUid.set(uid, Number(id))
      }
    }

    const irrigationNodeId = nodeIdsByUid.get('nd-test-irrig-1')
    const phNodeId = nodeIdsByUid.get('nd-test-ph-1')
    const ecNodeId = nodeIdsByUid.get('nd-test-ec-1')
    if (!irrigationNodeId || !phNodeId || !ecNodeId) {
      throw new Error(`Не удалось определить ID реальных нод: ${JSON.stringify(Object.fromEntries(nodeIdsByUid.entries()))}`)
    }

    const nodeStateLookup = psqlRows(`
      select uid, id, coalesce(zone_id::text, '') as zone_id
      from nodes
      where uid in ('nd-test-irrig-1', 'nd-test-ph-1', 'nd-test-ec-1')
      order by uid
    `)
    const nodeStateRows = nodeStateLookup
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const [uid, id, zoneId] = line.split('|')
        return {
          uid,
          id: Number(id),
          zoneId: zoneId ? Number(zoneId) : null,
        }
      })
    console.log('NODE_STATES_BEFORE_DETACH:', JSON.stringify(nodeStateRows, null, 2))

    const nodesToDetach = nodeStateRows.filter((node) => Number.isFinite(node.zoneId) || node.zoneId !== null)
    if (nodesToDetach.length > 0) {
      const detachResult = await page.evaluate(async ({ nodes }) => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        }

        if (csrf) {
          headers['X-CSRF-TOKEN'] = csrf
        }

        const results = []
        for (const node of nodes) {
          const response = await fetch(`/api/nodes/${node.id}/detach`, {
            method: 'POST',
            credentials: 'include',
            headers,
          })
          results.push({
            node_id: node.id,
            node_uid: node.uid,
            status: response.status,
            ok: response.ok,
            body: await response.json().catch(() => null),
          })
        }

        return results
      }, { nodes: nodesToDetach })
      console.log('DETACH_RESULT:', JSON.stringify(detachResult, null, 2))
    }

    const bindingResult = await page.evaluate(async ({ zoneId, irrigationNodeId, phNodeId, ecNodeId }) => {
      const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
      const headers = {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      }

      if (csrf) {
        headers['X-CSRF-TOKEN'] = csrf
      }

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

      const validateResponse = await fetch('/api/setup-wizard/validate-devices', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify(payload),
      })

      const validateJson = await validateResponse.json().catch(() => null)

      const applyResponse = await fetch('/api/setup-wizard/apply-device-bindings', {
        method: 'POST',
        credentials: 'include',
        headers,
        body: JSON.stringify(payload),
      })

      const applyJson = await applyResponse.json().catch(() => null)

      return {
        validateStatus: validateResponse.status,
        validateJson,
        applyStatus: applyResponse.status,
        applyJson,
      }
    }, { zoneId: created.zoneId, irrigationNodeId, phNodeId, ecNodeId })
    console.log('BINDING_RESULT:', JSON.stringify(bindingResult, null, 2))

    await page.getByRole('button', { name: 'Обновить ноды' }).click()
    await page.waitForResponse((response) => response.request().method() === 'GET' && response.url().includes('/api/nodes'))
    await waitForNodeOptions(page, ['Узел полива', 'Узел коррекции pH', 'Узел коррекции EC'])

    const bindingOptions = await page.evaluate(() => {
      const labels = ['Узел полива', 'Узел коррекции pH', 'Узел коррекции EC']
      const result = {}

      for (const label of labels) {
        const labelEl = Array.from(document.querySelectorAll('label')).find((el) =>
          (el.textContent || '').includes(label)
        )
        const select = labelEl ? labelEl.querySelector('select') : null
        result[label] = select
          ? Array.from(select.options).map((option) => ({
            text: option.textContent || '',
            value: option.value,
            selected: option.selected,
          }))
          : []
      }

      return result
    })
    console.log('BINDING_OPTIONS_AFTER_API:', JSON.stringify(bindingOptions, null, 2))

    await selectByLabel(page, 'Узел полива', irrigationNodeId)
    await selectByLabel(page, 'Узел коррекции pH', phNodeId)
    await selectByLabel(page, 'Узел коррекции EC', ecNodeId)
    await page.waitForTimeout(500)

    const saveWaterContourButton = page.locator('[data-test="save-section-water-contour"]')
    await ensureButtonEnabled(saveWaterContourButton)
    await saveWaterContourButton.click()
    await page.waitForTimeout(1500)

    const healthBeforeCalibration = await page.evaluate(async (zoneId) => {
      const response = await fetch(`/api/zones/${zoneId}/health`)
      return response.json()
    }, created.zoneId)
    console.log('HEALTH_AFTER_AUTOMATION:', JSON.stringify(healthBeforeCalibration, null, 2))

    if (healthBeforeCalibration?.data?.readiness?.dispatch_enabled === false) {
      const runtimeSettingsResult = await page.evaluate(async () => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        }

        if (csrf) {
          headers['X-CSRF-TOKEN'] = csrf
        }

        const response = await fetch('/api/automation-configs/system/0/system.runtime', {
          method: 'PUT',
          credentials: 'include',
          headers,
          body: JSON.stringify({
            payload: {
              'automation_engine.grow_cycle_start_dispatch_enabled': true,
            },
          }),
        })

        return {
          status: response.status,
          ok: response.ok,
          body: await response.json().catch(() => null),
        }
      })
      console.log('RUNTIME_SETTINGS_RESULT:', JSON.stringify(runtimeSettingsResult, null, 2))
      await page.waitForTimeout(1000)
      const healthAfterRuntimeSettings = await page.evaluate(async (zoneId) => {
        const response = await fetch(`/api/zones/${zoneId}/health`)
        return response.json()
      }, created.zoneId)
      console.log('HEALTH_AFTER_RUNTIME_SETTINGS:', JSON.stringify(healthAfterRuntimeSettings, null, 2))
    }

    const pidConfigs = {
      ph: {
        dead_zone: 0.05,
        close_zone: 0.3,
        far_zone: 1.0,
        zone_coeffs: {
          close: { kp: 5.0, ki: 0.05, kd: 0.0 },
          far: { kp: 8.0, ki: 0.02, kd: 0.0 },
        },
        max_integral: 20.0,
      },
      ec: {
        dead_zone: 0.1,
        close_zone: 0.5,
        far_zone: 1.5,
        zone_coeffs: {
          close: { kp: 30.0, ki: 0.3, kd: 0.0 },
          far: { kp: 50.0, ki: 0.1, kd: 0.0 },
        },
        max_integral: 100.0,
      },
    }

    const pidNamespaces = {
      ph: 'zone.pid.ph',
      ec: 'zone.pid.ec',
    }

    for (const [type, config] of Object.entries(pidConfigs)) {
      const pidResult = await page.evaluate(async ({ zoneId, namespace, configPayload }) => {
        const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || ''
        const headers = {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        }

        if (csrf) {
          headers['X-CSRF-TOKEN'] = csrf
        }

        const response = await fetch(`/api/automation-configs/zone/${zoneId}/${namespace}`, {
          method: 'PUT',
          credentials: 'include',
          headers,
          body: JSON.stringify({ payload: configPayload }),
        })

        return {
          status: response.status,
          ok: response.ok,
          body: await response.json().catch(() => null),
        }
      }, { zoneId: created.zoneId, namespace: pidNamespaces[type], configPayload: config })
      console.log(`PID_SAVE_${type.toUpperCase()}:`, JSON.stringify(pidResult, null, 2))
    }
    await page.waitForTimeout(1000)

    const processPanel = page.locator('.process-calibration-panel').first()
    await processPanel.getByRole('button', { name: 'Сохранить Наполнение' }).click()
    await waitForText(page, 'Калибровка процесса для режима', 30000).catch(() => null)

    const pumpOpenButtons = page.getByRole('button', { name: 'Открыть визард' })
    await pumpOpenButtons.first().click()
    await waitForText(page, 'Калибровка дозирующих насосов')

    const pumpModal = page.locator('.pump-calibration-modal')
    const pumpPairs = [
      { component: 'ph_down', channel: '19' },
      { component: 'ph_up', channel: '20' },
      { component: 'npk', channel: '23' },
      { component: 'calcium', channel: '24' },
      { component: 'magnesium', channel: '25' },
      { component: 'micro', channel: '26' },
    ]

    for (const pair of pumpPairs) {
      await pumpModal.getByTestId('pump-calibration-component').selectOption(pair.component)
      await pumpModal.getByTestId('pump-calibration-channel').selectOption(pair.channel)
      await pumpModal.getByTestId('pump-calibration-duration').fill('20')
      await pumpModal.getByTestId('pump-calibration-actual-ml').fill('20')
      await pumpModal.getByTestId('pump-calibration-save-btn').click()
      await page.waitForTimeout(750)
    }

    const healthAfterCalibration = await page.evaluate(async (zoneId) => {
      const response = await fetch(`/api/zones/${zoneId}/health`)
      return response.json()
    }, created.zoneId)
    console.log('HEALTH_AFTER_CALIBRATION:', JSON.stringify(healthAfterCalibration, null, 2))

    const openLaunchButton = page.getByRole('button', { name: 'Открыть мастер запуска цикла' })
    await ensureButtonEnabled(openLaunchButton)
    const launchNow = new Date()
    const launchOffsetMs = launchNow.getTimezoneOffset() * 60_000
    const startedAtLocal = new Date(launchNow.getTime() - launchOffsetMs).toISOString().slice(0, 16)
    const launchQuery = new URLSearchParams({
      start_cycle: '1',
      source: 'setup_wizard',
      recipe_id: String(created.recipeId ?? ''),
      recipe_revision_id: String(created.recipeRevisionId ?? ''),
      plant_id: String(created.plantId ?? ''),
      started_at: startedAtLocal,
    })
    const launchUrl = `${BASE_URL}/zones/${created.zoneId}?${launchQuery.toString()}`
    try {
      await Promise.all([
        page.waitForURL(/\/zones\/\d+/),
        openLaunchButton.click(),
      ])
    } catch {
      await page.goto(launchUrl, { waitUntil: 'domcontentloaded' })
    }
    await waitForText(page, 'Запуск нового цикла выращивания')

    await page.waitForTimeout(2000)

    for (let i = 0; i < 3; i += 1) {
      const nextButton = page.getByRole('button', { name: 'Далее' })
      const visible = await nextButton.isVisible().catch(() => false)
      if (!visible) {
        break
      }
      const disabled = await nextButton.isDisabled().catch(() => true)
      if (disabled) {
        break
      }
      await nextButton.click()
      await page.waitForTimeout(1000)
    }

    const submitButton = page.getByRole('button', { name: 'Запустить цикл' })
    await ensureButtonEnabled(submitButton, 45000)
    await submitButton.click()

    let createdCycleRow = ''
    for (let attempt = 0; attempt < 48; attempt += 1) {
      createdCycleRow = psqlRows(`
        select id, zone_id, recipe_revision_id, plant_id, status, started_at, created_at
        from grow_cycles
        where zone_id = ${created.zoneId}
        order by id desc
        limit 1;
      `).trim()
      if (createdCycleRow) {
        break
      }
      await page.waitForTimeout(5000)
    }

    if (!createdCycleRow) {
      throw new Error(`Цикл выращивания не появился в БД для зоны ${created.zoneId}`)
    }
    console.log('GROW_CYCLE_ROW:', createdCycleRow)
    await page.waitForTimeout(2000)

    const finalUrl = page.url()
    console.log('FINAL_URL:', finalUrl)

    const zoneId = created.zoneId
    const report = {
      greenhouses: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', 'select id, uid, name, created_at from greenhouses order by id desc limit 3;']),
      zones: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', 'select id, uid, name, greenhouse_id, status, created_at from zones order by id desc limit 3;']),
      plants: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', 'select id, name, created_at from plants order by id desc limit 3;']),
      recipes: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', 'select id, name, plant_id, latest_published_revision_id from recipes order by id desc limit 3;']),
      nodeBindings: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', `select cb.id, cb.role, n.id as node_id, n.uid, nc.channel from channel_bindings cb join node_channels nc on nc.id = cb.node_channel_id join nodes n on n.id = nc.node_id where cb.infrastructure_instance_id in (select id from infrastructure_instances where owner_type = 'zone' and owner_id = ${zoneId}) order by cb.id;`]),
      pidConfigs: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', `select id, zone_id, type, created_at from zone_pid_configs where zone_id = ${zoneId} order by type;`]),
      pumpCalibrations: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', `select pc.id, pc.node_channel_id, pc.component, pc.ml_per_sec, pc.is_active, pc.valid_from from pump_calibrations pc join node_channels nc on nc.id = pc.node_channel_id join nodes n on n.id = nc.node_id where nc.node_id in (1,2,3) order by pc.id desc limit 20;`]),
      processCalibrations: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', `select id, zone_id, mode, transport_delay_sec, settle_sec, ec_gain_per_ml, confidence, updated_at from zone_process_calibrations where zone_id = ${zoneId} order by id desc;`]),
      alerts: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', `select id, zone_id, code, status, severity, created_at, last_seen_at from alerts order by id desc limit 10;`]),
      cycles: run('docker', ['exec', 'backend-db-1', 'psql', '-U', 'hydro', '-d', 'hydro_dev', '-c', `select id, zone_id, recipe_revision_id, plant_id, status, started_at, created_at from grow_cycles where zone_id = ${zoneId} order by id desc limit 5;`]),
    }

    console.log('DB_REPORT_START')
    for (const [key, value] of Object.entries(report)) {
      console.log(`--- ${key} ---`)
      process.stdout.write(value)
    }
    console.log('DB_REPORT_END')

    console.log('AUTOMATION_HEALTH_FINAL:', JSON.stringify(await page.evaluate(async (id) => {
      const response = await fetch(`/api/zones/${id}/health`)
      return response.json()
    }, zoneId), null, 2))
  } catch (error) {
    console.error('SCRIPT_ERROR:', error)
    console.error('PAGE_URL:', page.url())
    console.error('PAGE_TEXT_HEAD:', (await page.locator('body').innerText().catch(() => '')).slice(0, 3000))
    process.exitCode = 1
  } finally {
    await browser.close()
  }
}

await main()
