import { describe, expect, it } from 'vitest'

import { resolveHumanErrorMessage } from '../errorCatalog'

describe('errorCatalog', () => {
  it('локализует код start_cycle_zone_busy', () => {
    expect(resolveHumanErrorMessage({
      code: 'start_cycle_zone_busy',
      message: 'Intent skipped: zone busy',
    })).toBe('Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.')
  })

  it('возвращает уже локализованное сообщение без изменений', () => {
    expect(resolveHumanErrorMessage({
      code: 'command_timeout',
      message: 'Команда не успела завершиться вовремя.',
    })).toBe('Команда не успела завершиться вовремя.')
  })

  it('берёт русское описание snapshot-ошибки из каталога кодов', () => {
    expect(resolveHumanErrorMessage({
      code: 'ae3_snapshot_no_online_actuator_channels',
      message: 'Zone 1 has no online actuator channels',
    })).toBe('В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.')
  })

  it('умеет локализовать legacy raw-message без кода', () => {
    expect(resolveHumanErrorMessage({
      message: 'Zone 1 has no online actuator channels',
    })).toBe('В зоне нет ни одного онлайн-исполнительного канала. Проверьте привязки устройств и состояние нод.')
  })

  it('даёт русский fallback для неизвестного кода', () => {
    expect(resolveHumanErrorMessage({
      code: 'some_unknown_error',
      message: 'Unknown failure',
    })).toBe('Внутренняя ошибка системы (код: some_unknown_error).')
  })
})
