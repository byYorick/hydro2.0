import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const zoneEventsMock = vi.hoisted(() => vi.fn())
const getDocumentMock = vi.hoisted(() => vi.fn())
const updateDocumentMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())

vi.mock('@/Components/Card.vue', () => ({
  default: {
    name: 'Card',
    template: '<div><slot /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<div><slot /></div>',
  },
}))

vi.mock('@/services/api', () => ({
  api: {
    zones: {
      events: zoneEventsMock,
    },
  },
}))

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    getDocument: getDocumentMock,
    updateDocument: updateDocumentMock,
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}))

import ProcessCalibrationPanel from '../ProcessCalibrationPanel.vue'

function calibration(mode: 'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation', overrides: Record<string, unknown> = {}) {
  return {
    mode,
    source: 'learned',
    valid_from: '2026-03-17T10:00:00Z',
    is_active: true,
    ec_gain_per_ml: 0.11,
    ph_up_gain_per_ml: 0.08,
    ph_down_gain_per_ml: 0.07,
    ph_per_ec_ml: -0.015,
    ec_per_ph_ml: 0.02,
    transport_delay_sec: 20,
    settle_sec: 45,
    confidence: 0.91,
    ...overrides,
  }
}

function calibrationDocument(
  namespace: string,
  payload: Record<string, unknown>,
  scopeType: 'system' | 'zone' = 'zone',
  scopeId = 7,
) {
  return {
    namespace,
    scope_type: scopeType,
    scope_id: scopeId,
    schema_version: 1,
    payload,
    status: 'valid',
    updated_at: '2026-03-17T10:00:00Z',
    updated_by: 5,
  }
}

