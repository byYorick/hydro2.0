import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CorrectionLiveEditCard from '../ZoneAutomation/CorrectionLiveEditCard.vue'

vi.mock('@/services/api/automationConfigs', () => ({
  automationConfigsApi: {
    get: vi.fn(),
  },
}))

vi.mock('@/services/api/zoneConfigMode', () => ({
  zoneConfigModeApi: {
    show: vi.fn(),
    update: vi.fn(),
    extend: vi.fn(),
    changes: vi.fn(),
    updatePhaseConfig: vi.fn(),
    updateCorrectionLiveEdit: vi.fn(),
  },
}))

import { automationConfigsApi } from '@/services/api/automationConfigs'
import { zoneConfigModeApi } from '@/services/api/zoneConfigMode'

const correctionDocument = {
  zone_id: 7,
  version: 4,
  base_config: {
    timing: { stabilization_sec: 8 },
    retry: { telemetry_stale_retry_sec: 30 },
    controllers: {
      ec: {
        kp: 0.55,
        observe: { decision_window_sec: 8 },
      },
    },
  },
  phase_overrides: {},
  resolved_config: {
    base: {
      timing: { stabilization_sec: 8 },
      retry: { telemetry_stale_retry_sec: 30 },
      controllers: {
        ec: {
          kp: 0.55,
          observe: { decision_window_sec: 8 },
        },
      },
    },
    phases: {
      solution_fill: {
        timing: { stabilization_sec: 9 },
        retry: { telemetry_stale_retry_sec: 30 },
        controllers: {
          ec: {
            kp: 0.57,
            observe: { decision_window_sec: 9 },
          },
        },
      },
      tank_recirc: {
        timing: { stabilization_sec: 10 },
        retry: { telemetry_stale_retry_sec: 32 },
        controllers: {
          ec: {
            kp: 0.6,
            observe: { decision_window_sec: 10 },
          },
        },
      },
      irrigation: {
        timing: { stabilization_sec: 11 },
        retry: { telemetry_stale_retry_sec: 34 },
        controllers: {
          ec: {
            kp: 0.61,
            observe: { decision_window_sec: 11 },
          },
        },
      },
    },
  },
  meta: {
    field_catalog: [
      {
        key: 'timing',
        label: 'Timing',
        description: 'timing section',
        fields: [
          {
            path: 'timing.stabilization_sec',
            label: 'Correction stabilization',
            description: 'wait before corr_check',
            type: 'integer',
            min: 0,
            max: 3600,
          },
        ],
      },
      {
        key: 'retry',
        label: 'Retry',
        description: 'retry section',
        fields: [
          {
            path: 'retry.telemetry_stale_retry_sec',
            label: 'Telemetry stale retry',
            description: 'retry on stale telemetry',
            type: 'integer',
            min: 1,
            max: 3600,
          },
        ],
      },
      {
        key: 'controllers.ec',
        label: 'EC controller',
        description: 'ec controller section',
        fields: [
          {
            path: 'controllers.ec.kp',
            label: 'Kp',
            description: 'ec kp',
            type: 'number',
            min: 0,
            max: 1000,
            step: 0.1,
          },
          {
            path: 'controllers.ec.observe.decision_window_sec',
            label: 'Decision window',
            description: 'observe decision window',
            type: 'integer',
            min: 1,
            max: 3600,
          },
        ],
      },
    ],
  },
}

const calibrationDocument = {
  namespace: 'zone.process_calibration.solution_fill',
  scope_type: 'zone',
  scope_id: 7,
  schema_version: 1,
  status: 'ok',
  updated_at: '2026-04-15T10:00:00Z',
  updated_by: 7,
  payload: {
    transport_delay_sec: 20,
    settle_sec: 45,
    ec_gain_per_ml: 0.11,
    ph_up_gain_per_ml: 0.08,
    ph_down_gain_per_ml: 0.07,
    ph_per_ec_ml: -0.015,
    ec_per_ph_ml: 0.02,
    confidence: 0.9,
  },
}

