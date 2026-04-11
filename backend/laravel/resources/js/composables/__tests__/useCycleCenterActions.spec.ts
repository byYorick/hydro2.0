import { describe, expect, it, vi } from 'vitest'

const pauseMock = vi.hoisted(() => vi.fn())
const resumeMock = vi.hoisted(() => vi.fn())
const harvestMock = vi.hoisted(() => vi.fn())
const abortMock = vi.hoisted(() => vi.fn())
const startIrrigationMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    growCycles: {
      pause: pauseMock,
      resume: resumeMock,
      harvest: harvestMock,
      abort: abortMock,
    },
    zones: {
      startIrrigation: startIrrigationMock,
    },
  },
}))

import { useCycleCenterActions } from '../useCycleCenterActions'
import type { ZoneSummary } from '../useCycleCenterView'

function buildZone(overrides: Partial<ZoneSummary> = {}): ZoneSummary {
  return {
    id: 1,
    name: 'Zone-1',
    status: 'RUNNING',
    greenhouse: { id: 1, name: 'GH-1' },
    telemetry: {
      ph: 6,
      ec: 1.5,
      temperature: 22,
      humidity: 60,
      co2: 700,
      updated_at: '2026-01-01T10:00:00Z',
    },
    alerts_count: 0,
    alerts_preview: [],
    devices: { total: 2, online: 2 },
    recipe: null,
    plant: null,
    cycle: { id: 77, status: 'RUNNING' },
    ...overrides,
  }
}

describe('useCycleCenterActions', () => {
  it('pauseCycle выставляет loading и завершает его после успеха', async () => {
    pauseMock.mockReset().mockResolvedValue(undefined)
    const showToast = vi.fn()
    const reloadCenter = vi.fn().mockResolvedValue(undefined)

    const actions = useCycleCenterActions({ showToast, reloadCenter })
    const zone = buildZone()

    await actions.pauseCycle(zone)

    expect(pauseMock).toHaveBeenCalledWith(77)
    expect(reloadCenter).toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith('Цикл приостановлен', 'success', expect.any(Number))
    expect(actions.isActionLoading(zone.id, 'pause')).toBe(false)
  })

  it('управляет harvest modal и обрабатывает неуспешный статус', async () => {
    harvestMock.mockReset().mockRejectedValue(new Error('Не удалось зафиксировать урожай'))
    const showToast = vi.fn()
    const reloadCenter = vi.fn().mockResolvedValue(undefined)

    const actions = useCycleCenterActions({ showToast, reloadCenter })
    const zone = buildZone()
    actions.openHarvestModal(zone)
    actions.harvestModal.batchLabel = 'BATCH-1'

    await actions.confirmHarvest()

    expect(harvestMock).toHaveBeenCalledWith(77, { batch_label: 'BATCH-1' })
    expect(showToast).toHaveBeenCalledWith('Не удалось зафиксировать урожай', 'error', expect.any(Number))
    expect(actions.harvestModal.open).toBe(true)
    expect(actions.isActionLoading(zone.id, 'harvest')).toBe(false)
  })

  it('submitAction запускает normal irrigation через public endpoint', async () => {
    startIrrigationMock.mockReset().mockResolvedValue(undefined)
    const showToast = vi.fn()
    const reloadCenter = vi.fn().mockResolvedValue(undefined)
    const actions = useCycleCenterActions({ showToast, reloadCenter })
    const zone = buildZone()

    actions.openActionModal(zone, 'START_IRRIGATION')
    await actions.submitAction({
      actionType: 'START_IRRIGATION',
      params: { duration_sec: 45 },
    })

    expect(startIrrigationMock).toHaveBeenCalledWith(1, {
      mode: 'normal',
      source: 'cycle_center',
      requested_duration_sec: 45,
    })
    expect(showToast).toHaveBeenCalledWith('Запущен обычный полив', 'success', expect.any(Number))
    expect(reloadCenter).toHaveBeenCalled()
    expect(actions.actionModal.open).toBe(false)
  })

  it('submitAction запускает force irrigation через тот же AE3 endpoint', async () => {
    startIrrigationMock.mockReset().mockResolvedValue(undefined)
    const showToast = vi.fn()
    const reloadCenter = vi.fn().mockResolvedValue(undefined)
    const actions = useCycleCenterActions({ showToast, reloadCenter })
    const zone = buildZone()

    actions.openActionModal(zone, 'FORCE_IRRIGATION')
    await actions.submitAction({
      actionType: 'FORCE_IRRIGATION',
      params: { duration_sec: 90 },
    })

    expect(startIrrigationMock).toHaveBeenCalledWith(1, {
      mode: 'force',
      source: 'cycle_center',
      requested_duration_sec: 90,
    })
    expect(showToast).toHaveBeenCalledWith('Запущена forced-промывка', 'success', expect.any(Number))
    expect(reloadCenter).toHaveBeenCalled()
  })
})
