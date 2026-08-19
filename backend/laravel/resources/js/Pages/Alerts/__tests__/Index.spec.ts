import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))
vi.mock('@/Components/Button.vue', () => ({
  default: { name: 'Button', template: '<button><slot /></button>' },
}))
vi.mock('@/Components/Modal.vue', () => ({
  default: { name: 'Modal', props: ['open'], template: '<div v-if="open"><slot /><slot name="footer" /></div>' },
}))

const itemsDataValue = vi.hoisted(() => [
  {
    id: 1,
    type: 'AE3_TASK_FAILED',
    code: 'biz_ae3_task_failed',
    severity: 'error',
    zone: { id: 1, name: 'Zone A1' },
    zone_id: 1,
    created_at: '2025-01-01T10:00:00Z',
    status: 'active',
    details: {
      task_id: 'ae-task-101',
      correction_window_id: 'task:101:irrigating:irrigation_check',
      error_code: 'ae3_task_failed',
      stage: 'waiting_command',
    },
  },
  {
    id: 2,
    type: 'EC_LOW',
    code: 'biz_ec_low',
    severity: 'warning',
    zone: { id: 2, name: 'Zone B2' },
    zone_id: 2,
    created_at: '2025-01-01T11:00:00Z',
    status: 'resolved',
  },
  {
    id: 3,
    type: 'TEMP_HIGH',
    code: 'biz_temp_high',
    severity: 'warning',
    zone: { id: 1, name: 'Zone A1' },
    zone_id: 1,
    created_at: '2025-01-01T12:00:00Z',
    status: 'active',
  },
  {
    id: 4,
    type: 'NO_FLOW',
    code: 'biz_no_flow',
    severity: 'critical',
    zone: { id: 2, name: 'Zone B2' },
    zone_id: 2,
    created_at: '2025-01-01T09:00:00Z',
    status: 'active',
    details: {
      correction_window_id: 'task:101:irrigating:irrigation_check',
    },
  },
])

const resetItemsData = () => {
  const fresh = [
    {
      id: 1,
      type: 'AE3_TASK_FAILED',
      code: 'biz_ae3_task_failed',
      severity: 'error',
      zone: { id: 1, name: 'Zone A1' },
      zone_id: 1,
      created_at: '2025-01-01T10:00:00Z',
      status: 'active',
      details: {
        task_id: 'ae-task-101',
        correction_window_id: 'task:101:irrigating:irrigation_check',
        error_code: 'ae3_task_failed',
        stage: 'waiting_command',
      },
    },
    {
      id: 2,
      type: 'EC_LOW',
      code: 'biz_ec_low',
      severity: 'warning',
      zone: { id: 2, name: 'Zone B2' },
      zone_id: 2,
      created_at: '2025-01-01T11:00:00Z',
      status: 'resolved',
    },
    {
      id: 3,
      type: 'TEMP_HIGH',
      code: 'biz_temp_high',
      severity: 'warning',
      zone: { id: 1, name: 'Zone A1' },
      zone_id: 1,
      created_at: '2025-01-01T12:00:00Z',
      status: 'active',
    },
    {
      id: 4,
      type: 'NO_FLOW',
      code: 'biz_no_flow',
      severity: 'critical',
      zone: { id: 2, name: 'Zone B2' },
      zone_id: 2,
      created_at: '2025-01-01T09:00:00Z',
      status: 'active',
      details: {
        correction_window_id: 'task:101:irrigating:irrigation_check',
      },
    },
  ]
  itemsDataValue.splice(0, itemsDataValue.length, ...fresh)
}

const currentUserRole = vi.hoisted(() => ({ value: undefined as string | undefined }))
const axiosGetMock = vi.hoisted(() => vi.fn())
const axiosPatchMock = vi.hoisted(() => vi.fn())
const routerReloadMock = vi.hoisted(() => vi.fn())
const subscribeManagedChannelEventsMock = vi.hoisted(() => vi.fn(() => vi.fn()))

