import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { router } from '@inertiajs/vue3'
import ZoneDashboardCard from '@/Components/ZoneDashboardCard.vue'
import CombinedTelemetrySparkline from '@/Components/ZoneDashboardCard/CombinedTelemetrySparkline.vue'
import MetricPillBar from '@/Components/ZoneDashboardCard/MetricPillBar.vue'
import CycleProgressStack from '@/Components/ZoneDashboardCard/CycleProgressStack.vue'

vi.mock('@inertiajs/vue3', () => ({
  Link: {
    name: 'Link',
    props: ['href'],
    template: '<a :href="href" @click.stop><slot /></a>',
  },
  router: {
    visit: vi.fn(),
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span class="badge"><slot /></span>',
  },
}))

function makeZone(overrides: Record<string, unknown> = {}) {
  return {
    id: 886,
    name: 'Зона 886',
    status: 'ALARM',
    greenhouse: { name: 'Теплица А' },
    recipe: { name: 'Салат' },
    devices: { online: 0, total: 3 },
    alerts_count: 4,
    telemetry: {
      ph: 5.6,
      ec: 1.9,
      temperature: 23.4,
      updated_at: '2026-04-30T06:32:00.000Z',
    },
    targets: {
      ph: { min: 5.35, max: 5.55 },
      ec: { min: 1.8, max: 2.0 },
      temperature: { min: 22.5, max: 25.5 },
    },
    cycle: {
      status: 'running',
      progress: { overall_pct: 10 },
      planting_at: '2026-04-29T00:00:00.000Z',
      expected_harvest_at: '2026-05-10T00:00:00.000Z',
      stages: [
        { state: 'ACTIVE', from: '2026-04-29T00:00:00.000Z', to: '2026-05-01T00:00:00.000Z', name: 'Посадка' },
      ],
      current_stage: { name: 'Посадка' },
    },
    system_state: {
      label: 'Нет связи',
      phase: 'error',
      stale: true,
    },
    tank_levels: {
      clean_percent: 42,
      solution_percent: 58,
      clean_offline: false,
      solution_offline: false,
      clean_present: true,
      solution_present: true,
    },
    irrig_node: { online: true, stale: false, last_seen_at: '2026-04-30T06:32:00.000Z' },
    alerts_preview: [
      { id: 1, type: 'task_failed', details: 'startup', created_at: '2026-04-30T06:32:00.000Z' },
      { id: 2, type: 'task_warning', details: 'startup', created_at: '2026-04-30T06:30:00.000Z' },
    ],
    ...overrides,
  }
}

