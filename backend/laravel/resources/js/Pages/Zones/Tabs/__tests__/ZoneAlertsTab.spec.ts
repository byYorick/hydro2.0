import { mount } from '@vue/test-utils'
import { describe, expect, it, beforeEach, vi } from 'vitest'

const acknowledgeMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    alerts: {
      acknowledge: (alertId: number) => acknowledgeMock(alertId),
    },
  },
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: (...args: unknown[]) => showToastMock(...args),
  }),
}))

vi.mock('@/composables/useRole', () => ({
  useRole: () => ({
    canResolveAlerts: { value: true },
  }),
}))

import ZoneAlertsTab from '../ZoneAlertsTab.vue'

function makeAlert(overrides: Record<string, unknown> = {}) {
  return {
    id: 11,
    type: 'AE3_ALERT',
    code: 'biz_zone_recipe_phase_targets_missing',
    source: 'biz',
    title: 'Не настроены phase targets рецепта',
    description: 'Для активной фазы рецепта отсутствуют обязательные целевые значения.',
    recommendation: 'Проверьте recipe phase targets и заполните обязательные цели для активной фазы.',
    status: 'active',
    message: 'Recipe phase targets are missing',
    details: {
      title: 'Не настроены phase targets рецепта',
      error_message: 'Validation failed',
      stage: 'prepare',
      correction_window_id: 'cw-9001',
    },
    created_at: '2026-03-29T08:00:00Z',
    ...overrides,
  }
}

