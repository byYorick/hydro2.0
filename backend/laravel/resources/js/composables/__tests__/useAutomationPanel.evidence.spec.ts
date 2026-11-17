import { defineComponent, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAutomationPanel } from '../useAutomationPanel'

const read = vi.hoisted(() => vi.fn())
vi.mock('@inertiajs/vue3', () => ({ usePage: () => ({ props: {} }) }))
vi.mock('@/services/api', () => ({ api: { zones: { getState: read } } }))
vi.mock('@/stores/zones', () => ({ useZonesStore: () => ({ zoneEventSeq: {} }) }))
vi.mock('@/utils/env', () => ({ readBooleanEnv: () => true }))
vi.mock('@/utils/echoClient', () => ({ getConnectionState: () => ({ state: 'connected' }), onWsStateChange: () => () => {} }))
vi.mock('@/ws/managedChannelEvents', () => ({ subscribeManagedChannelEvents: () => () => {} }))
const snapshot = () => ({ zone_id: 42, state: 'IRRIGATING', current_stage: 'irrigation_run', state_details: { elapsed_sec: 12, progress_percent: 30 }, active_processes: { pump_in: true }, current_levels: {}, state_meta: { source: 'live', served_at: new Date().toISOString() } })
function harness() {
  const props = reactive({ zoneId: 42 })
  let state!: ReturnType<typeof useAutomationPanel>
  const wrapper = mount(defineComponent({ setup() { state = useAutomationPanel(props, vi.fn()); return () => null } }))
  return { state, props, wrapper }
}
describe('automation snapshot evidence and lifecycle', () => {
  beforeEach(() => { vi.useFakeTimers(); read.mockReset() })
  afterEach(() => vi.useRealTimers())
  it('keeps unknown levels distinct from an observed zero', async () => {
    read.mockResolvedValue({ ...snapshot(), current_levels: { clean_tank_level_percent: 0, nutrient_tank_level_percent: null, ph: false, ec: '' }, active_processes: { pump_in: 'false' } })
    const { state, wrapper } = harness(); await flushPromises()
    expect(state.cleanTankLevel.value).toBe(0)
    expect(state.nutrientTankLevel.value).toBeNull()
    expect(state.bufferTankLevel.value).toBeNull()
    expect(state.automationState.value?.current_levels.ph).toBeNull()
    expect(state.automationState.value?.current_levels.ec).toBeNull()
    expect(state.isPumpInActive.value).toBe(false)
    wrapper.unmount()
  })
  it('rejects a malformed state instead of displaying idle', async () => {
    read.mockResolvedValue({ zone_id: 42, state: 'future_state' })
    const { state, wrapper } = harness(); await flushPromises()
    expect(state.automationState.value).toBeNull()
    expect(state.errorMessage.value).toContain('Не удалось получить')
    expect(state.isProcessActive.value).toBe(false)
    wrapper.unmount()
  })
  it('preserves the old snapshot but pauses animation and live progress after a read failure', async () => {
    read.mockResolvedValueOnce(snapshot())
    const { state, wrapper } = harness(); await flushPromises()
    expect(state.isProcessActive.value).toBe(true)
    read.mockRejectedValueOnce(new Error('fixture'))
    await state.refresh()
    const flow = state.flowOffset.value
    await vi.advanceTimersByTimeAsync(1000)
    expect(state.automationState.value?.state).toBe('IRRIGATING')
    expect(state.snapshotUnreliable.value).toBe(true)
    expect(state.isProcessActive.value).toBe(false)
    expect(state.showProgressPercent.value).toBe(false)
    expect(state.flowOffset.value).toBe(flow)
    expect(state.connectivityWarning.value).toContain('ранее полученные')
    wrapper.unmount()
  })
  it('continues periodic verification while WebSocket is connected', async () => {
    read.mockResolvedValue(snapshot())
    const { wrapper } = harness(); await flushPromises()
    const initial = read.mock.calls.length
    await vi.advanceTimersByTimeAsync(31000); await flushPromises()
    expect(read.mock.calls.length).toBeGreaterThan(initial)
    expect(read).toHaveBeenCalledWith(42, { skipErrorToast: true })
    wrapper.unmount()
  })
  it('ignores a response after unmount and does not run a queued read', async () => {
    let finish!: (value: unknown) => void
    read.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const { state, wrapper } = harness()
    void state.refresh()
    wrapper.unmount(); finish(snapshot()); await flushPromises()
    expect(state.automationState.value).toBeNull()
    await vi.advanceTimersByTimeAsync(60000)
    expect(read).toHaveBeenCalledTimes(1)
  })
  it('does not apply an old request after navigating away and back to the same zone', async () => {
    let finish!: (value: unknown) => void
    read.mockReturnValueOnce(new Promise(resolve => { finish = resolve })).mockResolvedValue({ ...snapshot(), state: 'READY' })
    const { state, props, wrapper } = harness()
    props.zoneId = 43; await flushPromises()
    props.zoneId = 42; await flushPromises()
    finish(snapshot()); await flushPromises()
    expect(state.automationState.value?.state).toBe('READY')
    wrapper.unmount()
  })
})