describe('ZoneDashboardCard', () => {
  it('рендерит ключевые поля карточки', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone(),
        sparklineSeriesData: {
          ph: [5.5, 5.6, 5.7],
          ec: [1.7, 1.8, 1.9],
          temperature: [23.1, 23.2, 23.3],
        },
      },
    })

    expect(wrapper.text()).toContain('Зона 886')
    expect(wrapper.text()).toContain('Теплица А')
    expect(wrapper.text()).toContain('Салат')
    expect(wrapper.text()).toContain('Устр: 0/3')
    expect(wrapper.text()).toContain('Алертов: 4')
    expect(wrapper.text()).toContain('Обновление:')
  })

  it('показывает текущий workflow-статус зоны в шапке', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          alerts_count: 0,
          system_state: { label: 'Готов', phase: 'ready', stale: false },
        }),
      },
    })

    const status = wrapper.find('[data-testid="zone-card-current-status"]')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('Готов')
  })

  it('в non-dense показывает только выбранную метрику на графике и переключает вкладки', async () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone(),
        dense: false,
        sparklineSeriesData: {
          ph: [5.5, 5.6, 5.7],
          ec: [1.7, 1.8, 1.9],
          temperature: [23.1, 23.2, 23.3],
        },
      },
    })

    const sparkline = wrapper.findComponent(CombinedTelemetrySparkline)
    expect(sparkline.exists()).toBe(true)
    expect(sparkline.props('showHeader')).toBe(false)

    const initialSeries = sparkline.props('series') as Array<{ key: string }>
    expect(initialSeries).toHaveLength(1)
    expect(initialSeries[0]?.key).toBe('ph')

    const ecButton = wrapper.findAll('button').find((b) => b.text() === 'EC')
    expect(ecButton).toBeTruthy()
    await ecButton!.trigger('click')

    const ecSeries = wrapper.findComponent(CombinedTelemetrySparkline).props('series') as Array<{ key: string }>
    expect(ecSeries).toHaveLength(1)
    expect(ecSeries[0]?.key).toBe('ec')
  })

  it('прокидывает offline=true в метрики при старой telemetry.updated_at', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          alerts_count: 0,
          telemetry: {
            ph: 5.6,
            ec: 1.9,
            temperature: 23.4,
            updated_at: '2000-01-01T00:00:00.000Z',
          },
        }),
      },
    })

    const metricBars = wrapper.findAllComponents(MetricPillBar)
    expect(metricBars).toHaveLength(3)
    for (const metric of metricBars) {
      expect(metric.props('offline')).toBe(true)
    }
    expect(wrapper.text()).toContain('НЕТ СВЯЗИ')
    expect(wrapper.text()).not.toContain('ВНЕ НОРМЫ')
  })

  it('показывает «НЕТ ДАННЫХ» при unknown telemetryHealth без алертов', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          alerts_count: 0,
          telemetry: {
            ph: null,
            ec: null,
            temperature: null,
            updated_at: new Date().toISOString(),
          },
          targets: {
            ph: null,
            ec: null,
            temperature: null,
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('НЕТ ДАННЫХ')
    expect(wrapper.text()).not.toContain('OK')
  })

  it('MetricPillBar не рендерит marker при offline=true', () => {
    const offline = mount(MetricPillBar, {
      props: {
        label: 'pH',
        value: 5.6,
        targetMin: 5.3,
        targetMax: 5.7,
        offline: true,
      },
    })
    expect(offline.find('.h-2\\.5.w-\\[3px\\]').exists()).toBe(false)

    const online = mount(MetricPillBar, {
      props: {
        label: 'pH',
        value: 5.6,
        targetMin: 5.3,
        targetMax: 5.7,
        offline: false,
      },
    })
    expect(online.find('.h-2\\.5.w-\\[3px\\]').exists()).toBe(true)
  })

  it('без system_state при IRR online показывает «Нет данных», не «Ожидание»', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          system_state: null,
          irrig_node: { online: true, stale: false, last_seen_at: '2026-04-30T06:32:00.000Z' },
        }),
      },
    })

    expect(wrapper.text()).toContain('Нет данных')
    expect(wrapper.text()).not.toContain('Ожидание')
    expect(wrapper.text()).toContain('IRR')
    expect(wrapper.text()).toContain('online')
  })

  it('показывает статус IRR-ноды и адаптирует баки под одно-баковую топологию', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          tank_levels: {
            clean_percent: 67,
            solution_percent: null,
            clean_offline: false,
            solution_offline: true,
            clean_present: true,
            solution_present: false,
          },
          irrig_node: { online: true, stale: false, last_seen_at: '2026-04-30T06:31:00.000Z' },
        }),
      },
    })

    expect(wrapper.text()).toContain('IRR')
    expect(wrapper.text()).toContain('online')
    expect(wrapper.text()).toContain('Бак')
    expect(wrapper.text()).not.toContain('Чистая вода')
    expect(wrapper.text()).not.toContain('Раствор')
  })

  it('показывает топологию 3 бака и рендерит буферный бак', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          tank_levels: {
            clean_percent: 70,
            solution_percent: 55,
            buffer_percent: 33,
            clean_offline: false,
            solution_offline: false,
            buffer_offline: false,
            clean_present: true,
            solution_present: true,
            buffer_present: true,
            topology_count: 3,
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('Топология: 3 бака')
    expect(wrapper.text()).toContain('Буфер')
  })

  it('показывает чип «Автоматика остановлена» и причину при automation_block.blocked=true', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          automation_block: {
            blocked: true,
            reason_code: 'biz_ae3_task_failed',
            severity: 'critical',
            message: 'Цикл прерван: prepare_recirculation timeout',
            since: '2026-04-30T06:32:00.000Z',
            alert_id: 42,
            alerts_count: 1,
          },
        }),
      },
    })

    expect(wrapper.text()).toContain('Автоматика остановлена')
    expect(wrapper.text()).toContain('Задача AE3 завершилась ошибкой')
    expect(wrapper.text()).toContain('Цикл прерван: prepare_recirculation timeout')
  })

  it('не показывает чип блокировки при automation_block=null', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({ automation_block: null }),
      },
    })

    expect(wrapper.text()).not.toContain('Автоматика остановлена')
    expect(wrapper.text()).toContain('Алертов: 4')
  })

  it('при наличии cycle не показывает empty-state «Активный цикл не запущен»', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          cycle: {
            status: 'RUNNING',
            progress: null,
            planting_at: null,
            stages: [],
            current_stage: null,
          },
        }),
      },
    })

    expect(wrapper.text()).not.toContain('Активный цикл не запущен')
    const stack = wrapper.findComponent(CycleProgressStack)
    expect(stack.props('hasCycle')).toBe(true)
  })

  it('показывает empty-state цикла только если cycle == null', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({ cycle: null }),
      },
    })

    expect(wrapper.text()).toContain('Активный цикл не запущен')
  })

  it('считает прогресс фазы локально по датам (1-based день)', () => {
    const now = Date.now()
    // 4 ч из 10 ч фазы → 40%; день посадки = 1
    const stageFrom = new Date(now - 4 * 60 * 60 * 1000)
    const stageTo = new Date(now + 6 * 60 * 60 * 1000)
    const planting = new Date(now - 4 * 60 * 60 * 1000)
    const harvest = new Date(planting.getTime() + 10 * 24 * 60 * 60 * 1000)

    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          cycle: {
            status: 'RUNNING',
            // Устаревший snapshot DTO не должен перебивать live-расчёт.
            progress: { overall_pct: 0, stage_pct: 0 },
            planting_at: planting.toISOString(),
            expected_harvest_at: harvest.toISOString(),
            stages: [
              {
                state: 'ACTIVE',
                from: stageFrom.toISOString(),
                to: stageTo.toISOString(),
                name: 'Вегетация',
                pct: 0,
              },
            ],
            current_stage: { name: 'Вегетация' },
          },
        }),
      },
    })

    expect(wrapper.text()).toMatch(/День 1\/10/)
    const stack = wrapper.findComponent(CycleProgressStack)
    expect(stack.props('phase')).toMatchObject({
      dayElapsed: 1,
      progress: 40,
    })
    expect(stack.props('overallPct')).toBeGreaterThan(0)
  })

  it('задаёт ось EC 0–5 даже без targets', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          targets: {
            ph: { min: 5.35, max: 5.55 },
            ec: null,
            temperature: { min: 22.5, max: 25.5 },
          },
        }),
      },
    })

    const ecBar = wrapper.findAllComponents(MetricPillBar).find((m) => m.props('label') === 'EC')
    expect(ecBar).toBeTruthy()
    expect(ecBar!.props('axisMin')).toBe(0)
    expect(ecBar!.props('axisMax')).toBe(5)
  })

  it('карточка — div с кликом, tabs вне Link; клик ведёт на /zones/:id', async () => {
    vi.mocked(router.visit).mockClear()
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone(),
        dense: false,
        sparklineSeriesData: { ph: [5.5], ec: [1.8], temperature: [23] },
      },
    })

    const root = wrapper.find('[data-testid="zone-dashboard-card"]')
    expect(root.element.tagName).toBe('DIV')
    expect(root.find('a button').exists()).toBe(false)

    const metricTabs = wrapper.findAll('button.metric-tab')
    expect(metricTabs.length).toBeGreaterThan(0)
    // tabs не внутри <a>
    for (const tab of metricTabs) {
      expect(tab.element.closest('a')).toBeNull()
    }

    await root.trigger('click')
    expect(router.visit).toHaveBeenCalledWith('/zones/886')
  })

  it('показывает в алерте только сообщение без сырого JSON', () => {
    const wrapper = mount(ZoneDashboardCard, {
      props: {
        zone: makeZone({
          alerts_preview: [
            {
              id: 1,
              type: 'task_failed',
              details: '{"code":"biz_ae3_task_failed","stage":"startup","message":"Сбой запуска контура"}',
              created_at: '2026-04-30T06:32:00.000Z',
            },
          ],
        }),
      },
    })

    expect(wrapper.text()).toContain('Сбой запуска контура')
    expect(wrapper.text()).not.toContain('"code"')
    expect(wrapper.text()).not.toContain('{"code"')
  })
})

