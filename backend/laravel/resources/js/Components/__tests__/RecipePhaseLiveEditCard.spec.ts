import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import RecipePhaseLiveEditCard from '../ZoneAutomation/RecipePhaseLiveEditCard.vue'

vi.mock('@/services/api/zoneConfigMode', () => ({
  zoneConfigModeApi: {
    show: vi.fn(),
    update: vi.fn(),
    extend: vi.fn(),
    changes: vi.fn(),
    updatePhaseConfig: vi.fn(),
  },
}))

import { zoneConfigModeApi } from '@/services/api/zoneConfigMode'

describe('RecipePhaseLiveEditCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('disables submit until a field + reason are provided', async () => {
    const w = mount(RecipePhaseLiveEditCard, { props: { growCycleId: 5 } })
    const btn = w.find('[data-testid="recipe-phase-submit"]')
    expect(btn.attributes('disabled')).toBeDefined()

    // Only reason
    await w.find('[data-testid="recipe-phase-reason"]').setValue('bump')
    expect(w.find('[data-testid="recipe-phase-submit"]').attributes('disabled'))
      .toBeDefined()

    // Add a numeric field
    await w.find('input[type="number"]').setValue('6.2')
    expect(w.find('[data-testid="recipe-phase-submit"]').attributes('disabled'))
      .toBeUndefined()
  })

  it('submits only filled fields with reason', async () => {
    vi.mocked(zoneConfigModeApi.updatePhaseConfig).mockResolvedValue({
      status: 'ok',
      grow_cycle_id: 5,
      phase_id: 7,
      zone_id: 1,
      config_revision: 9,
      updated_fields: ['ec_target'],
    })

    const w = mount(RecipePhaseLiveEditCard, { props: { growCycleId: 5 } })
    // pH target + EC target
    const inputs = w.findAll('input[type="number"]')
    await inputs[0].setValue('') // ph_target empty — не должен попасть
    await inputs[3].setValue('2.0') // ec_target
    await w.find('[data-testid="recipe-phase-reason"]').setValue('ec bump for flowering')
    await w.find('[data-testid="recipe-phase-form"]').trigger('submit')
    await flushPromises()

    expect(zoneConfigModeApi.updatePhaseConfig).toHaveBeenCalledWith(5, {
      reason: 'ec bump for flowering',
      ec_target: 2.0,
    })
  })

  it('renders success state after submit', async () => {
    vi.mocked(zoneConfigModeApi.updatePhaseConfig).mockResolvedValue({
      status: 'ok',
      grow_cycle_id: 5,
      phase_id: 7,
      zone_id: 1,
      config_revision: 11,
      updated_fields: ['ph_target'],
    })
    const w = mount(RecipePhaseLiveEditCard, { props: { growCycleId: 5 } })
    await w.findAll('input[type="number"]')[0].setValue('6.1')
    await w.find('[data-testid="recipe-phase-reason"]').setValue('ph tweak')
    await w.find('[data-testid="recipe-phase-form"]').trigger('submit')
    await flushPromises()

    const success = w.find('[data-testid="recipe-phase-success"]')
    expect(success.exists()).toBe(true)
    expect(success.text()).toContain('revision 11')
  })

  it('renders error state on failure', async () => {
    vi.mocked(zoneConfigModeApi.updatePhaseConfig).mockRejectedValue({
      response: { data: { message: 'Validation failed' } },
    })
    const w = mount(RecipePhaseLiveEditCard, { props: { growCycleId: 5 } })
    await w.findAll('input[type="number"]')[0].setValue('6.1')
    await w.find('[data-testid="recipe-phase-reason"]').setValue('trigger error')
    await w.find('[data-testid="recipe-phase-form"]').trigger('submit')
    await flushPromises()

    expect(w.find('[data-testid="recipe-phase-error"]').text()).toContain('Validation failed')
  })

  it('prefills form from initial prop', async () => {
    const w = mount(RecipePhaseLiveEditCard, {
      props: {
        growCycleId: 5,
        initial: { ph_target: 6.2, ec_target: 1.8, ec_min: 1.6, ec_max: 2.0 },
      },
    })
    const inputs = w.findAll('input[type="number"]')
    expect((inputs[0].element as HTMLInputElement).value).toBe('6.2')
    expect((inputs[3].element as HTMLInputElement).value).toBe('1.8')
    expect((inputs[4].element as HTMLInputElement).value).toBe('1.6')
    expect((inputs[5].element as HTMLInputElement).value).toBe('2')
  })
})
