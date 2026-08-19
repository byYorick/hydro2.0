import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { UnifiedSummary, UnifiedZone } from '@/composables/useUnifiedDashboard'

const pageState = vi.hoisted(() => ({
  role: 'agronomist' as string,
  pagedZones: [] as UnifiedZone[],
}))

const healthMock = vi.hoisted(() =>
  vi.fn(async () => ({
    app: 'ok',
    db: 'ok',
    mqtt: 'ok',
    history_logger: 'ok',
    automation_engine: 'fail',
  })),
)

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: {
    name: 'AppLayout',
    template: '<div><slot /><slot name="context" /></div>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: { name: 'Badge', props: ['variant'], template: '<span><slot /></span>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'variant'],
    template: '<button @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/Pagination.vue', () => ({
  default: { name: 'Pagination', template: '<div />' },
}))

vi.mock('@/Components/ZoneDashboardCard.vue', () => ({
  default: { name: 'ZoneDashboardCard', template: '<div />' },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}))

vi.mock('@/composables/useTheme', async () => {
  const { ref } = await import('vue')
  return {
    useTheme: () => ({ theme: ref('dark') }),
  }
})

vi.mock('@/composables/useDashboardRealtimeFeed', async () => {
  const { computed, ref } = await import('vue')
  return {
    useDashboardRealtimeFeed: () => ({
      eventFilter: ref('ALL'),
      filteredEvents: computed(() => []),
    }),
  }
})

vi.mock('@/composables/useUnifiedDashboard', async () => {
  const { computed, ref } = await import('vue')
  return {
    useUnifiedDashboard: () => ({
      query: ref(''),
      statusFilter: ref(''),
      greenhouseFilter: ref(''),
      showOnlyAlerts: ref(false),
      denseView: ref(false),
      currentPage: ref(1),
      perPage: ref(25),
      filteredZones: computed(() => pageState.pagedZones),
      pagedZones: computed(() => pageState.pagedZones),
      toggleDense: vi.fn(),
      sparklines: computed(() => ({})),
    }),
  }
})

vi.mock('@/services/api/system', () => ({
  systemApi: {
    health: () => healthMock(),
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: {
        user: { role: pageState.role },
      },
    },
  }),
  router: { visit: vi.fn() },
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
}))

import DashboardIndex from '../Index.vue'

const summary: UnifiedSummary = {
  zones_total: 2,
  zones_running: 1,
  zones_warning: 1,
  zones_alarm: 0,
  cycles_running: 1,
  cycles_paused: 0,
  cycles_planned: 0,
  cycles_none: 1,
  devices_online: 3,
  devices_total: 4,
  alerts_active: 0,
  greenhouses_count: 1,
}

function makeZone(overrides: Partial<UnifiedZone> = {}): UnifiedZone {
  return {
    id: 1,
    name: 'Салат-1',
    status: 'RUNNING',
    greenhouse: null,
    telemetry: {
      ph: 6,
      ec: 1.5,
      temperature: 22,
      humidity: 60,
      co2: null,
      updated_at: '2026-08-19T10:00:00.000Z',
    },
    targets: {
      ph: { min: 5.5, max: 6.5 },
      ec: { min: 1.2, max: 1.8 },
      temperature: { min: 18, max: 26 },
    },
    crop: null,
    alerts_count: 0,
    alerts_preview: [],
    devices: { total: 3, online: 3 },
    recipe: null,
    plant: null,
    cycle: null,
    ...overrides,
  }
}

function mountDashboard(role: string, zones: UnifiedZone[] = []) {
  pageState.role = role
  pageState.pagedZones = zones
  return mount(DashboardIndex, {
    props: {
      summary,
      zones,
      greenhouses: [],
      latestAlerts: [],
    },
  })
}

