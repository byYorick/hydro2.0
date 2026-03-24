const { chromium } = require('playwright')

const BASE_URL = 'http://localhost:8080'
const EMAIL = 'agronomist@example.com'
const PASSWORD = 'password'
const TARGET_ZONE_NAME = 'Zone Launch 2026-03-23T16-02-54-961Z'

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, '-')
}

async function login(page) {
  await page.goto('/login', { waitUntil: 'domcontentloaded' })
  await page.locator('#email').fill(EMAIL)
  await page.locator('#password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Войти в систему' }).click()
  await page.waitForTimeout(1200)
}

async function openWizard(page) {
  await page.goto('/setup/wizard', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
}

async function selectFirstRealOption(selectLocator) {
  const count = await selectLocator.locator('option').count()
  if (count <= 1) {
    throw new Error('No selectable options found')
  }
  await selectLocator.selectOption({ index: 1 })
}

async function waitForOptionCount(selectLocator, minCount = 2, timeoutMs = 10000) {
  const page = selectLocator.page()
  const startedAt = Date.now()

  while (Date.now() - startedAt < timeoutMs) {
    const count = await selectLocator.locator('option').count()
    if (count >= minCount) {
      return count
    }
    await page.waitForTimeout(250)
  }

  return selectLocator.locator('option').count()
}

async function selectOptionByTextFragment(selectLocator, fragment) {
  const options = await selectLocator.locator('option').evaluateAll((items) =>
    items.map((item) => ({
      value: item.value,
      text: item.textContent ? item.textContent.trim() : '',
    })),
  )
  const option = options.find((item) => item.value && item.text.toLowerCase().includes(fragment.toLowerCase()))
  if (!option) {
    throw new Error(`Option containing "${fragment}" not found`)
  }
  await selectLocator.selectOption(option.value)
}

async function createOrSelectGreenhouse(page, greenhouseName) {
  const greenhouseSection = page.locator('section').filter({ has: page.getByRole('heading', { name: '1. Теплица' }) })
  const greenhouseTypeSelect = greenhouseSection.locator('select').first()
  await waitForOptionCount(greenhouseTypeSelect, 2, 10000)
  if (await greenhouseTypeSelect.locator('option').count() > 1) {
    await selectFirstRealOption(greenhouseTypeSelect)
    return
  }

  await greenhouseSection.locator('button[data-test="toggle-greenhouse-create"]').click()
  await greenhouseSection.locator('input[placeholder="Название теплицы"]').fill(greenhouseName)
  await selectFirstRealOption(greenhouseTypeSelect)
  await greenhouseSection.getByRole('button', { name: 'Создать теплицу' }).click()
  await page.waitForTimeout(1500)
}

async function createOrSelectZone(page, zoneName) {
  const zoneSection = page.locator('section').filter({ has: page.getByRole('heading', { name: '2. Зона' }) })
  const zoneSelect = zoneSection.locator('select').first()
  await waitForOptionCount(zoneSelect, 2, 10000)
  if (await zoneSelect.locator('option').count() > 1) {
    const options = await zoneSelect.locator('option').evaluateAll((items) =>
      items.map((item) => ({
        value: item.value,
        text: item.textContent ? item.textContent.trim() : '',
      })),
    )
    const target = options.find((item) => item.text.toLowerCase().includes(TARGET_ZONE_NAME.toLowerCase()))
    if (target) {
      await zoneSelect.selectOption(target.value)
    } else {
      await selectFirstRealOption(zoneSelect)
    }
    return
  }

  await zoneSection.locator('button[data-test="toggle-zone-create"]').click()
  await zoneSection.locator('input[placeholder="Название зоны"]').fill(zoneName)
  await zoneSection.locator('input[placeholder="Описание зоны"]').fill('Front launch zone')
  await zoneSection.getByRole('button', { name: 'Создать зону' }).click()
  await page.waitForTimeout(1500)
}

async function createPlant(page, plantName) {
  const plantSection = page.locator('section').filter({ has: page.getByRole('heading', { name: '3. Культура и рецепт' }) })
  const plantSelect = plantSection.locator('select').first()
  await waitForOptionCount(plantSelect, 2, 10000)
  if (await plantSelect.locator('option').count() > 1) {
    await selectFirstRealOption(plantSelect)
    return
  }

  await plantSection.getByRole('button', { name: 'Создать' }).click()
  await page.waitForSelector('#plant-name', { state: 'visible', timeout: 10000 })

  const plantNameInput = page.locator('#plant-name')
  await plantNameInput.fill(plantName)

  const systemSelect = page.locator('#plant-system')
  await waitForOptionCount(systemSelect, 2, 15000)
  await selectFirstRealOption(systemSelect)

  const substrateSelect = page.locator('#plant-substrate')
  if (await substrateSelect.count()) {
    const substrateOptions = await substrateSelect.locator('option').evaluateAll((items) =>
      items.map((item) => ({
        value: item.value,
        text: item.textContent ? item.textContent.trim() : '',
      })),
    )
    const substrateOption = substrateOptions.find((item) => item.value)
    if (substrateOption) {
      await substrateSelect.selectOption(substrateOption.value)
    }
  }

  await page.getByRole('button', { name: 'Далее' }).click()
  await page.waitForTimeout(600)
  await page.getByRole('button', { name: 'Создать культуру и рецепт' }).click()
  await page.waitForTimeout(2500)
}

async function selectExistingPlant(page) {
  const plantSection = page.locator('section').filter({ has: page.getByRole('heading', { name: '3. Культура и рецепт' }) })
  const select = plantSection.locator('select').first()
  await selectFirstRealOption(select)
  await page.waitForTimeout(1000)
}

async function saveZoneWaterContour(page) {
  const waterSection = page.locator('section').filter({ has: page.getByRole('heading', { name: '4. Автоматика зоны' }) })
  await selectOptionByTextFragment(waterSection.getByLabel('Узел полива'), 'Test: irrigation')
  await selectOptionByTextFragment(waterSection.getByLabel('Узел коррекции pH'), 'Test: pH correction')
  await selectOptionByTextFragment(waterSection.getByLabel('Узел коррекции EC'), 'Test: EC correction')
  await waterSection.locator('[data-test="save-section-water-contour"]').click()
  await page.waitForTimeout(2000)
}

async function calibratePump(page, component, channelFragment, actualMl = 10) {
  const modal = page.locator('[role="dialog"]').filter({ hasText: 'Калибровка дозирующих насосов' })
  if (await modal.count() === 0) {
    const openButtons = page.getByRole('button', { name: 'Открыть визард' })
    if (await openButtons.count()) {
      await openButtons.first().click()
    } else {
      throw new Error('Pump calibration wizard button not found')
    }
  }

  await page.waitForTimeout(700)
  await modal.locator('[data-testid="pump-calibration-component"]').selectOption(component)
  const channelSelect = modal.locator('[data-testid="pump-calibration-channel"]')
  await selectOptionByTextFragment(channelSelect, channelFragment)
  await modal.locator('[data-testid="pump-calibration-duration"]').fill('10')
  await modal.locator('[data-testid="pump-calibration-actual-ml"]').fill(String(actualMl))
  await modal.locator('[data-testid="pump-calibration-save-btn"]').click()
  await page.waitForTimeout(1400)
}

async function savePumpCalibrations(page) {
  const components = [
    { component: 'ph_up', channel: 'pump_base' },
    { component: 'ph_down', channel: 'pump_acid' },
    { component: 'npk', channel: 'pump_a' },
    { component: 'calcium', channel: 'pump_b' },
    { component: 'magnesium', channel: 'pump_c' },
    { component: 'micro', channel: 'pump_d' },
  ]

  for (const item of components) {
    await calibratePump(page, item.component, item.channel, 10)
  }
}

async function savePidConfigs(page) {
  const calibrationSection = page.locator('section').filter({ has: page.getByRole('heading', { name: '5. Калибровка' }) })
  const pidDetails = calibrationSection.locator('details').filter({ hasText: 'Расширенная тонкая настройка PID и autotune' })
  await pidDetails.locator('summary').click()
  await page.waitForTimeout(600)

  const pidForm = page.locator('#zone-pid-config-panel-shared')
  const saveButton = pidForm.getByRole('button', { name: 'Сохранить' })
  await pidForm.getByRole('button', { name: 'pH' }).click()
  await page.waitForTimeout(400)
  await saveButton.click()
  await page.waitForTimeout(1600)
  await pidForm.getByRole('button', { name: 'EC' }).click()
  await page.waitForTimeout(400)
  await saveButton.click()
  await page.waitForTimeout(1600)
}

async function saveProcessCalibrations(page) {
  const processPanel = page.locator('.process-calibration-panel')
  const buttons = [
    'Наполнение',
    'Рециркуляция',
    'Полив',
    'Generic',
  ]

  for (const modeLabel of buttons) {
    await processPanel.getByRole('button', { name: modeLabel }).click()
    await page.waitForTimeout(400)
    await processPanel.getByRole('button', { name: /Сохранить/ }).click()
    await page.waitForTimeout(1400)
  }
}

async function launchCycle(page) {
  const launchSection = page.locator('section').filter({ has: page.getByRole('heading', { name: '6. Проверка и запуск' }) })
  await launchSection.getByRole('button', { name: 'Открыть мастер запуска цикла' }).click()
  await page.waitForTimeout(2000)

  const url = page.url()
  if (!url.includes('/zones/')) {
    throw new Error(`Expected to navigate to zone page, got ${url}`)
  }

  const wizard = page.locator('body')
  await page.waitForTimeout(3000)

  const buttons = page.getByRole('button', { name: 'Запустить цикл' })
  if (await buttons.count()) {
    await buttons.first().click()
    await page.waitForTimeout(3000)
  } else {
    throw new Error('Launch button not found in growth cycle wizard')
  }
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/snap/bin/chromium',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })

  const context = await browser.newContext({ baseURL: BASE_URL })
  const page = await context.newPage()

  const greenhouseName = `GH Launch ${stamp()}`
  const zoneName = `Zone Launch ${stamp()}`
  const plantName = `Tomato Launch ${stamp()}`

  await login(page)
  await openWizard(page)

  await createOrSelectGreenhouse(page, greenhouseName)
  await createOrSelectZone(page, zoneName)

  // If the greenhouse/zone already existed from a prior attempt, we still create
  // the plant here and then re-select the newly created entries.
  await createPlant(page, plantName)
  await selectExistingPlant(page)

  await saveZoneWaterContour(page)
  await savePumpCalibrations(page)
  await savePidConfigs(page)
  await saveProcessCalibrations(page)
  await launchCycle(page)

  console.log('DONE')
  console.log('URL', page.url())
  console.log('TITLE', await page.title())
  console.log((await page.locator('body').innerText()).slice(0, 3000))

  await browser.close()
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