describe('CorrectionLiveEditCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(automationConfigsApi.get).mockImplementation(async (_scope, _id, namespace) => {
      if (namespace === 'zone.correction') {
        return correctionDocument as never
      }

      return calibrationDocument as never
    })
  })

  it('blocks submit until there is a diff and reason', async () => {
    const wrapper = mount(CorrectionLiveEditCard, { props: { zoneId: 7 } })
    await flushPromises()

    expect(wrapper.text()).toContain('Тонкая настройка correction runtime в режиме live')
    expect(wrapper.text()).toContain('Стабилизация перед corr_check')
    expect(wrapper.text()).toContain('Сколько секунд runtime ждёт после активации сенсоров')

    expect(wrapper.find('[data-testid="correction-live-submit"]').attributes('disabled'))
      .toBeDefined()

    await wrapper.find('[data-testid="correction-live-field-timing__stabilization_sec"]').setValue('12')
    expect(wrapper.find('[data-testid="correction-live-submit"]').attributes('disabled'))
      .toBeDefined()

    await wrapper.find('[data-testid="correction-live-reason"]').setValue('bump timing')
    expect(wrapper.find('[data-testid="correction-live-submit"]').attributes('disabled'))
      .toBeUndefined()
  })

  it('submits base correction patch without phase', async () => {
    vi.mocked(zoneConfigModeApi.updateCorrectionLiveEdit).mockResolvedValue({
      status: 'ok',
      zone_id: 7,
      config_revision: 15,
      phase: null,
      affected_fields: {
        correction: ['timing.stabilization_sec'],
        calibration: [],
      },
    })

    const wrapper = mount(CorrectionLiveEditCard, { props: { zoneId: 7 } })
    await flushPromises()

    await wrapper.find('[data-testid="correction-live-field-timing__stabilization_sec"]').setValue('12')
    await wrapper.find('[data-testid="correction-live-reason"]').setValue('bump timing')
    await wrapper.find('[data-testid="correction-live-form"]').trigger('submit')
    await flushPromises()

    expect(zoneConfigModeApi.updateCorrectionLiveEdit).toHaveBeenCalledWith(7, {
      reason: 'bump timing',
      correction_patch: {
        'timing.stabilization_sec': 12,
      },
    })

    expect(wrapper.find('[data-testid="correction-live-success"]').text()).toContain('ревизия 15')
  })

  it('submits combined phase correction and calibration when phase matches', async () => {
    vi.mocked(zoneConfigModeApi.updateCorrectionLiveEdit).mockResolvedValue({
      status: 'ok',
      zone_id: 7,
      config_revision: 21,
      phase: 'tank_recirc',
      affected_fields: {
        correction: ['controllers.ec.kp'],
        calibration: ['transport_delay_sec'],
      },
    })

    const wrapper = mount(CorrectionLiveEditCard, { props: { zoneId: 7 } })
    await flushPromises()

    await wrapper.find('[data-testid="correction-live-correction-target"]').setValue('tank_recirc')
    await wrapper.find('[data-testid="correction-live-calibration-target"]').setValue('tank_recirc')
    await wrapper.find('[data-testid="correction-live-field-controllers__ec__kp"]').setValue('0.95')
    await wrapper.find('[data-testid="correction-live-calibration-field-transport_delay_sec"]').setValue('28')
    await wrapper.find('[data-testid="correction-live-reason"]').setValue('tank recirc tuning')
    await wrapper.find('[data-testid="correction-live-form"]').trigger('submit')
    await flushPromises()

    expect(zoneConfigModeApi.updateCorrectionLiveEdit).toHaveBeenCalledWith(7, {
      reason: 'tank recirc tuning',
      phase: 'tank_recirc',
      correction_patch: {
        'controllers.ec.kp': 0.95,
      },
      calibration_patch: {
        transport_delay_sec: 28,
      },
    })
  })

  it('prevents conflicting combined submit for base correction and calibration', async () => {
    const wrapper = mount(CorrectionLiveEditCard, { props: { zoneId: 7 } })
    await flushPromises()

    await wrapper.find('[data-testid="correction-live-calibration-target"]').setValue('solution_fill')
    await wrapper.find('[data-testid="correction-live-field-timing__stabilization_sec"]').setValue('12')
    await wrapper.find('[data-testid="correction-live-calibration-field-transport_delay_sec"]').setValue('28')
    await wrapper.find('[data-testid="correction-live-reason"]').setValue('mixed submit')
    await flushPromises()

    expect(wrapper.find('[data-testid="correction-live-submit"]').attributes('disabled'))
      .toBeDefined()
    expect(wrapper.find('[data-testid="correction-live-blocker"]').text())
      .toContain('Базовую correction-конфигурацию и process calibration нельзя отправить одним запросом')
  })
})
