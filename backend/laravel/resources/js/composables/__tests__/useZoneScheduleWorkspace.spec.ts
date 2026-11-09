import { defineComponent, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useZoneScheduleWorkspace } from '../useZoneScheduleWorkspace'
import type { ZoneAutomationTabProps } from '../zoneAutomationTypes'

const api = vi.hoisted(() => ({ scheduleWorkspace: vi.fn(), getState: vi.fn(), getExecution: vi.fn(), schedulerDiagnostics: vi.fn() }))
vi.mock('@/services/api', () => ({ api: { zones: api } }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(res => { resolve = res })
  return { promise, resolve }
}
function workspace(zoneId = 1) {
  return { zone_id: zoneId, execution: { recent_runs: [], active_run: null }, capabilities: { executable_task_types: ['irrigation'] }, plan: { lanes: [], windows: [] } }
}
function harness() {
  const props = reactive({ zoneId: 1, targets: {} } as ZoneAutomationTabProps)
  let state!: ReturnType<typeof useZoneScheduleWorkspace>
  const wrapper = mount(defineComponent({ setup() { state = useZoneScheduleWorkspace(props); return () => null } }))
  return { state, props, wrapper }
}

describe('scheduler workspace lifecycle', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.scheduleWorkspace.mockImplementation(async (zoneId: number) => workspace(zoneId))
    api.getState.mockResolvedValue({ state_label: 'Готово' })
    api.getExecution.mockImplementation(async (_zone: number, id: string) => ({ execution_id: id }))
  })

  it('загружает данные один раз при открытии и смене зоны', async () => {
    const { props, wrapper } = harness()
    await flushPromises()
    expect(api.scheduleWorkspace).toHaveBeenCalledTimes(1)
    expect(api.getState).toHaveBeenCalledTimes(1)
    props.zoneId = 2
    await flushPromises()
    expect(api.scheduleWorkspace).toHaveBeenCalledTimes(2)
    expect(api.getState).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('не возвращает старую зону после позднего ответа состояния', async () => {
    const old = deferred<unknown>()
    api.getState.mockReturnValueOnce(old.promise).mockResolvedValue({ state_label: 'Новая зона' })
    const { state, props, wrapper } = harness()
    props.zoneId = 2
    await flushPromises()
    old.resolve({ state_label: 'Старая зона' })
    await flushPromises()
    expect(state.automationState.value?.state_label).toBe('Новая зона')
    wrapper.unmount()
  })

  it('сохраняет последний выбор при ответах деталей в обратном порядке', async () => {
    const old = deferred<unknown>()
    const { state, wrapper } = harness()
    await flushPromises()
    api.getExecution.mockReturnValueOnce(old.promise).mockResolvedValue({ execution_id: 'new' })
    state.selectExecution('old')
    state.selectExecution('new')
    await flushPromises()
    old.resolve({ execution_id: 'old' })
    await flushPromises()
    expect(state.selectedExecution.value?.execution_id).toBe('new')
    wrapper.unmount()
  })

  it('не открывает закрытую панель после запоздавшего ответа', async () => {
    const pending = deferred<unknown>()
    const { state, wrapper } = harness()
    await flushPromises()
    api.getExecution.mockReturnValue(pending.promise)
    state.selectExecution('old')
    state.clearSelectedExecution()
    pending.resolve({ execution_id: 'old' })
    await flushPromises()
    expect(state.selectedExecution.value).toBeNull()
    expect(state.detailLoading.value).toBe(false)
    wrapper.unmount()
  })

  it('считает весь горизонт, но показывает только три ближайших запуска', async () => {
    api.scheduleWorkspace.mockResolvedValue({ ...workspace(), plan: { lanes: [], windows: Array.from({ length: 8 }, (_, index) => ({ task_type: 'irrigation', trigger_at: `2026-11-03T${String(17 - index).padStart(2, '0')}:00:00Z` })) } })
    const { state, wrapper } = harness()
    await flushPromises()
    expect(state.executableWindows.value).toHaveLength(8)
    expect(state.nextExecutableWindows.value).toHaveLength(3)
    expect(state.nextExecutableWindows.value[0].trigger_at).toBe('2026-11-03T10:00:00Z')
    wrapper.unmount()
  })
})
