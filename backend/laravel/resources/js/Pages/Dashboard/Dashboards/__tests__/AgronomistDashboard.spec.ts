import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import AgronomistDashboard from '../AgronomistDashboard.vue'

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('@inertiajs/vue3', () => ({
  Link: {
    name: 'Link',
    props: ['href'],
    template: '<a :href="href"><slot /></a>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant', 'size'],
    template: '<span class="badge" :data-variant="variant"><slot /></span>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'variant'],
    template: '<button class="btn"><slot /></button>',
  },
}))

vi.mock('@/Components/Sparkline.vue', () => ({
  default: {
    name: 'Sparkline',
    props: ['data', 'width', 'height', 'color', 'showArea', 'strokeWidth'],
    template: '<svg class="sparkline" />',
  },
}))

vi.mock('@/Components/ZoneHealthGauge.vue', () => ({
  default: {
    name: 'ZoneHealthGauge',
    props: ['value', 'targetMin', 'targetMax', 'globalMin', 'globalMax', 'label', 'unit', 'decimals'],
    template: '<div class="zone-gauge" />',
  },
}))

vi.mock('@/Components/ZoneAIPredictionHint.vue', () => ({
  default: {
    name: 'ZoneAIPredictionHint',
    props: ['zoneId', 'metricType', 'targetMin', 'targetMax', 'horizonMinutes'],
    template: '<div class="ai-hint" />',
  },
}))

vi.mock('@/utils/i18n', () => ({
  translateStatus: (s: string) => `tr:${s}`,
}))

