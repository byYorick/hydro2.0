import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ConfigModeCard from '../ZoneAutomation/ConfigModeCard.vue'

vi.mock('@/services/api/zoneConfigMode', () => {
  return {
    zoneConfigModeApi: {
      show: vi.fn(),
      update: vi.fn(),
      extend: vi.fn(),
      changes: vi.fn(),
      updatePhaseConfig: vi.fn(),
    },
  }
})

import { zoneConfigModeApi } from '@/services/api/zoneConfigMode'

const lockedState = {
  zone_id: 1,
  config_mode: 'locked' as const,
  config_revision: 3,
  live_until: null,
  live_started_at: null,
  config_mode_changed_at: null,
  config_mode_changed_by: null,
}

const liveState = {
  ...lockedState,
  config_mode: 'live' as const,
  live_until: new Date(Date.now() + 30 * 60_000).toISOString(),
  live_started_at: new Date().toISOString(),
}

describe('ConfigModeCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders locked badge by default', async () => {
    vi.mocked(zoneConfigModeApi.show).mockResolvedValue(lockedState)
    const w = mount(ConfigModeCard, {
      props: { zoneId: 1, controlMode: 'manual', role: 'agronomist' },
    })
    await flushPromises()
    expect(w.find('[data-testid="config-mode-badge"]').text()).toContain('Locked')
  })

  it('shows live badge + countdown in live mode', async () => {
    vi.mocked(zoneConfigModeApi.show).mockResolvedValue(liveState)
    const w = mount(ConfigModeCard, {
      props: { zoneId: 1, controlMode: 'manual', role: 'agronomist' },
    })
    await flushPromises()
    expect(w.find('[data-testid="config-mode-badge"]').text()).toContain('Live tuning')
    expect(w.find('[data-testid="config-mode-countdown"]').exists()).toBe(true)
  })

  it('disables live button when control_mode is auto', async () => {
    vi.mocked(zoneConfigModeApi.show).mockResolvedValue(lockedState)
    const w = mount(ConfigModeCard, {
      props: { zoneId: 1, controlMode: 'auto', role: 'agronomist' },
    })
    await flushPromises()
    const liveBtn = w.find('[data-testid="config-mode-switch-live"]')
    expect(liveBtn.attributes('disabled')).toBeDefined()
  })

  it('disables live button for operator (cannot setLive)', async () => {
    vi.mocked(zoneConfigModeApi.show).mockResolvedValue(lockedState)
    const w = mount(ConfigModeCard, {
      props: { zoneId: 1, controlMode: 'manual', role: 'operator' },
    })
    await flushPromises()
    const liveBtn = w.find('[data-testid="config-mode-switch-live"]')
    expect(liveBtn.attributes('disabled')).toBeDefined()
  })

  it('opens live dialog on click', async () => {
    vi.mocked(zoneConfigModeApi.show).mockResolvedValue(lockedState)
    const w = mount(ConfigModeCard, {
      props: { zoneId: 1, controlMode: 'manual', role: 'agronomist' },
    })
    await flushPromises()
    await w.find('[data-testid="config-mode-switch-live"]').trigger('click')
    expect(w.find('[data-testid="config-mode-live-dialog"]').exists()).toBe(true)
  })

  it('calls update API on live confirm', async () => {
    vi.mocked(zoneConfigModeApi.show).mockResolvedValue(lockedState)
    vi.mocked(zoneConfigModeApi.update).mockResolvedValue(liveState)
    const w = mount(ConfigModeCard, {
      props: { zoneId: 1, controlMode: 'manual', role: 'agronomist' },
    })
    await flushPromises()
    await w.find('[data-testid="config-mode-switch-live"]').trigger('click')
    await w.find('[data-testid="config-mode-live-dialog"] input[type="text"]').setValue('tuning ec')
    await w.find('[data-testid="config-mode-live-confirm"]').trigger('click')
    await flushPromises()
    expect(zoneConfigModeApi.update).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ mode: 'live', reason: 'tuning ec' }),
    )
  })
})
