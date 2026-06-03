import { describe, expect, it, vi } from 'vitest'
import { useZoneAutomationScheduler } from '@/composables/useZoneAutomationScheduler'

vi.mock('@/composables/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribeToZoneCommands: vi.fn(),
    unsubscribeAll: vi.fn(),
  }),
}))

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      getControlMode: vi.fn(),
      setControlMode: vi.fn(),
      runManualStep: vi.fn(),
    },
  },
}))

describe('useZoneAutomationScheduler', () => {
  it('гидратирует режим из zoneControlMode до fetch', async () => {
    const props = {
      zoneId: 1,
      zoneControlMode: 'semi' as const,
      targets: {},
    }

    const { automationControlMode, hydrateControlModeFromProp } = useZoneAutomationScheduler(
      props,
      { showToast: vi.fn() },
    )

    expect(automationControlMode.value).toBe('auto')

    hydrateControlModeFromProp()
    expect(automationControlMode.value).toBe('semi')
  })

  it('resetForZoneChange не сбрасывает в auto при zoneControlMode=manual', () => {
    const props = {
      zoneId: 2,
      zoneControlMode: 'manual' as const,
      targets: {},
    }

    const { automationControlMode, resetForZoneChange } = useZoneAutomationScheduler(
      props,
      { showToast: vi.fn() },
    )

    automationControlMode.value = 'semi'
    resetForZoneChange()
    expect(automationControlMode.value).toBe('manual')
  })
})