vi.mock('axios', () => {
  const axiosInstance = {
    get: (...args: Parameters<typeof axiosGetMock>) => axiosGetMock(...args),
    patch: (url: string, data?: any, config?: any) => axiosPatchMock(url, data, config),
    interceptors: {
      request: {
        use: vi.fn(),
        eject: vi.fn(),
      },
      response: {
        use: vi.fn(),
        eject: vi.fn(),
      },
  },
  }

  return {
    default: {
      ...axiosInstance,
      create: () => axiosInstance,
    },
  }
})

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: currentUserRole.value
        ? { user: { role: currentUserRole.value } }
        : {},
      alerts: itemsDataValue,
      zones: [
        { id: 1, name: 'Zone A1' },
        { id: 2, name: 'Zone B2' },
      ],
    },
  }),
  router: {
    reload: routerReloadMock,
  },
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

vi.mock('@/ws/managedChannelEvents', () => ({
  subscribeManagedChannelEvents: (...args: Parameters<typeof subscribeManagedChannelEventsMock>) => subscribeManagedChannelEventsMock(...args),
}))

import AlertsIndex from '../Index.vue'
import { config } from '@vue/test-utils'

config.global.components.RecycleScroller = {
  name: 'RecycleScroller',
  props: ['items', 'itemSize', 'keyField'],
  template: `
    <div>
      <slot
        v-for="(item, index) in items"
        :item="item"
        :index="index"
      />
    </div>
  `,
}

