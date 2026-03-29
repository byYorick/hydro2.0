import { mount } from '@vue/test-utils'
import { describe, expect, it, beforeEach, vi } from 'vitest'

const patchMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    patch: (...args: unknown[]) => patchMock(...args),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: (...args: unknown[]) => showToastMock(...args),
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
    },
    created_at: '2026-03-29T08:00:00Z',
    ...overrides,
  }
}

describe('ZoneAlertsTab.vue', () => {
  beforeEach(() => {
    patchMock.mockReset()
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
    expect(wrapper.text()).toContain('Что делать')
    expect(wrapper.text()).toContain('Проверьте recipe phase targets')
  })

  it('закрывает алерт по кнопке Решить', async () => {
    patchMock.mockResolvedValue({
      data: {
        data: makeAlert({
          status: 'resolved',
          resolved_at: '2026-03-29T08:10:00Z',
        }),
      },
    })

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

    expect(patchMock).toHaveBeenCalledWith('/api/alerts/11/ack', {})
    expect(showToastMock).toHaveBeenCalledWith('Алерт помечен как решённый', 'success', 3000)
    expect(wrapper.find('[data-testid="zone-alert-details-modal"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Решённые')
  })
})
