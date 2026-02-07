import { describe, expect, it, vi } from 'vitest'
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
    const api = { post: vi.fn().mockResolvedValue({ data: { status: 'ok' } }) }
    const showToast = vi.fn()
    const reloadCenter = vi.fn().mockResolvedValue(undefined)
    const sendZoneCommand = vi.fn().mockResolvedValue(undefined)

    const actions = useCycleCenterActions({ api, showToast, reloadCenter, sendZoneCommand })
    const zone = buildZone()

    await actions.pauseCycle(zone)

    expect(api.post).toHaveBeenCalledWith('/api/grow-cycles/77/pause')
    expect(reloadCenter).toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith('Цикл приостановлен', 'success', expect.any(Number))
    expect(actions.isActionLoading(zone.id, 'pause')).toBe(false)
  })

  it('управляет harvest modal и обрабатывает неуспешный статус', async () => {
    const api = { post: vi.fn().mockResolvedValue({ data: { status: 'fail' } }) }
    const showToast = vi.fn()
    const reloadCenter = vi.fn().mockResolvedValue(undefined)
    const sendZoneCommand = vi.fn().mockResolvedValue(undefined)

    const actions = useCycleCenterActions({ api, showToast, reloadCenter, sendZoneCommand })
    const zone = buildZone()
    actions.openHarvestModal(zone)
    actions.harvestModal.batchLabel = 'BATCH-1'

    await actions.confirmHarvest()

    expect(api.post).toHaveBeenCalledWith('/api/grow-cycles/77/harvest', {
      batch_label: 'BATCH-1',
    })
    expect(showToast).toHaveBeenCalledWith('Не удалось зафиксировать урожай', 'error', expect.any(Number))
    expect(actions.harvestModal.open).toBe(true)
    expect(actions.isActionLoading(zone.id, 'harvest')).toBe(false)
  })
})