describe('Alerts/Index.vue', () => {
  const mountWithPinia = () => mount(AlertsIndex, {
    global: {
      plugins: [createPinia()],
    },
  })

  beforeEach(() => {
    currentUserRole.value = undefined
    setActivePinia(createPinia())
    window.history.replaceState({}, '', '/alerts')
    resetItemsData()
    axiosGetMock.mockReset()
    axiosPatchMock.mockClear()
    routerReloadMock.mockClear()
    subscribeManagedChannelEventsMock.mockClear()
    axiosGetMock.mockResolvedValue({ data: { data: itemsDataValue } })
    axiosPatchMock.mockImplementation((url: string) => {
      const id = Number(String(url).match(/\/alerts\/(\d+)\/ack/)?.[1])
      const source = itemsDataValue.find((item) => item.id === id)
      return Promise.resolve({
        data: {
          data: {
            ...source,
            status: 'resolved',
            resolved_at: '2025-01-01T13:00:00Z',
          },
        },
      })
    })
  })

  const findRows = (wrapper: ReturnType<typeof mount>) => wrapper.findAll('[data-testid^="alert-row-"]')

  it('фильтрует только активные', async () => {
    const wrapper = mountWithPinia()
    // onlyActive=true по умолчанию -> исключает resolved
    await wrapper.vm.$nextTick()
    const rows = findRows(wrapper)
    expect(rows.length).toBeGreaterThan(0)
    rows.forEach(r => expect(r.text()).not.toContain('Решено'))
  })

  it('фильтрует по зоне', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()
    const select = wrapper.find('select[data-testid="alerts-filter-zone"]')
    await select.setValue('1')
    await wrapper.vm.$nextTick()
    const rows = findRows(wrapper)
    expect(rows.length).toBeGreaterThanOrEqual(1)
    rows.forEach(r => expect(r.text()).toMatch(/A1/))
  })

  it('группирует active алерты и показывает severity/process-stopping бейджи', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="alerts-section-automation_block"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alerts-section-safety"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alerts-section-other_active"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Блокируют автоматику')
    expect(wrapper.text()).toContain('Останавливают железо')
    expect(wrapper.text()).toContain('Критичность')
    expect(wrapper.text()).toContain('Критическая')
    expect(wrapper.text()).toContain('Автоматика')
    expect(wrapper.text()).toContain('Железо')
  })

  it('локализует заголовок и фильтры источника/критичности, сохраняя machine values', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Тревоги')
    expect(wrapper.text()).toContain('Отклонения по зонам и статус решения.')
    expect(wrapper.text()).toContain('Скрытие повторов, сек')

    const sourceOptions = wrapper.get('[data-testid="alerts-filter-source"]').findAll('option')
    expect(sourceOptions.map((option) => option.attributes('value'))).toEqual(['', 'biz', 'infra', 'node'])
    expect(sourceOptions.map((option) => option.text().trim())).toEqual([
      'Все',
      'Процесс',
      'Инфраструктура',
      'Узел',
    ])

    const severityOptions = wrapper.get('[data-testid="alerts-filter-severity"]').findAll('option')
    expect(severityOptions.map((option) => option.attributes('value'))).toEqual([
      '',
      'critical',
      'error',
      'warning',
      'info',
    ])
    expect(severityOptions.map((option) => option.text().trim())).toEqual([
      'Все',
      'Критическая',
      'Ошибка',
      'Предупреждение',
      'Информация',
    ])
  })

  it('фильтрует алерты, которые останавливают процесс', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    const processToggle = wrapper.get('[data-testid="alerts-filter-process-stopping"]')
    await processToggle.trigger('click')
    await wrapper.vm.$nextTick()

    const rows = findRows(wrapper)
    expect(rows).toHaveLength(2)
    expect(wrapper.text()).toContain('biz_ae3_task_failed')
    expect(wrapper.text()).toContain('biz_no_flow')
    expect(wrapper.text()).not.toContain('biz_temp_high')
  })

  it('показывает process-stopping kind в drawer деталей', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    await wrapper.get('[data-testid="alert-row-1"]').trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.get('[data-testid="alert-details-process-stop"]').text()).toContain('Стоп: Автоматика')
  })

  it('рендерит deep-link на зону в таблице и drawer', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    const zoneLink = wrapper.get('[data-testid="alert-zone-link-1"]')
    expect(zoneLink.attributes('href')).toBe('/zones/1?tab=alerts')
    expect(zoneLink.text()).toContain('Zone A1')

    await wrapper.get('[data-testid="alert-row-1"]').trigger('click')
    await wrapper.vm.$nextTick()

    const openZoneBtn = wrapper.get('[data-testid="alert-open-zone-btn"]')
    expect(openZoneBtn.attributes('href')).toBe('/zones/1?tab=alerts')
    expect(openZoneBtn.text()).toContain('Открыть зону')
  })

  it('показывает task_id из details в drawer деталей', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    await wrapper.get('[data-testid="alert-row-1"]').trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('задача')
    expect(wrapper.get('[data-testid="alert-details-task-id"]').text()).toBe('ae-task-101')
    expect(wrapper.text()).toContain('error: ae3_task_failed · stage: waiting_command')
  })

  it('подтверждение алерта вызывает API', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()
    
    // Эмулируем выбор алерта и подтверждение напрямую через метод
    // чтобы избежать сложной работы со слотами виртуализатора
    // @ts-ignore accessing component instance internals for testing
    wrapper.vm.confirm = { open: true, alertId: itemsDataValue[0].id, loading: false }

    // @ts-ignore
    await wrapper.vm.doResolve()
    await new Promise(resolve => setTimeout(resolve, 10))
            
    expect(axiosPatchMock).toHaveBeenCalled()
  })

  it('глобальный select-all в FilterBar без чекбокса в header секций', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    const globalSelectAll = wrapper.find('[data-testid="alerts-select-all"] input[type="checkbox"]')
    expect(globalSelectAll.exists()).toBe(true)

    for (const sectionKey of ['automation_block', 'safety', 'other_active']) {
      const section = wrapper.find(`[data-testid="alerts-section-${sectionKey}"]`)
      expect(section.find('thead input[type="checkbox"]').exists()).toBe(false)
    }

    const rowCheckboxes = wrapper.findAll('tbody input[type="checkbox"]')
    expect(rowCheckboxes).toHaveLength(3)
  })

  it('глобальный select-all выбирает и снимает все видимые активные алерты', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    const rowCheckboxes = wrapper.findAll('tbody input[type="checkbox"]:not(:disabled)')
    const expectedCount = rowCheckboxes.length
    const globalSelectAll = wrapper.find('[data-testid="alerts-select-all"] input[type="checkbox"]')

    await globalSelectAll.setValue(true)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain(`Выбрано: ${expectedCount}`)
    rowCheckboxes.forEach((checkbox) => {
      expect((checkbox.element as HTMLInputElement).checked).toBe(true)
    })

    await globalSelectAll.setValue(false)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).not.toContain('Выбрано:')
    rowCheckboxes.forEach((checkbox) => {
      expect((checkbox.element as HTMLInputElement).checked).toBe(false)
    })
  })

  it('показывает счётчики активных секций в видимом наборе', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="alerts-section-counts"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="alerts-count-automation-block"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="alerts-count-safety"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="alerts-count-other"]').text()).toContain('1')
    expect(wrapper.get('[data-testid="alerts-count-active-total"]').text()).toContain('3')
    expect(wrapper.get('[data-testid="alerts-count-automation-block"]').text()).toContain('Блокируют автоматику')
    expect(wrapper.get('[data-testid="alerts-count-safety"]').text()).toContain('Останавливают железо')
    expect(wrapper.get('[data-testid="alerts-count-other"]').text()).toContain('Остальные активные')
  })

  it('показывает подгруппы по зоне внутри active секций', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="alerts-zone-group-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alerts-zone-group-2"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="alerts-zone-group-1"]').text()).toContain('Zone A1')
    expect(wrapper.get('[data-testid="alerts-zone-group-2"]').text()).toContain('Zone B2')
  })

  it('показывает safety process-stopping badge и correction window в drawer', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    await wrapper.get('[data-testid="alert-row-4"]').trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.get('[data-testid="alert-details-process-stop"]').text()).toContain('Стоп: Железо')
    expect(wrapper.get('[data-testid="alert-details-correction-window-id"]').text())
      .toBe('task:101:irrigating:irrigation_check')

    // @ts-expect-error test access
    wrapper.vm.closeDetails()
    await wrapper.vm.$nextTick()

    await wrapper.get('[data-testid="alert-row-1"]').trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.get('[data-testid="alert-details-task-id"]').text()).toBe('ae-task-101')
  })

  it('показывает resolved секцию при фильтре «Все»', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    await wrapper.get('[data-testid="alerts-filter-active"]').setValue('all')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="alerts-section-resolved"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="alerts-section-resolved"]').text()).toContain('Решённые')
    expect(wrapper.get('[data-testid="alert-row-2"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alerts-count-active-total"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="alerts-count-active-total"]').text()).toContain('3')
  })

  it('использует «Отметить как решённый» вместо «Подтвердить»', async () => {
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    const resolveBtn = wrapper.get('[data-testid="alert-resolve-btn-1"]')
    expect(resolveBtn.text()).toContain('Отметить как решённый')
    expect(resolveBtn.text()).not.toContain('Подтвердить')

    const globalSelectAll = wrapper.find('[data-testid="alerts-select-all"] input[type="checkbox"]')
    await globalSelectAll.setValue(true)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Отметить выбранные как решённые')
    expect(wrapper.text()).not.toContain('Подтвердить выбранные')
  })

  it('у operator прячет source/category/suppression в дополнительные фильтры', async () => {
    currentUserRole.value = 'operator'
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="alerts-extra-filters-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alerts-filter-process-stopping"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alerts-filter-source"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="alerts-filter-category"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="alerts-filter-suppression"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="alerts-extra-filters"]').exists()).toBe(false)

    await wrapper.get('[data-testid="alerts-extra-filters-toggle"]').trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.find('[data-testid="alerts-extra-filters"]').exists()).toBe(true)
    const sourceOptions = wrapper.get('[data-testid="alerts-filter-source"]').findAll('option')
    expect(sourceOptions.map((option) => option.attributes('value'))).toEqual(['', 'biz', 'infra', 'node'])
    expect(wrapper.find('[data-testid="alerts-filter-category"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alerts-filter-suppression"]').exists()).toBe(true)
  })

  it('у agronomist включает пресет раствор/климат/свет по code/type', async () => {
    currentUserRole.value = 'agronomist'
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    expect(wrapper.get('[data-testid="alerts-preset-agronomy-domain"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="alert-row-3"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Температура выше нормы в Zone A1')
    expect(wrapper.find('[data-testid="alert-row-1"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('biz_ae3_task_failed')
    expect(wrapper.find('[data-testid="alerts-filter-source"]').exists()).toBe(true)
  })

  it('показывает человеческий заголовок с именем зоны и машинный code вторым слоем', async () => {
    itemsDataValue.push({
      id: 5,
      type: 'PH_HIGH',
      code: 'biz_high_ph',
      severity: 'warning',
      zone: { id: 3, name: 'Салат-1' },
      zone_id: 3,
      created_at: '2025-01-01T13:00:00Z',
      status: 'active',
    })
    const wrapper = mountWithPinia()
    await wrapper.vm.$nextTick()

    const row = wrapper.get('[data-testid="alert-row-5"]')
    expect(row.get('[data-testid="alert-human-title"]').text()).toContain('pH выше нормы в Салат-1')
    expect(row.text()).toContain('biz_high_ph')
  })
})
