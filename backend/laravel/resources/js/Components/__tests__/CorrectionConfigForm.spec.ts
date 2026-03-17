import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const getZoneCorrectionConfigMock = vi.hoisted(() => vi.fn())
const getZoneCorrectionConfigHistoryMock = vi.hoisted(() => vi.fn())
const updateZoneCorrectionConfigMock = vi.hoisted(() => vi.fn())
const createCorrectionPresetMock = vi.hoisted(() => vi.fn())
const deleteCorrectionPresetMock = vi.hoisted(() => vi.fn())

vi.mock('@/Components/Card.vue', () => ({
  default: {
    name: 'Card',
    template: '<div><slot /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size', 'type'],
    emits: ['click'],
    template: '<button :disabled="disabled" :type="type" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/composables/useCorrectionConfig', () => ({
  useCorrectionConfig: () => ({
    loading: ref(false),
    getZoneCorrectionConfig: getZoneCorrectionConfigMock,
    updateZoneCorrectionConfig: updateZoneCorrectionConfigMock,
    getZoneCorrectionConfigHistory: getZoneCorrectionConfigHistoryMock,
    createCorrectionPreset: createCorrectionPresetMock,
    deleteCorrectionPreset: deleteCorrectionPresetMock,
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

import CorrectionConfigForm from '../CorrectionConfigForm.vue'

const resolvedBase = {
  retry: {
    telemetry_stale_retry_sec: 30,
    decision_window_retry_sec: 30,
    low_water_retry_sec: 60,
  },
  controllers: {
    ph: {
      kp: 5,
      observe: {
        decision_window_sec: 6,
        observe_poll_sec: 2,
        min_effect_fraction: 0.25,
        no_effect_consecutive_limit: 3,
      },
    },
    ec: {
      observe: {
        decision_window_sec: 8,
        observe_poll_sec: 3,
        min_effect_fraction: 0.4,
        no_effect_consecutive_limit: 2,
      },
    },
  },
}

describe('CorrectionConfigForm.vue', () => {
  beforeEach(() => {
    getZoneCorrectionConfigMock.mockReset()
    getZoneCorrectionConfigHistoryMock.mockReset()
    updateZoneCorrectionConfigMock.mockReset()
    createCorrectionPresetMock.mockReset()
    deleteCorrectionPresetMock.mockReset()

    getZoneCorrectionConfigMock.mockResolvedValue({
      id: 1,
      zone_id: 5,
      preset: null,
      base_config: resolvedBase,
      phase_overrides: {
        irrigation: {
          retry: {
            decision_window_retry_sec: 45,
          },
          controllers: {
            ph: {
              kp: 6.5,
              observe: {
                decision_window_sec: 10,
              },
            },
          },
        },
      },
      resolved_config: {
        base: resolvedBase,
        phases: {
          solution_fill: resolvedBase,
          tank_recirc: resolvedBase,
          irrigation: {
            ...resolvedBase,
            retry: {
              ...resolvedBase.retry,
              decision_window_retry_sec: 45,
            },
            controllers: {
              ...resolvedBase.controllers,
              ph: {
                ...resolvedBase.controllers.ph,
                kp: 6.5,
                observe: {
                  ...resolvedBase.controllers.ph.observe,
                  decision_window_sec: 10,
                },
              },
            },
          },
        },
      },
      version: 4,
      updated_at: '2026-03-17T10:00:00Z',
      updated_by: 1,
      last_applied_at: '2026-03-17T10:02:00Z',
      last_applied_version: 4,
      meta: {
        phases: ['solution_fill', 'tank_recirc', 'irrigation'],
        defaults: resolvedBase,
        field_catalog: [
          {
            key: 'retry',
            label: 'Retry and windows',
            description: 'Лимиты correction-loop и временные retry delay.',
            fields: [
              {
                path: 'retry.telemetry_stale_retry_sec',
                label: 'Telemetry stale retry',
                description: 'Повтор при stale telemetry.',
                type: 'integer',
                min: 1,
                max: 3600,
                advanced_only: true,
              },
              {
                path: 'retry.decision_window_retry_sec',
                label: 'Decision window retry',
                description: 'Повтор при неготовом decision window.',
                type: 'integer',
                min: 1,
                max: 3600,
                advanced_only: true,
              },
              {
                path: 'retry.low_water_retry_sec',
                label: 'Low water retry',
                description: 'Повтор после low-water guard.',
                type: 'integer',
                min: 1,
                max: 3600,
                advanced_only: true,
              },
            ],
          },
          {
            key: 'controllers.ph',
            label: 'pH controller',
            description: 'Параметры bounded PI/PID для коррекции pH.',
            fields: [
              {
                path: 'controllers.ph.kp',
                label: 'Kp',
                description: 'Пропорциональная составляющая pH-контроллера.',
                type: 'number',
                min: 0,
                max: 1000,
              },
              {
                path: 'controllers.ph.observe.decision_window_sec',
                label: 'Decision window',
                description: 'Минимальная длина окна наблюдения pH после дозы.',
                type: 'integer',
                min: 1,
                max: 3600,
              },
              {
                path: 'controllers.ph.observe.observe_poll_sec',
                label: 'Observe poll',
                description: 'Повторная проверка окна.',
                type: 'integer',
                min: 1,
                max: 300,
              },
              {
                path: 'controllers.ph.observe.min_effect_fraction',
                label: 'Min effect fraction',
                description: 'Доля ожидаемого эффекта.',
                type: 'number',
                min: 0.01,
                max: 1,
              },
              {
                path: 'controllers.ph.observe.no_effect_consecutive_limit',
                label: 'No-effect consecutive',
                description: 'Порог fail-closed.',
                type: 'integer',
                min: 1,
                max: 10,
              },
            ],
          },
        ],
      },
      available_presets: [],
    })
    getZoneCorrectionConfigHistoryMock.mockResolvedValue([])
  })

  it('показывает runtime-подсказку для observe-loop и fail-closed guard', async () => {
    const wrapper = mount(CorrectionConfigForm, {
      props: { zoneId: 5 },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Process Calibration (transport_delay_sec + settle_sec)')
    expect(wrapper.text()).toContain('decision window 6 сек')
    expect(wrapper.text()).toContain('каждые 2 сек')
    expect(wrapper.text()).toContain('ниже 25% считается no-effect')
    expect(wrapper.text()).toContain('после 3 подряд no-effect correction идёт в fail-closed')
  })

  it('показывает retry delay fields в advanced mode из backend field_catalog', async () => {
    const wrapper = mount(CorrectionConfigForm, {
      props: { zoneId: 5 },
    })

    await flushPromises()
    await wrapper.find('input[type="checkbox"]').setValue(true)

    expect(wrapper.text()).toContain('Retry and windows')
    expect(wrapper.text()).toContain('Telemetry stale retry')
    expect(wrapper.text()).toContain('Decision window retry')
    expect(wrapper.text()).toContain('Low water retry')
  })

  it('показывает effective preview и diff выбранной фазы относительно base', async () => {
    const wrapper = mount(CorrectionConfigForm, {
      props: { zoneId: 5 },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Effective preview: solution_fill')
    expect(wrapper.text()).toContain('Overrides: 0')
    expect(wrapper.text()).toContain('Для этой фазы используется base config без phase override diff.')

    const irrigationButton = wrapper
      .findAll('button')
      .find((button) => button.text() === 'irrigation')

    expect(irrigationButton).toBeTruthy()
    await irrigationButton!.trigger('click')

    expect(wrapper.text()).toContain('Effective preview: irrigation')
    expect(wrapper.text()).toContain('Overrides: 3')
    expect(wrapper.text()).toContain('Sections: 2')
    expect(wrapper.text()).toContain('pH controller')
    expect(wrapper.text()).toContain('Kp: 6,5')
    expect(wrapper.text()).toContain('base 5')
    expect(wrapper.text()).toContain('Decision window: 10')
    expect(wrapper.text()).toContain('base 6')
    expect(wrapper.text()).toContain('Retry and windows')
    expect(wrapper.text()).toContain('Decision window retry45')
    expect(wrapper.text()).toContain('base 30')
  })
})
