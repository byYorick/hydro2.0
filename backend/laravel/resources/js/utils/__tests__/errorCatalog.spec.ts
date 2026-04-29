import { describe, expect, it } from 'vitest'

import { resolveHumanErrorMessage } from '../errorCatalog'

describe('errorCatalog', () => {
  it('локализует код start_cycle_zone_busy', () => {
    expect(resolveHumanErrorMessage({
      code: 'start_cycle_zone_busy',
      message: 'Intent skipped: zone busy',
    })).toBe('Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.')
  })

  it('локализует код start_irrigation_setup_pending', () => {
    expect(resolveHumanErrorMessage({
      code: 'start_irrigation_setup_pending',
      message: 'Zone is not ready',
    })).toBe('Полив отклонён: зона ещё не готова. Сначала завершите setup/cycle_start.')
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

  it('локализует unknown irrigation strategy через каталог кодов', () => {
    expect(resolveHumanErrorMessage({
      code: 'irrigation_decision_strategy_unknown',
      message: 'Irrigation decision-controller returned fail.',
    })).toBe('Для зоны указана неизвестная стратегия decision-controller полива. Проверьте automation profile и logic profile зоны.')
  })

  it('локализует потерю lease зоны во время выполнения задачи', () => {
    expect(resolveHumanErrorMessage({
      message: 'Zone lease was lost during task execution',
    })).toBe('Во время выполнения задачи был потерян lease зоны.')
  })

  it('локализует таймаут ожидания READY перед поливом', () => {
    expect(resolveHumanErrorMessage({
      message: 'Irrigation request timed out while waiting for READY state',
    })).toBe('Истекло время ожидания перехода зоны в состояние READY перед поливом.')
  })

  it('локализует ошибки planner runtime spec', () => {
    expect(resolveHumanErrorMessage({
      message: 'Missing required correction_config field: correction.runtime.telemetry_max_age_sec',
    })).toBe('Отсутствует обязательное поле correction_config.')
  })

  it('берёт русское описание новых fail-safe кодов из каталога', () => {
    expect(resolveHumanErrorMessage({
      code: 'solution_fill_leak_detected',
      message: 'Solution minimum level dropped during solution fill',
    })).toBe('Наполнение раствором остановлено: нижний уровень раствора пропал после guard-delay, возможна утечка или неправильная гидравлика.')
  })

  it('локализует ошибки recovery command gateway', () => {
    expect(resolveHumanErrorMessage({
      message: 'Task 41 has no ae_command for recovery',
    })).toBe('У задачи отсутствует связанная ae_command для recovery.')
  })
})