describe('ZoneAlertsTab.vue', () => {
  beforeEach(() => {
    acknowledgeMock.mockReset()
    showToastMock.mockReset()
  })

  it('открывает модалку деталей по клику на алерт', async () => {
    const wrapper = mount(ZoneAlertsTab, {
      props: {
        zoneId: 42,
        alerts: [makeAlert()],
      },
      global: {
        stubs: {
          VirtualList: {
            props: ['items'],
            template: '<div><slot v-for="item in items" :key="item.id" :item="item" /></div>',
          },
          Modal: {
            props: ['open', 'title'],
            template: '<div v-if="open" data-testid="zone-alert-details-modal"><slot /><slot name="footer" /></div>',
          },
        },
      },
    })

    await wrapper.get('[data-testid="zone-alert-row-11"]').trigger('click')

    expect(wrapper.get('[data-testid="zone-alert-details-modal"]').text()).toContain('Не настроены phase targets рецепта')
    expect(wrapper.get('[data-testid="alert-details-process-stop"]').text()).toContain('Стоп: Автоматика')
    expect(wrapper.get('[data-testid="alert-details-correction-window-id"]').text()).toBe('cw-9001')
    expect(wrapper.text()).toContain('Что делать')
    expect(wrapper.text()).toContain('Проверьте recipe phase targets')
  })

  it('закрывает алерт по кнопке Решить', async () => {
    acknowledgeMock.mockResolvedValue(makeAlert({
      status: 'resolved',
      resolved_at: '2026-03-29T08:10:00Z',
    }))

    const wrapper = mount(ZoneAlertsTab, {
      props: {
        zoneId: 42,
        alerts: [makeAlert()],
      },
      global: {
        stubs: {
          VirtualList: {
            props: ['items'],
            template: '<div><slot v-for="item in items" :key="item.id" :item="item" /></div>',
          },
          Modal: {
            props: ['open', 'title'],
            template: '<div v-if="open" data-testid="zone-alert-details-modal"><slot /><slot name="footer" /></div>',
          },
        },
      },
    })

    await wrapper.get('[data-testid="zone-alert-row-11"]').trigger('click')
    await wrapper.get('[data-testid="zone-alert-resolve-button"]').trigger('click')

    expect(acknowledgeMock).toHaveBeenCalledWith(11)
    expect(showToastMock).toHaveBeenCalledWith('Алерт помечен как решённый', 'success', 3000)
    expect(wrapper.find('[data-testid="zone-alert-details-modal"]').exists()).toBe(false)

    const allFilter = wrapper.findAll('button').find((button) => button.text() === 'Все')
    expect(allFilter).toBeTruthy()
    await allFilter!.trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Решённые')
  })

  it('группирует active process-stopping алерты перед остальными', async () => {
    const wrapper = mount(ZoneAlertsTab, {
      props: {
        zoneId: 42,
        alerts: [
          makeAlert({
            id: 1,
            code: 'biz_low_ph',
            title: 'Низкий pH',
          }),
          makeAlert({
            id: 2,
            code: 'biz_overcurrent',
            category: 'safety',
            severity: 'critical',
            title: 'Сверхток на исполнительном канале',
          }),
          makeAlert({
            id: 3,
            code: 'biz_zone_recipe_phase_targets_missing',
            title: 'Не настроены phase targets рецепта',
          }),
          makeAlert({
            id: 4,
            code: 'biz_high_ec',
            status: 'resolved',
            title: 'Высокий EC',
            resolved_at: '2026-03-29T08:10:00Z',
          }),
        ],
      },
      global: {
        stubs: {
          Modal: {
            props: ['open', 'title'],
            template: '<div v-if="open" data-testid="zone-alert-details-modal"><slot /><slot name="footer" /></div>',
          },
        },
      },
    })

    const allFilter = wrapper.findAll('button').find((button) => button.text() === 'Все')
    expect(allFilter).toBeTruthy()
    await allFilter!.trigger('click')
    await wrapper.vm.$nextTick()

    expect(wrapper.get('[data-testid="zone-alert-section-automation-block"]').text()).toContain('Блокируют автоматику')
    expect(wrapper.get('[data-testid="zone-alert-section-safety"]').text()).toContain('Останавливают железо')
    expect(wrapper.get('[data-testid="zone-alert-section-other"]').text()).toContain('Остальные')
    expect(wrapper.get('[data-testid="zone-alert-section-resolved"]').text()).toContain('Решённые')

    const rowTestIds = wrapper
      .findAll('[data-testid^="zone-alert-row-"]')
      .map((row) => row.attributes('data-testid'))

    expect(rowTestIds).toEqual([
      'zone-alert-row-3',
      'zone-alert-row-2',
      'zone-alert-row-1',
      'zone-alert-row-4',
    ])

    const processStoppingKinds = wrapper
      .findAll('[data-testid="alert-process-stop-badge"]')
      .map((badge) => badge.attributes('data-process-stopping-kind'))

    expect(processStoppingKinds).toEqual(['automation_block', 'safety'])
  })

  it('сортирует алерты внутри секции по severity и дате создания', () => {
    const wrapper = mount(ZoneAlertsTab, {
      props: {
        zoneId: 42,
        alerts: [
          makeAlert({
            id: 10,
            code: 'biz_overcurrent',
            severity: 'warning',
            created_at: '2026-03-29T10:00:00Z',
            title: 'Сверхток warning',
          }),
          makeAlert({
            id: 11,
            code: 'biz_no_flow',
            severity: 'critical',
            created_at: '2026-03-29T08:00:00Z',
            title: 'Нет потока critical',
          }),
          makeAlert({
            id: 12,
            code: 'biz_dry_run',
            severity: 'critical',
            created_at: '2026-03-29T12:00:00Z',
            title: 'Сухой ход critical новее',
          }),
        ],
      },
      global: {
        stubs: {
          Modal: {
            props: ['open', 'title'],
            template: '<div v-if="open" data-testid="zone-alert-details-modal"><slot /><slot name="footer" /></div>',
          },
        },
      },
    })

    const safetyRows = wrapper
      .get('[data-testid="zone-alert-section-safety"]')
      .findAll('[data-testid^="zone-alert-row-"]')
      .map((row) => row.attributes('data-testid'))

    expect(safetyRows).toEqual([
      'zone-alert-row-12',
      'zone-alert-row-11',
      'zone-alert-row-10',
    ])
  })
})
