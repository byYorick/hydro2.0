import { flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useZoneEstop } from '@/composables/useZoneEstop'

const getSnapshot = vi.hoisted(() => vi.fn())
const applyEstop = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      getSnapshot: (...args: unknown[]) => getSnapshot(...args),
      applyEstop: (...args: unknown[]) => applyEstop(...args),
    },
  },
}))

describe('useZoneEstop', () => {
  beforeEach(() => {
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
})
