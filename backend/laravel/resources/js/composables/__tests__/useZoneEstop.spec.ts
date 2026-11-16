import { flushPromises } from '@vue/test-utils'
import { effectScope, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useZoneEstop } from '@/composables/useZoneEstop'

const getEstop = vi.hoisted(() => vi.fn())
const getSnapshot = vi.hoisted(() => vi.fn())
const applyEstop = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      getEstop: (...args: unknown[]) => getEstop(...args),
      getSnapshot: (...args: unknown[]) => getSnapshot(...args),
      applyEstop: (...args: unknown[]) => applyEstop(...args),
    },
  },
}))

describe('useZoneEstop', () => {
  afterEach(() => vi.useRealTimers())
  beforeEach(() => {
    getEstop.mockReset()
    getEstop.mockImplementation((...args: unknown[]) => getSnapshot(...args))
    getSnapshot.mockReset()
    applyEstop.mockReset()
  })

  it('читает аварийную остановку и пустой датчик раствора из снимка', async () => {
    getSnapshot.mockResolvedValue({
      estop: { active: true, source: 'operator', since: '2026-11-09T10:00:00Z', node_uid: null, event_id: 4 },
      tank_levels: { solution_percent: null, clean_percent: null },
    })

    const zoneId = ref<number | null>(12)
    const estop = useZoneEstop(zoneId)
    await flushPromises()

    expect(getSnapshot).toHaveBeenCalledWith(12)
    expect(estop.active.value).toBe(true)
    expect(estop.solutionPercent.value).toBeNull()
  })

  it('включает и снимает остановку через API зоны', async () => {
    getSnapshot.mockResolvedValue({
      estop: { active: false, source: null, since: null, node_uid: null, event_id: null },
      tank_levels: { solution_percent: 40 },
    })
    applyEstop
      .mockResolvedValueOnce({
        zone_id: 3,
        action: 'engage',
        result: 'engaged',
        estop: { active: true, source: 'operator', since: null, node_uid: null, event_id: 9 },
      })
      .mockResolvedValueOnce({
        zone_id: 3,
        action: 'release',
        result: 'released',
        estop: { active: false, source: null, since: null, node_uid: null, event_id: null },
      })

    const estop = useZoneEstop(ref(3))
    await flushPromises()
    expect(estop.solutionPercent.value).toBe(40)

    const engaged = await estop.engage()
    expect(applyEstop).toHaveBeenCalledWith(3, { action: 'engage' })
    expect(engaged.result).toBe('engaged')
    expect(estop.active.value).toBe(true)

    const released = await estop.release('дым устранён')
    expect(applyEstop).toHaveBeenLastCalledWith(3, { action: 'release', reason: 'дым устранён' })
    expect(released.result).toBe('released')
    expect(estop.active.value).toBe(false)
  })
  it('не применяет задержанный ответ предыдущей зоны', async () => {
    let finishOld!: (value: unknown) => void
    getEstop.mockImplementation((id: number) => id === 1
      ? new Promise((resolve) => { finishOld = resolve })
      : Promise.resolve({ estop: { active: false } }))
    getSnapshot.mockResolvedValue({})
    const id = ref(1)
    const estop = useZoneEstop(id)
    id.value = 2
    await flushPromises()
    finishOld({ estop: { active: true } })
    await flushPromises()
    expect(estop.active.value).toBe(false)
  })

  it('обновляет pending до confirmed и сохраняет блокировку при ошибке API', async () => {
    vi.useFakeTimers()
    getSnapshot.mockResolvedValue({})
    getEstop.mockResolvedValue({ estop: { active: true, stop_status: 'pending' } })
    const scope = effectScope()
    const estop = scope.run(() => useZoneEstop(ref(3)))!
    await flushPromises()
    expect(estop.status.value?.stop_status).toBe('pending')
    getEstop.mockResolvedValue({ estop: { active: true, stop_status: 'confirmed' } })
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(estop.status.value?.stop_status).toBe('confirmed')
    getEstop.mockRejectedValue(new Error('network'))
    await vi.advanceTimersByTimeAsync(3000)
    expect(estop.active.value).toBe(true)
    scope.stop()
    expect(vi.getTimerCount()).toBe(0)
  })

})
