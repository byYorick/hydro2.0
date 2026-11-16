import { describe, expect, it } from 'vitest'
import { estopDeliveryMessage, estopResultMessage, readEstopStatus } from '@/utils/zoneEstop'

describe('E-STOP delivery', () => {
  it('не выдаёт pending и failed за физически выключенные выходы', () => {
    const pending = readEstopStatus({ estop: { active: true, stop_status: 'pending' } })!
    expect(estopResultMessage('engaged', pending)).toContain('Ожидается подтверждение')
    const failed = { ...pending, stop_status: 'failed' as const }
    expect(estopDeliveryMessage(failed)).toContain('не подтверждено')
    expect(estopResultMessage('released')).not.toContain('остаются выключенными')
  })
  it('показывает подтверждение только для confirmed', () => {
    const status = readEstopStatus({ estop: { active: true, stop_status: 'confirmed' } })!
    expect(estopDeliveryMessage(status)).toContain('подтверждено всеми узлами')
  })
})
