import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useZoneCycleActions } from '../useZoneCycleActions'

const harvestMock = vi.hoisted(() => vi.fn())
const harvestsCreateMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    growCycles: {
      harvest: harvestMock,
      pause: vi.fn(),
      resume: vi.fn(),
      abort: vi.fn(),
      advancePhase: vi.fn(),
      changeRecipeRevision: vi.fn(),
    },
    harvests: {
      create: harvestsCreateMock,
    },
  },
}))

function buildActions(cycle: Record<string, unknown> | null = { id: 77, recipe_id: 5 }) {
  const showToast = vi.fn()
  const handleError = vi.fn()
  const reloadZone = vi.fn().mockResolvedValue(undefined)
  const setLoading = vi.fn()
  const actions = useZoneCycleActions({
    activeGrowCycle: ref(cycle),
    zoneId: ref(12),
    reloadZone,
    showToast,
    setLoading,
    handleError,
  })
  return { actions, showToast, handleError, reloadZone, setLoading }
}

describe('useZoneCycleActions', () => {
  it('confirmHarvest без кг закрывает цикл и не пишет harvests', async () => {
    harvestMock.mockReset().mockResolvedValue(undefined)
    harvestsCreateMock.mockReset().mockResolvedValue({})
    const { actions } = buildActions()
    actions.harvestModal.batchLabel = 'BATCH-1'
    actions.harvestModal.yieldKg = ''
    actions.harvestModal.open = true

    await actions.confirmHarvest()

    expect(harvestsCreateMock).not.toHaveBeenCalled()
    expect(harvestMock).toHaveBeenCalledWith(77, { batch_label: 'BATCH-1' })
    expect(actions.harvestModal.open).toBe(false)
  })

  it('confirmHarvest с кг сначала POST /harvests, затем harvest цикла', async () => {
    const order: string[] = []
    harvestsCreateMock.mockReset().mockImplementation(async () => {
      order.push('harvests')
      return { id: 1 }
    })
    harvestMock.mockReset().mockImplementation(async () => {
      order.push('cycle')
    })
    const { actions } = buildActions({
      id: 77,
      recipe_id: 5,
    })
    actions.harvestModal.yieldKg = '4.5'
    actions.harvestModal.batchLabel = 'B-2'
    actions.harvestModal.open = true

    await actions.confirmHarvest()

    expect(order).toEqual(['harvests', 'cycle'])
    expect(harvestsCreateMock).toHaveBeenCalledWith(expect.objectContaining({
      zone_id: 12,
      recipe_id: 5,
      yield_weight_kg: 4.5,
    }))
    expect(String(harvestsCreateMock.mock.calls[0][0].harvest_date)).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(harvestMock).toHaveBeenCalledWith(77, { batch_label: 'B-2' })
    expect(harvestMock.mock.calls[0][1]).not.toHaveProperty('yield_kg')
    expect(harvestMock.mock.calls[0][1]).not.toHaveProperty('yield_weight_kg')
  })

  it('confirmHarvest принимает кг как число из input type=number', async () => {
    harvestsCreateMock.mockReset().mockResolvedValue({ id: 2 })
    harvestMock.mockReset().mockResolvedValue(undefined)
    const { actions } = buildActions()
    actions.harvestModal.yieldKg = 3 as unknown as string
    actions.harvestModal.open = true

    await actions.confirmHarvest()

    expect(harvestsCreateMock).toHaveBeenCalledWith(expect.objectContaining({
      yield_weight_kg: 3,
    }))
    expect(harvestMock).toHaveBeenCalled()
  })

  it('confirmHarvest не закрывает цикл, если POST harvests упал', async () => {
    harvestsCreateMock.mockReset().mockRejectedValue(new Error('fail'))
    harvestMock.mockReset().mockResolvedValue(undefined)
    const { actions, handleError } = buildActions()
    actions.harvestModal.yieldKg = '2'
    actions.harvestModal.open = true

    await actions.confirmHarvest()

    expect(harvestMock).not.toHaveBeenCalled()
    expect(handleError).toHaveBeenCalled()
    expect(actions.harvestModal.open).toBe(true)
  })
})