vi.mock('@/composables/useTelemetry', () => ({
  useTelemetry: () => ({
    fetchHistory: vi.fn().mockResolvedValue([]),
  }),
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makeZone(overrides: Record<string, any> = {}): any {
  return {
    id: 1,
    uid: 'zone-1',
    name: 'Zone Alpha',
    status: 'RUNNING',
    greenhouse_id: 1,
    targets: {},
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    ...overrides,
  }
}

function mountDashboard(dashboardOverrides: Record<string, any> = {}) {
  return mount(AgronomistDashboard, {
    props: {
      dashboard: {
        zones: [],
        recipes: [],
        zonesByStatus: {},
        ...dashboardOverrides,
      },
    },
  })
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AgronomistDashboard', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // ─── Empty state ──────────────────────────────────────────────────────────

  it('показывает empty state когда нет зон', () => {
    const wrapper = mountDashboard()
    expect(wrapper.text()).toContain('Нет зон для мониторинга')
  })

  it('скрывает ZoneHealthGauge когда нет зон', () => {
    const wrapper = mountDashboard()
    expect(wrapper.findAllComponents({ name: 'ZoneHealthGauge' }).length).toBe(0)
  })

  // ─── KPI counts ───────────────────────────────────────────────────────────

  it('показывает runningCount из zonesByStatus.RUNNING', () => {
    const wrapper = mountDashboard({ zonesByStatus: { RUNNING: 5, WARNING: 0, ALARM: 0 } })
    expect(wrapper.text()).toContain('5')
    expect(wrapper.text()).toContain('В работе')
  })

  it('показывает warningCount из zonesByStatus.WARNING', () => {
    const wrapper = mountDashboard({ zonesByStatus: { RUNNING: 0, WARNING: 3, ALARM: 0 } })
    expect(wrapper.text()).toContain('3')
    expect(wrapper.text()).toContain('Warning')
  })

  it('показывает alarmCount из zonesByStatus.ALARM', () => {
    const wrapper = mountDashboard({ zonesByStatus: { RUNNING: 0, WARNING: 0, ALARM: 2 } })
    expect(wrapper.text()).toContain('2')
    expect(wrapper.text()).toContain('Alarm')
  })

  it('показывает activeCyclesCount как число зон с activeGrowCycle', () => {
    const zones = [
      makeZone({ id: 1, activeGrowCycle: { id: 10, zone_id: 1 } }),
      makeZone({ id: 2, activeGrowCycle: null }),
      makeZone({ id: 3, activeGrowCycle: { id: 11, zone_id: 3 } }),
    ]
    // RUNNING=9 → уникально, cycles=2
    const wrapper = mountDashboard({ zones, zonesByStatus: { RUNNING: 9, WARNING: 0, ALARM: 0 } })
    expect(wrapper.text()).toContain('Циклов')
    const cyclesBlock = wrapper.findAll('.glass-panel').find(d => d.text().includes('Циклов'))
    expect(cyclesBlock?.text()).toContain('2')
  })

  // ─── Critical alert bar ───────────────────────────────────────────────────

  it('скрывает alert bar когда нет ALARM/WARNING зон', () => {
    const zones = [makeZone({ status: 'RUNNING' })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).not.toContain('🔴')
    // ⚠️ может появляться в Inertia Link или ещё где-то, проверим именно alert bar:
    // При RUNNING-only зонах criticalZones.length === 0, блок v-if="criticalZones.length > 0" скрыт
    expect(wrapper.text()).not.toContain('Перейти')
  })

  it('показывает 🔴 и имя зоны когда есть ALARM зона', () => {
    const zones = [makeZone({ status: 'ALARM', name: 'CriticalZone' })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('🔴')
    expect(wrapper.text()).toContain('CriticalZone')
  })

  it('показывает ⚠️ в alert bar когда есть только WARNING зоны', () => {
    const zones = [makeZone({ status: 'WARNING', name: 'WarnZone' })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('WarnZone')
    expect(wrapper.text()).toContain('⚠️')
  })

  it('показывает "и ещё N зон" для нескольких критических зон', () => {
    const zones = [
      makeZone({ id: 1, status: 'ALARM', name: 'Zone1' }),
      makeZone({ id: 2, status: 'ALARM', name: 'Zone2' }),
      makeZone({ id: 3, status: 'WARNING', name: 'Zone3' }),
    ]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('и ещё 2')
  })

  // ─── criticalZoneHint ─────────────────────────────────────────────────────

  it('выводит criticalZoneHint из issues[0]', () => {
    const zones = [makeZone({ status: 'ALARM', issues: ['pH критически низкий'] })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('pH критически низкий')
  })

  it('выводит criticalZoneHint из alerts_count когда нет issues', () => {
    const zones = [makeZone({ status: 'WARNING', alerts_count: 3 })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('3 активных алертов')
  })

  it('выводит дефолтный хинт "критическое отклонение" для ALARM без issues и alerts', () => {
    const zones = [makeZone({ status: 'ALARM' })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('критическое отклонение')
  })

  it('выводит дефолтный хинт "требует внимания" для WARNING без issues и alerts', () => {
    const zones = [makeZone({ status: 'WARNING' })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('требует внимания')
  })

  // ─── Zone sort order ──────────────────────────────────────────────────────

  it('сортирует зоны в порядке ALARM → WARNING → RUNNING', () => {
    const zones = [
      makeZone({ id: 10, name: 'RunningZone', status: 'RUNNING' }),
      makeZone({ id: 11, name: 'WarningZone', status: 'WARNING' }),
      makeZone({ id: 12, name: 'AlarmZone', status: 'ALARM' }),
    ]
    const wrapper = mountDashboard({ zones })
    const text = wrapper.text()
    expect(text.indexOf('AlarmZone')).toBeLessThan(text.indexOf('WarningZone'))
    expect(text.indexOf('WarningZone')).toBeLessThan(text.indexOf('RunningZone'))
  })

  // ─── Zone card content ────────────────────────────────────────────────────

  it('рендерит имя зоны в карточке', () => {
    const zones = [makeZone({ name: 'MyGreenZone' })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('MyGreenZone')
  })

  it('рендерит badge с переведённым статусом через translateStatus', () => {
    const zones = [makeZone({ status: 'RUNNING' })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('tr:RUNNING')
  })

  it('показывает zone.crop когда нет activeGrowCycle', () => {
    const zones = [makeZone({ crop: 'Базилик', activeGrowCycle: null })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('Базилик')
  })

  it('показывает имя рецепта из activeGrowCycle.recipeRevision.recipe.name', () => {
    const zones = [makeZone({
      activeGrowCycle: {
        id: 1,
        zone_id: 1,
        recipeRevision: { recipe: { name: 'Рецепт Томат' } },
      },
    })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('Рецепт Томат')
  })

  // ─── Phase strip ─────────────────────────────────────────────────────────

  it('показывает phase strip с именем фазы когда задан current_phase_name', () => {
    const zones = [makeZone({
      activeGrowCycle: {
        id: 1,
        zone_id: 1,
        current_phase_name: 'Вегетация',
        started_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
      },
    })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).toContain('Вегетация')
    expect(wrapper.text()).toMatch(/День \d+/)
  })

  it('скрывает phase strip когда нет activeGrowCycle', () => {
    const zones = [makeZone({ activeGrowCycle: null })]
    const wrapper = mountDashboard({ zones })
    expect(wrapper.text()).not.toMatch(/День \d+\/\d+/)
  })

  // ─── resolveTarget ────────────────────────────────────────────────────────

  it('передаёт targetMin/targetMax из вложенного { ph: { min, max } } в ZoneHealthGauge', () => {
    const zones = [makeZone({ targets: { ph: { min: 5.8, max: 6.2 } } })]
    const wrapper = mountDashboard({ zones })
    const phGauge = wrapper.findAllComponents({ name: 'ZoneHealthGauge' })
      .find(g => g.props('label') === 'pH')
    expect(phGauge?.props('targetMin')).toBe(5.8)
    expect(phGauge?.props('targetMax')).toBe(6.2)
  })

  it('передаёт targetMin/targetMax из плоского { ph_min, ph_max } в ZoneHealthGauge', () => {
    const zones = [makeZone({ targets: { ph_min: 5.5, ph_max: 6.5 } })]
    const wrapper = mountDashboard({ zones })
    const phGauge = wrapper.findAllComponents({ name: 'ZoneHealthGauge' })
      .find(g => g.props('label') === 'pH')
    expect(phGauge?.props('targetMin')).toBe(5.5)
    expect(phGauge?.props('targetMax')).toBe(6.5)
  })

  it('передаёт null для targetMin/targetMax когда targets пуст', () => {
    const zones = [makeZone({ targets: {} })]
    const wrapper = mountDashboard({ zones })
    const phGauge = wrapper.findAllComponents({ name: 'ZoneHealthGauge' })
      .find(g => g.props('label') === 'pH')
    expect(phGauge?.props('targetMin')).toBeNull()
    expect(phGauge?.props('targetMax')).toBeNull()
  })

  it('передаёт EC targets из вложенного { ec: { min, max } }', () => {
    const zones = [makeZone({ targets: { ec: { min: 1.4, max: 2.0 } } })]
    const wrapper = mountDashboard({ zones })
    const ecGauge = wrapper.findAllComponents({ name: 'ZoneHealthGauge' })
      .find(g => g.props('label') === 'EC')
    expect(ecGauge?.props('targetMin')).toBe(1.4)
    expect(ecGauge?.props('targetMax')).toBe(2.0)
  })

  // ─── Temperature gauge ────────────────────────────────────────────────────

  it('показывает гауж температуры когда есть telemetry.temperature', () => {
    const zones = [makeZone({ telemetry: { temperature: 22.5 } })]
    const wrapper = mountDashboard({ zones })
    const tempGauge = wrapper.findAllComponents({ name: 'ZoneHealthGauge' })
      .find(g => g.props('label') === 'T°C')
    expect(tempGauge).toBeDefined()
    expect(tempGauge?.props('value')).toBe(22.5)
  })

  it('не показывает гауж температуры когда telemetry.temperature отсутствует', () => {
    const zones = [makeZone({ telemetry: { ph: 6.0, ec: 1.5 } })]
    const wrapper = mountDashboard({ zones })
    const tempGauge = wrapper.findAllComponents({ name: 'ZoneHealthGauge' })
      .find(g => g.props('label') === 'T°C')
    expect(tempGauge).toBeUndefined()
  })

  // ─── Active recipes ───────────────────────────────────────────────────────

  it('показывает блок "Активные рецепты" когда рецепт привязан к зоне', () => {
    const zones = [makeZone({
      id: 1,
      activeGrowCycle: {
        id: 1,
        zone_id: 1,
        recipeRevision: { recipe_id: 42, recipe: { name: 'Томаты' } },
      },
    })]
    const recipes = [{ id: 42, name: 'Рецепт Томаты' }]
    const wrapper = mountDashboard({ zones, recipes })
    expect(wrapper.text()).toContain('Активные рецепты')
    expect(wrapper.text()).toContain('Рецепт Томаты')
  })

  it('скрывает блок "Активные рецепты" когда рецепты не связаны с зонами', () => {
    const zones = [makeZone({ activeGrowCycle: null })]
    const recipes = [{ id: 99, name: 'Несвязанный рецепт' }]
    const wrapper = mountDashboard({ zones, recipes })
    expect(wrapper.text()).not.toContain('Активные рецепты')
  })

  it('показывает число зон в записи рецепта', () => {
    const zones = [
      makeZone({ id: 1, activeGrowCycle: { id: 1, zone_id: 1, recipeRevision: { recipe_id: 5, recipe: { name: 'R' } } } }),
      makeZone({ id: 2, activeGrowCycle: { id: 2, zone_id: 2, recipeRevision: { recipe_id: 5, recipe: { name: 'R' } } } }),
    ]
    const recipes = [{ id: 5, name: 'Двойной рецепт' }]
    const wrapper = mountDashboard({ zones, recipes })
    // 2 зоны используют рецепт → "2 зон"
    expect(wrapper.text()).toContain('Двойной рецепт')
    expect(wrapper.text()).toContain('2 зон')
  })

  // ─── Force irrigation event ───────────────────────────────────────────────

  it('эмитит force-irrigation с zoneId при клике кнопки "Полить"', async () => {
    const zones = [makeZone({ id: 7 })]
    const wrapper = mountDashboard({ zones })
    const buttons = wrapper.findAll('button')
    const irrigateBtn = buttons.find(b => b.text().includes('Полить'))
    expect(irrigateBtn).toBeDefined()
    await irrigateBtn!.trigger('click')
    expect(wrapper.emitted('force-irrigation')).toBeTruthy()
    expect(wrapper.emitted('force-irrigation')![0]).toEqual([7])
  })

  // ─── ZoneAIPredictionHint ─────────────────────────────────────────────────

  it('передаёт zoneId и metricType=PH в ZoneAIPredictionHint', () => {
    const zones = [makeZone({ id: 99 })]
    const wrapper = mountDashboard({ zones })
    const hint = wrapper.findComponent({ name: 'ZoneAIPredictionHint' })
    expect(hint.props('zoneId')).toBe(99)
    expect(hint.props('metricType')).toBe('PH')
  })

  it('передаёт pH targets в ZoneAIPredictionHint', () => {
    const zones = [makeZone({ targets: { ph: { min: 5.8, max: 6.2 } }, id: 1 })]
    const wrapper = mountDashboard({ zones })
    const hint = wrapper.findComponent({ name: 'ZoneAIPredictionHint' })
    expect(hint.props('targetMin')).toBe(5.8)
    expect(hint.props('targetMax')).toBe(6.2)
  })
})
