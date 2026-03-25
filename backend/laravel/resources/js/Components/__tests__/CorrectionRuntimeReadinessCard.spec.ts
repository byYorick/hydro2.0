import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const getDocumentMock = vi.hoisted(() => vi.fn())
const getAllPidConfigsMock = vi.hoisted(() => vi.fn())
const getPumpCalibrationsMock = vi.hoisted(() => vi.fn())

vi.mock('@/Components/Card.vue', () => ({
  default: {
    name: 'Card',
    template: '<div><slot /></div>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span><slot /></span>',
  },
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: apiGetMock,
    },
  }),
}))

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    getDocument: getDocumentMock,
  }),
}))

vi.mock('@/composables/usePidConfig', () => ({
  usePidConfig: () => ({
    getAllPidConfigs: getAllPidConfigsMock,
    getPumpCalibrations: getPumpCalibrationsMock,
  }),
}))

import CorrectionRuntimeReadinessCard from '../CorrectionRuntimeReadinessCard.vue'

function calibrationDocument(
  namespace: string,
  payload: Record<string, unknown>,
  scopeId = 42,
) {
  return {
    namespace,
    scope_type: 'zone',
    scope_id: scopeId,
    schema_version: 1,
    payload,
    status: 'valid',
    updated_at: '2026-03-17T10:00:00Z',
    updated_by: 5,
  }
}

function processNamespace(mode: 'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation'): string {
  return `zone.process_calibration.${mode}`
}

function systemDefaultPayload(mode: 'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation') {
  return {
    mode,
    source: 'system_default',
    is_active: true,
    ec_gain_per_ml: 0.11,
    ph_up_gain_per_ml: 0.08,
    ph_down_gain_per_ml: 0.07,
    ph_per_ec_ml: -0.015,
    ec_per_ph_ml: 0.02,
    transport_delay_sec: 20,
    settle_sec: 45,
    confidence: 0.75,
  }
}

function savedPayload(mode: 'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation', confidence: number) {
  return {
    ...systemDefaultPayload(mode),
    source: 'learned',
    confidence,
  }
}

function installProcessDocuments(overrides: Partial<Record<'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation', Record<string, unknown>>>) {
  getDocumentMock.mockImplementation((_scopeType: string, _scopeId: number, namespace: string) => {
    if (namespace === processNamespace('generic')) {
      return Promise.resolve(calibrationDocument(namespace, overrides.generic ?? systemDefaultPayload('generic')))
    }

    if (namespace === processNamespace('solution_fill')) {
      return Promise.resolve(calibrationDocument(namespace, overrides.solution_fill ?? systemDefaultPayload('solution_fill')))
    }

    if (namespace === processNamespace('tank_recirc')) {
      return Promise.resolve(calibrationDocument(namespace, overrides.tank_recirc ?? systemDefaultPayload('tank_recirc')))
    }

    if (namespace === processNamespace('irrigation')) {
      return Promise.resolve(calibrationDocument(namespace, overrides.irrigation ?? systemDefaultPayload('irrigation')))
    }

    return Promise.reject(new Error(`Unexpected namespace ${namespace}`))
  })
}

