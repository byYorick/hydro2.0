import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ZonePageHeader from '../ZonePageHeader.vue'
import type { UserRole } from '@/types/User'

const pageProps = vi.hoisted(() => ({
  auth: { user: { role: 'operator' as UserRole } },
}))

vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({ props: pageProps }),
}))

function mountHeader(role: UserRole, extra: Record<string, unknown> = {}) {
  pageProps.auth.user.role = role
  return mount(ZonePageHeader, {
    props: {
      zoneName: 'Test Zone',
      cropLabel: 'Test Recipe',
      phaseLabel: 'Phase 1',
      phaseDaysElapsed: 2,
      phaseDaysTotal: 7,
      statusLabel: 'Цикл активен',
      statusVariant: 'success',
      cycleStatus: 'RUNNING',
      canOperateZone: true,
      canManageCycle: true,
      ...extra,
    },
  })
}

describe('ZonePageHeader', () => {
  beforeEach(() => {
    pageProps.auth.user.role = 'operator'
  })

  it('renders a visible h1 with zone name', () => {
    const wrapper = mountHeader('operator')
    const title = wrapper.get('[data-testid="zone-page-header-title"]')

    expect(title.element.tagName).toBe('H1')
    expect(title.classes()).not.toContain('sr-only')
    expect(title.text()).toBe('Test Zone')
  })

  it('shows crop, phase, days and a single status badge', () => {
    const wrapper = mountHeader('operator')

    expect(wrapper.get('[data-testid="zone-page-header-crop"]').text()).toBe('Test Recipe')
    expect(wrapper.get('[data-testid="zone-page-header-phase"]').text()).toBe('Phase 1')
    expect(wrapper.get('[data-testid="zone-page-header-days"]').text()).toBe('День 2/7')
    expect(wrapper.findAll('[data-testid="zone-page-header-status"]')).toHaveLength(1)
    expect(wrapper.get('[data-testid="zone-page-header-status"]').text()).toBe('Цикл активен')
  })

  it('shows operator actions: water, pause and actions', () => {
    const wrapper = mountHeader('operator')

    expect(wrapper.get('[data-testid="zone-header-water"]').text()).toBe('Полить')
    expect(wrapper.get('[data-testid="zone-header-pause"]').text()).toBe('Пауза')
    expect(wrapper.get('[data-testid="zone-header-actions"]').text()).toBe('Действия')
    expect(wrapper.find('[data-testid="zone-header-next-phase"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="zone-header-diagnose"]').exists()).toBe(false)
  })

  it('shows agronomist pause and next phase', () => {
    const wrapper = mountHeader('agronomist')

    expect(wrapper.find('[data-testid="zone-header-water"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="zone-header-pause"]').text()).toBe('Пауза')
    expect(wrapper.get('[data-testid="zone-header-next-phase"]').text()).toBe('Следующая фаза')
    expect(wrapper.find('[data-testid="zone-header-actions"]').exists()).toBe(false)
  })

  it('shows engineer diagnose action', async () => {
    const wrapper = mountHeader('engineer')

    expect(wrapper.find('[data-testid="zone-header-water"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="zone-header-pause"]').exists()).toBe(false)
    const diagnose = wrapper.get('[data-testid="zone-header-diagnose"]')
    expect(diagnose.text()).toBe('Диагностика')
    await diagnose.trigger('click')
    expect(wrapper.emitted('diagnose')).toHaveLength(1)
  })

  it('shows admin pause when cycle can be managed', () => {
    const wrapper = mountHeader('admin')

    expect(wrapper.get('[data-testid="zone-header-pause"]').text()).toBe('Пауза')
    expect(wrapper.find('[data-testid="zone-header-water"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="zone-header-diagnose"]').exists()).toBe(false)
  })

  it('hides pause when cycle is not running', () => {
    const wrapper = mountHeader('operator', { cycleStatus: 'PAUSED' })

    expect(wrapper.find('[data-testid="zone-header-pause"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="zone-header-water"]').exists()).toBe(true)
  })
})