describe('Dashboard/Index.vue', () => {
  beforeEach(() => {
    pageState.role = 'agronomist'
    pageState.pagedZones = []
    healthMock.mockClear()
  })

  it('агроном видит кнопку «Запустить цикл»', () => {
    const wrapper = mountDashboard('agronomist')

    expect(wrapper.text()).toContain('Запустить цикл')
    expect(wrapper.text()).toContain('Обзор культур')
  })

  it('operator не видит кнопку «Запустить цикл» и видит пустую очередь', () => {
    const wrapper = mountDashboard('operator')

    expect(wrapper.text()).not.toContain('Запустить цикл')
    expect(wrapper.text()).not.toContain('операционный центр')
    expect(wrapper.text()).toContain('смена')
    expect(wrapper.text()).toContain('Сегодня')
    expect(wrapper.text()).toContain('Сегодня действий не требуется')
    expect(wrapper.find('[data-testid="dashboard-shift-empty"]').exists()).toBe(true)
  })

  it('operator показывает очередь дел по тревоге и блокировке', () => {
    const wrapper = mountDashboard('operator', [
      makeZone({
        id: 7,
        name: 'Томат-2',
        status: 'ALARM',
        alerts_count: 2,
        automation_block: {
          blocked: true,
          reason_code: 'biz_correction_exhausted',
          severity: 'critical',
          message: 'Автоматика остановлена',
          since: '2026-08-19T09:00:00.000Z',
          alert_id: 11,
          alerts_count: 1,
        },
      }),
    ])

    expect(wrapper.text()).toContain('Томат-2')
    expect(wrapper.text()).toContain('Автоматика остановлена')
    expect(wrapper.text()).toContain('Открыть зону')
    expect(wrapper.text()).toContain('Тревоги')
    expect(wrapper.text()).not.toContain('Сегодня действий не требуется')
    expect(wrapper.get('a[href="/zones/7?tab=alerts"]').text()).toContain('Тревоги')
  })

  it('агроном группирует карточки по культуре', () => {
    const wrapper = mountDashboard('agronomist', [
      makeZone({ id: 1, name: 'Зона A', crop: 'Томат' }),
      makeZone({ id: 2, name: 'Зона B', crop: 'Салат', plant: { id: 4, name: 'Салат' } }),
    ])

    const groups = wrapper.findAll('[data-testid="dashboard-crop-group"]')
    expect(groups).toHaveLength(2)
    expect(wrapper.text()).toContain('Томат')
    expect(wrapper.text()).toContain('Салат')
    expect(wrapper.text()).toContain('В норме')
    expect(wrapper.text()).toContain('Вне коридора')
  })

  it('engineer показывает блок проблемных узлов и зон', () => {
    const wrapper = mountDashboard('engineer', [
      makeZone({
        id: 3,
        name: 'Климат-1',
        devices: { total: 4, online: 1 },
        irrig_node: { online: false, stale: true, last_seen_at: null },
      }),
    ])

    expect(wrapper.text()).toContain('Узлы')
    expect(wrapper.text()).toContain('Проблемные узлы и зоны')
    expect(wrapper.text()).toContain('Узлы офлайн: 1/4')
    expect(wrapper.text()).toContain('Поливной узел не на связи')
    expect(wrapper.find('[data-testid="dashboard-engineering-issues"]').exists()).toBe(true)
  })

  it('admin показывает заголовок Система и светофор сервисов', async () => {
    const wrapper = mountDashboard('admin')
    await flushPromises()

    expect(wrapper.text()).toContain('Система')
    expect(wrapper.text()).toContain('4 из 5 ok')
    expect(wrapper.find('[data-testid="dashboard-admin-health"]').exists()).toBe(true)
    expect(healthMock).toHaveBeenCalled()
  })

  it('подписывает KPI Warning/Alarm по-русски', () => {
    const wrapper = mountDashboard('agronomist')

    expect(wrapper.text()).toContain('Предупреждение')
    expect(wrapper.text()).toContain('Тревога')
    expect(wrapper.text()).not.toMatch(/\bWarning\b/)
    expect(wrapper.text()).not.toMatch(/\bAlarm\b/)
  })

  it('фильтр зоны сохраняет значения WARNING/ALARM и меняет только подписи', () => {
    const wrapper = mountDashboard('operator')
    const warning = wrapper.find('option[value="WARNING"]')
    const alarm = wrapper.find('option[value="ALARM"]')
    const running = wrapper.find('option[value="RUNNING"]')

    expect(warning.exists()).toBe(true)
    expect(alarm.exists()).toBe(true)
    expect(running.exists()).toBe(true)
    expect(warning.text()).toBe('Предупреждение')
    expect(alarm.text()).toBe('Тревога')
    expect(running.text()).toBe('Активные зоны')
  })
})
