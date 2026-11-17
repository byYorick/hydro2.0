import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useSchedulerDispatchMetrics } from '../useSchedulerDispatchMetrics'
const read = vi.hoisted(() => vi.fn())
vi.mock('@/services/api', () => ({ api: { system: { schedulerObservability: read } } }))
function harness() {
  let state!: ReturnType<typeof useSchedulerDispatchMetrics>
  const wrapper = mount(defineComponent({ setup() { state = useSchedulerDispatchMetrics(); return () => null } }))
  return { state, wrapper }
}
describe('authenticated dispatcher polling', () => {
  beforeEach(() => { vi.useFakeTimers(); read.mockReset() })
  afterEach(() => vi.useRealTimers())
  it('shares an in-flight refresh and ignores a response after unmount', async () => {
    let finish!: (value: unknown) => void
    read.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const { state, wrapper } = harness()
    const a = state.refresh(); const b = state.refresh()
    expect(read).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    finish({ pending_intents: 5 })
    await Promise.all([a, b]); await flushPromises()
    expect(state.metrics.value).toBeNull()
    await vi.advanceTimersByTimeAsync(60000)
    expect(read).toHaveBeenCalledTimes(1)
  })
  it('keeps real zero distinct from absent data and marks a stale read', async () => {
    read.mockResolvedValueOnce({ pending_intents: 0, oldest_pending_age_sec: null, cycle_overrun_sec: 0 })
    const { state, wrapper } = harness(); await flushPromises()
    expect(state.metrics.value).toEqual({ pendingIntents: 0, oldestPendingAgeSec: null, dispatchCycleOverrunSec: 0 })
    read.mockRejectedValueOnce(new Error('fixture'))
    await state.refresh()
    expect(state.metrics.value?.pendingIntents).toBe(0)
    expect(state.error.value).toContain('Не удалось обновить')
    wrapper.unmount()
  })
})
