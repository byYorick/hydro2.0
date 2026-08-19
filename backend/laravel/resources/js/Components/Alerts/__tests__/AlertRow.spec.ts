import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AlertRow from '../AlertRow.vue'
import type { Alert } from '@/types/Alert'

function makeAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    id: 11,
    type: 'AE3_ALERT',
    code: 'biz_zone_recipe_phase_targets_missing',
    title: 'Не настроены phase targets рецепта',
    status: 'active',
    severity: 'error',
    message: 'Recipe phase targets are missing',
    details: null,
    created_at: '2026-03-29T08:00:00Z',
    ...overrides,
  }
}

describe('AlertRow.vue', () => {
  it('показывает badge остановки автоматики для policy-managed кода', () => {
    const wrapper = mount(AlertRow, {
      props: {
        item: makeAlert({ code: 'biz_zone_recipe_phase_targets_missing' }),
      },
    })

    const badge = wrapper.get('[data-testid="alert-process-stop-badge"]')
    expect(badge.text()).toContain('Автоматика')
    expect(badge.attributes('data-process-stopping-kind')).toBe('automation_block')
  })

  it('показывает badge safety для critical hardware кода', () => {
    const wrapper = mount(AlertRow, {
      props: {
        item: makeAlert({
          code: 'biz_overcurrent',
          category: 'safety',
          severity: 'critical',
          title: 'Сверхток на исполнительном канале',
        }),
      },
    })

    const badge = wrapper.get('[data-testid="alert-process-stop-badge"]')
    expect(badge.text()).toContain('Железо')
    expect(badge.attributes('data-process-stopping-kind')).toBe('safety')
  })

  it('показывает человеческий заголовок с именем зоны, code остаётся вторым слоем', () => {
    const wrapper = mount(AlertRow, {
      props: {
        item: makeAlert({
          type: 'PH_HIGH',
          code: 'biz_high_ph',
          title: 'High pH',
          zone: { id: 7, name: 'Салат-1' },
        }),
      },
    })

    expect(wrapper.get('[data-testid="alert-human-title"]').text()).toBe('pH выше нормы в Салат-1')
    expect(wrapper.text()).toContain('biz_high_ph')
  })
})