function defaultsDocument() {
  return calibrationDocument('system.process_calibration_defaults', {
    ec_gain_per_ml: 0.11,
    ph_up_gain_per_ml: 0.08,
    ph_down_gain_per_ml: 0.07,
    ph_per_ec_ml: -0.015,
    ec_per_ph_ml: 0.02,
    transport_delay_sec: 20,
    settle_sec: 45,
    confidence: 0.75,
  }, 'system', 0)
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

function runtimeTuningBundleDocument(overrides: Partial<Record<'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation', Record<string, unknown>>> = {}) {
  const processCalibration = {
    generic: overrides.generic ?? systemDefaultPayload('generic'),
    solution_fill: overrides.solution_fill ?? systemDefaultPayload('solution_fill'),
    tank_recirc: overrides.tank_recirc ?? systemDefaultPayload('tank_recirc'),
    irrigation: overrides.irrigation ?? systemDefaultPayload('irrigation'),
  }

  return calibrationDocument('zone.runtime_tuning_bundle', {
    selected_preset_key: 'system_default',
    presets: [
      {
        key: 'system_default',
        name: 'Системный preset',
        description: 'Канонические стартовые значения process calibration и PID для зоны.',
        process_calibration: processCalibration,
        pid: {
          ph: { dead_zone: 0.04, close_zone: 0.18, far_zone: 0.65, zone_coeffs: { close: { kp: 0.18, ki: 0.01, kd: 0 }, far: { kp: 0.28, ki: 0.015, kd: 0 } }, max_integral: 12 },
          ec: { dead_zone: 0.06, close_zone: 0.25, far_zone: 0.9, zone_coeffs: { close: { kp: 0.35, ki: 0.02, kd: 0 }, far: { kp: 0.55, ki: 0.03, kd: 0 } }, max_integral: 20 },
        },
      },
    ],
    advanced_overrides: {},
    resolved_preview: {
      process_calibration: processCalibration,
      pid: {
        ph: { dead_zone: 0.04, close_zone: 0.18, far_zone: 0.65, zone_coeffs: { close: { kp: 0.18, ki: 0.01, kd: 0 }, far: { kp: 0.28, ki: 0.015, kd: 0 } }, max_integral: 12 },
        ec: { dead_zone: 0.06, close_zone: 0.25, far_zone: 0.9, zone_coeffs: { close: { kp: 0.35, ki: 0.02, kd: 0 }, far: { kp: 0.55, ki: 0.03, kd: 0 } }, max_integral: 20 },
      },
    },
  })
}

function installDocumentMocks(overrides: Partial<Record<'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation', Record<string, unknown>>>) {
  getDocumentMock.mockImplementation((_scopeType: string, _scopeId: number, namespace: string) => {
    if (namespace === 'system.process_calibration_defaults') {
      return Promise.resolve(defaultsDocument())
    }

    if (namespace === 'zone.runtime_tuning_bundle') {
      return Promise.resolve(runtimeTuningBundleDocument(overrides))
    }

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

    return Promise.reject(new Error(`Unexpected document namespace ${namespace}`))
  })
}

describe('ProcessCalibrationPanel.vue', () => {
  beforeEach(() => {
    zoneEventsMock.mockReset()
    getDocumentMock.mockReset()
    updateDocumentMock.mockReset()
    showToastMock.mockReset()

    installDocumentMocks({
      solution_fill: calibration('solution_fill'),
    })

    zoneEventsMock.mockResolvedValue([])

    updateDocumentMock.mockResolvedValue(
      runtimeTuningBundleDocument({
        solution_fill: calibration('solution_fill'),
      })
    )
  })

  it('использует materialized system default для solution_fill и показывает observation window', async () => {
    installDocumentMocks({
      generic: calibration('generic'),
      solution_fill: systemDefaultPayload('solution_fill'),
    })

    const wrapper = mount(ProcessCalibrationPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()

    expect(getDocumentMock).toHaveBeenCalledWith('zone', 7, 'zone.process_calibration.solution_fill')
    expect(wrapper.text()).toContain('Режим: Наполнение')
    expect(wrapper.text()).toContain('transport_delay_sec + settle_sec = 65 сек')
    expect(wrapper.text()).toContain('Доверие: 0.75')
  })

  it('подставляет системные дефолты в пустую форму, если сохранённой калибровки ещё нет', async () => {
    installDocumentMocks({})

    const wrapper = mount(ProcessCalibrationPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()
    await wrapper.get('[data-testid="process-calibration-toggle-advanced"]').trigger('click')

    const inputs = wrapper.findAll('input')
    expect(inputs[0]?.element).toHaveProperty('value', '20')
    expect(inputs[1]?.element).toHaveProperty('value', '45')
    expect(inputs[2]?.element).toHaveProperty('value', '0.11')
    expect(inputs[7]?.element).toHaveProperty('value', '0.75')
    expect(wrapper.text()).toContain('Материализованные bootstrap defaults уже считаются валидной стартовой калибровкой.')
    expect(wrapper.text()).toContain('Источник: системные значения по умолчанию')
    expect(wrapper.text()).toContain('Доверие: 0.75')
  })

  it('не отправляет save при выходе за диапазон и показывает warning toast', async () => {
    const wrapper = mount(ProcessCalibrationPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()
    await wrapper.get('[data-testid="process-calibration-toggle-advanced"]').trigger('click')

    const confidenceInput = wrapper.find('input[min="0"][max="1"]')
    await confidenceInput.setValue('2')

    const saveButton = wrapper.findAll('button').find((button) => button.text().includes('Сохранить'))
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(updateDocumentMock).not.toHaveBeenCalled()
    expect(showToastMock).toHaveBeenCalledWith('Проверь диапазоны process calibration.', 'warning')
    expect(wrapper.text()).toContain('Доверие к калибровке: диапазон 0..1')
  })

  it('сохраняет текущий режим и перезагружает calibrations', async () => {
    let currentSolutionFill = calibration('solution_fill')
    getDocumentMock.mockImplementation((_scopeType: string, _scopeId: number, namespace: string) => {
      if (namespace === 'system.process_calibration_defaults') {
        return Promise.resolve(defaultsDocument())
      }

      if (namespace === 'zone.runtime_tuning_bundle') {
        return Promise.resolve(runtimeTuningBundleDocument({
          solution_fill: currentSolutionFill,
        }))
      }

      if (namespace === processNamespace('solution_fill')) {
        return Promise.resolve(calibrationDocument(namespace, currentSolutionFill))
      }

      const mode = namespace.split('.').at(-1) as 'generic' | 'solution_fill' | 'tank_recirc' | 'irrigation'
      return Promise.resolve(calibrationDocument(namespace, systemDefaultPayload(mode)))
    })
    updateDocumentMock.mockResolvedValue(
      runtimeTuningBundleDocument({
        solution_fill: calibration('solution_fill', { confidence: 0.5, transport_delay_sec: 30 }),
      })
    )

    const wrapper = mount(ProcessCalibrationPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()
    await wrapper.get('[data-testid="process-calibration-toggle-advanced"]').trigger('click')

    await wrapper.find('input[min="0"][max="120"]').setValue('30')
    await wrapper.find('input[min="0"][max="1"]').setValue('0.5')
    currentSolutionFill = calibration('solution_fill', { confidence: 0.5, transport_delay_sec: 30 })

    const saveButton = wrapper.findAll('button').find((button) => button.text().includes('Сохранить'))
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(updateDocumentMock).toHaveBeenCalledWith('zone', 7, 'zone.runtime_tuning_bundle', expect.objectContaining({
      advanced_overrides: expect.objectContaining({
        process_calibration: expect.objectContaining({
          solution_fill: expect.objectContaining({
            mode: 'solution_fill',
            transport_delay_sec: 30,
            confidence: 0.5,
            source: 'manual',
          }),
        }),
      }),
    }))
    expect(showToastMock).toHaveBeenCalledWith('Калибровка процесса для режима "Наполнение" сохранена.', 'success')
    expect(wrapper.text()).toContain('transport_delay_sec + settle_sec = 75 сек')
  })

  it('показывает историю сохранений для активного режима', async () => {
    installDocumentMocks({
      tank_recirc: calibration('tank_recirc', { confidence: 0.74 }),
    })
    zoneEventsMock.mockResolvedValue([
      {
        event_id: 12,
        type: 'PROCESS_CALIBRATION_SAVED',
        message: 'Process calibration обновлена (tank_recirc): окно 20+45 сек, confidence 0.91, EC=0.110',
        created_at: '2026-03-17T10:20:00Z',
        payload: {
          mode: 'tank_recirc',
          source: 'hil_manual',
          confidence: 0.91,
          transport_delay_sec: 20,
          settle_sec: 45,
        },
      },
      {
        event_id: 11,
        type: 'PROCESS_CALIBRATION_SAVED',
        message: 'Process calibration обновлена (generic): окно 18+30 сек, confidence 0.75, EC=0.090',
        created_at: '2026-03-17T09:00:00Z',
        payload: {
          mode: 'generic',
          source: 'manual',
          confidence: 0.75,
          transport_delay_sec: 18,
          settle_sec: 30,
        },
      },
    ])

    const wrapper = mount(ProcessCalibrationPanel, {
      props: { zoneId: 7 },
    })

    await flushPromises()

    await wrapper.get('[data-testid="process-calibration-mode-tank_recirc"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('История calibration')
    expect(wrapper.text()).toContain('Process calibration обновлена (tank_recirc): окно 20+45 сек, confidence 0.91, EC=0.110')
    expect(wrapper.text()).toContain('Источник: hil_manual')
    expect(wrapper.text()).toContain('Окно: 20+45 сек')
    expect(wrapper.text()).not.toContain('Process calibration обновлена (generic): окно 18+30 сек, confidence 0.75, EC=0.090')
  })
})