describe('CorrectionRuntimeReadinessCard.vue', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    getDocumentMock.mockReset()
    getAllPidConfigsMock.mockReset()
    getPumpCalibrationsMock.mockReset()

    installProcessDocuments({})

    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/zones/42/events') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [],
          },
        })
      }

      return Promise.reject(new Error(`Unexpected url: ${url}`))
    })
  })

  it('показывает готовность с generic fallback, когда насосы откалиброваны', async () => {
    installProcessDocuments({
      generic: savedPayload('generic', 0.82),
    })
    getAllPidConfigsMock.mockResolvedValue({
      ph: { type: 'ph', config: { dead_zone: 0.05 }, is_default: false },
      ec: { type: 'ec', config: { dead_zone: 0.1 }, is_default: false },
    })
    getPumpCalibrationsMock.mockResolvedValue([
      { role: 'ph_acid_pump', ml_per_sec: 0.5 },
      { role: 'ph_base_pump', ml_per_sec: 0.5 },
      { role: 'ec_npk_pump', ml_per_sec: 1.0 },
      { role: 'ec_calcium_pump', ml_per_sec: 1.0 },
      { role: 'ec_magnesium_pump', ml_per_sec: 0.8 },
      { role: 'ec_micro_pump', ml_per_sec: 0.8 },
    ])

    const wrapper = mount(CorrectionRuntimeReadinessCard, {
      props: { zoneId: 42 },
    })

    await flushPromises()

    expect(getDocumentMock).toHaveBeenCalledWith('zone', 42, 'zone.process_calibration.generic')
    expect(apiGetMock).toHaveBeenCalledWith('/api/zones/42/events', {
      params: {
        limit: 80,
      },
    })
    expect(getAllPidConfigsMock).toHaveBeenCalledWith(42)
    expect(getPumpCalibrationsMock).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('Готово с fallback')
    expect(wrapper.text()).toContain('Через generic')
    expect(wrapper.text()).toContain('Все обязательные насосы откалиброваны.')
    expect(wrapper.text()).toContain('PID pH')
    expect(wrapper.text()).toContain('PID EC')
  })

  it('показывает fail-closed и отсутствующие pump calibration', async () => {
    installProcessDocuments({})
    getAllPidConfigsMock.mockResolvedValue({
      ph: { type: 'ph', config: { dead_zone: 0.05 }, is_default: false },
      ec: { type: 'ec', config: { dead_zone: 0.1 }, is_default: false },
    })
    getPumpCalibrationsMock.mockResolvedValue([
      { role: 'ph_acid_pump', ml_per_sec: 0.4 },
      { role: 'ph_base_pump', ml_per_sec: null },
      { role: 'ec_npk_pump', ml_per_sec: null },
    ])

    const wrapper = mount(CorrectionRuntimeReadinessCard, {
      props: { zoneId: 42 },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Блокировано')
    expect(wrapper.text()).toContain('process calibration: Наполнение, Рециркуляция, Полив')
    expect(wrapper.text()).toContain('Для этой фазы не заданы ни отдельная, ни generic-калибровка процесса')
    expect(wrapper.text()).toContain('насос pH щёлочи')
    expect(wrapper.text()).toContain('насос EC NPK')
  })

  it('эмитит действия для исправления process и pump gaps', async () => {
    installProcessDocuments({})
    getAllPidConfigsMock.mockResolvedValue({
      ph: { type: 'ph', config: { dead_zone: 0.05 }, is_default: true },
      ec: { type: 'ec', config: { dead_zone: 0.1 }, is_default: false },
    })
    getPumpCalibrationsMock.mockResolvedValue([
      { role: 'ph_acid_pump', ml_per_sec: null },
    ])

    const wrapper = mount(CorrectionRuntimeReadinessCard, {
      props: { zoneId: 42 },
    })

    await flushPromises()

    await wrapper.find('[data-testid="correction-readiness-process-btn"]').trigger('click')
    await wrapper.find('[data-testid="correction-readiness-pump-btn"]').trigger('click')
    await wrapper.find('[data-testid="correction-readiness-pid-btn"]').trigger('click')

    expect(wrapper.emitted('focus-process-calibration')).toBeTruthy()
    expect(wrapper.emitted('open-pump-calibration')).toBeTruthy()
    expect(wrapper.emitted('focus-pid-config')).toBeTruthy()
  })

  it('показывает последние runtime blockers и эмитит action из них', async () => {
    installProcessDocuments({
      solution_fill: savedPayload('solution_fill', 0.91),
      tank_recirc: savedPayload('tank_recirc', 0.88),
      irrigation: savedPayload('irrigation', 0.84),
    })
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/zones/42/events') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [
              {
                id: 13,
                type: 'CORRECTION_NO_EFFECT',
                message: 'Коррекция: нет наблюдаемого эффекта (EC, эффект 0.0200 < 0.1000, лимит 3)',
                occurred_at: '2026-03-17T10:10:00Z',
                payload: {
                  pid_type: 'ec',
                  actual_effect: 0.02,
                  threshold_effect: 0.1,
                  no_effect_limit: 3,
                },
              },
              {
                id: 12,
                type: 'CORRECTION_SKIPPED_WINDOW_NOT_READY',
                message: 'Коррекция: окно наблюдения не готово (observe window, EC, insufficient_samples, повтор через 2 с)',
                occurred_at: '2026-03-17T10:09:30Z',
                payload: {
                  sensor_scope: 'observe_window',
                  sensor_type: 'EC',
                  reason: 'insufficient_samples',
                  retry_after_sec: 2,
                },
              },
              {
                id: 11,
                type: 'CORRECTION_SKIPPED_FRESHNESS',
                message: 'Коррекция: устаревшие данные (observe window, EC, повтор через 30 с)',
                occurred_at: '2026-03-17T10:09:00Z',
                payload: {
                  sensor_scope: 'observe_window',
                  sensor_type: 'EC',
                  retry_after_sec: 30,
                },
              },
            ],
          },
        })
      }

      return Promise.reject(new Error(`Unexpected url: ${url}`))
    })
    getAllPidConfigsMock.mockResolvedValue({
      ph: { type: 'ph', config: { dead_zone: 0.05 }, is_default: false },
      ec: { type: 'ec', config: { dead_zone: 0.1 }, is_default: false },
    })
    getPumpCalibrationsMock.mockResolvedValue([
      { role: 'ph_acid_pump', ml_per_sec: 0.5 },
      { role: 'ph_base_pump', ml_per_sec: 0.5 },
      { role: 'ec_npk_pump', ml_per_sec: 1.0 },
      { role: 'ec_calcium_pump', ml_per_sec: 1.0 },
      { role: 'ec_magnesium_pump', ml_per_sec: 0.8 },
      { role: 'ec_micro_pump', ml_per_sec: 0.8 },
    ])

    const wrapper = mount(CorrectionRuntimeReadinessCard, {
      props: { zoneId: 42 },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Последние runtime blockers')
    expect(wrapper.text()).toContain('Correction не дал наблюдаемого эффекта')
    expect(wrapper.text()).toContain('Окно наблюдения correction ещё не готово')
    expect(wrapper.text()).toContain('Недостаточно свежих данных для correction')
    expect(wrapper.text()).toContain('Проверьте pump calibration и реальный dosing path')
    expect(wrapper.text()).toContain('Проверьте частоту telemetry и параметры observe-window')
    expect(wrapper.text()).toContain('Проверьте поток и окно наблюдения')

    await wrapper.find('[data-testid="correction-issue-action-13"]').trigger('click')
    await wrapper.find('[data-testid="correction-issue-action-12"]').trigger('click')

    expect(wrapper.emitted('open-pump-calibration')).toBeTruthy()
    expect(wrapper.emitted('focus-process-calibration')).toBeTruthy()
  })
})
