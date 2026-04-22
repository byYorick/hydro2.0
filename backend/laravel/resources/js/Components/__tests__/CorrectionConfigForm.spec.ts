import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const getDocumentMock = vi.hoisted(() => vi.fn())
const getHistoryMock = vi.hoisted(() => vi.fn())
const updateDocumentMock = vi.hoisted(() => vi.fn())
const createPresetMock = vi.hoisted(() => vi.fn())
const updatePresetMock = vi.hoisted(() => vi.fn())
const deletePresetMock = vi.hoisted(() => vi.fn())
const listPresetsMock = vi.hoisted(() => vi.fn())

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
    template: '<button :disabled="disabled" :type="type" @click="$emit(\'click\', $event)"><slot /></button>',
  },
}))

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    loading: ref(false),
    getDocument: getDocumentMock,
    getHistory: getHistoryMock,
    updateDocument: updateDocumentMock,
    createPreset: createPresetMock,
    updatePreset: updatePresetMock,
    deletePreset: deletePresetMock,
    listPresets: listPresetsMock,
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

const systemPreset = {
  id: 11,
  slug: 'system-default',
  name: 'System Default',
  scope: 'system',
  is_locked: true,
  is_active: false,
  description: 'System preset description',
  config: {
    base: resolvedBase,
    phases: {
      solution_fill: resolvedBase,
      tank_recirc: resolvedBase,
      irrigation: resolvedBase,
    },
  },
  created_by: null,
  updated_by: null,
  updated_at: '2026-03-17T09:50:00Z',
}

const customPreset = {
  id: 22,
  slug: 'custom-aggressive',
  name: 'Custom Aggressive',
  scope: 'custom',
  is_locked: false,
  is_active: false,
  description: 'Custom preset description',
  config: {
    base: {
      ...resolvedBase,
      controllers: {
        ...resolvedBase.controllers,
        ph: {
          ...resolvedBase.controllers.ph,
          kp: 7.1,
        },
      },
    },
    phases: {
      solution_fill: resolvedBase,
      tank_recirc: resolvedBase,
      irrigation: {
        ...resolvedBase,
        retry: {
          ...resolvedBase.retry,
          decision_window_retry_sec: 55,
        },
      },
    },
  },
  created_by: 5,
  updated_by: 5,
  updated_at: '2026-03-17T09:55:00Z',
}

const baseHistory = [
  {
    id: 1001,
    version: 4,
    change_type: 'updated',
    preset: { id: systemPreset.id, name: systemPreset.name },
    changed_at: '2026-03-17T10:01:00Z',
  },
]

function makeDocument(overrides: Record<string, unknown> = {}) {
  return {
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
    available_presets: [systemPreset, customPreset],
    ...overrides,
  }
}

describe('CorrectionConfigForm.vue', () => {
  beforeEach(() => {
    getDocumentMock.mockReset()
    getHistoryMock.mockReset()
    updateDocumentMock.mockReset()
    createPresetMock.mockReset()
    updatePresetMock.mockReset()
    deletePresetMock.mockReset()
    listPresetsMock.mockReset()

    getDocumentMock.mockResolvedValue(makeDocument())
    getHistoryMock.mockResolvedValue(baseHistory)
    listPresetsMock.mockResolvedValue([systemPreset, customPreset])
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

    const preview = wrapper.get('[data-testid="phase-effective-preview"]')

    // По умолчанию активен таб solution_fill
    expect(preview.text()).toContain('Итоговое состояние runtime')
    expect(preview.text()).toContain('фаза: solution_fill')

    // Переключаемся на фазу irrigation через таб
    await wrapper.get('[data-testid="correction-config-tab-irrigation"]').trigger('click')

    expect(preview.text()).toContain('фаза: irrigation')
    expect(preview.text()).toMatch(/\d+ переопределений/)
    expect(preview.text()).toMatch(/\d+ секций затронуто/)
    expect(preview.text()).toContain('pH controller')
    expect(preview.text()).toContain('Kp')
    expect(preview.text()).toContain('Decision window')
    expect(preview.text()).toContain('Retry and windows')
    // Для overridden строк рендерится базовое значение рядом (class cc-preview__base)
    expect(preview.html()).toContain('cc-preview__row--overridden')
    expect(preview.html()).toContain('cc-preview__base')
  })

  it('рендерит authority history, обновляет его после сохранения и эмитит saved', async () => {
    getHistoryMock
      .mockResolvedValueOnce(baseHistory)
      .mockResolvedValueOnce([
        {
          id: 1002,
          version: 5,
          change_type: 'updated',
          preset: { id: customPreset.id, name: customPreset.name },
          changed_at: '2026-03-17T10:05:00Z',
        },
      ])
    updateDocumentMock.mockResolvedValue(makeDocument({
      version: 5,
      updated_at: '2026-03-17T10:05:00Z',
      last_applied_version: 5,
    }))

    const wrapper = mount(CorrectionConfigForm, {
      props: { zoneId: 5 },
      global: {
        stubs: { teleport: true },
      },
    })

    await flushPromises()

    // История живёт в teleport-drawer'е, открывается кнопкой
    await wrapper.get('[data-testid="correction-config-history-open"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('v4')
    expect(wrapper.text()).toContain('updated')
    expect(wrapper.text()).toContain('System Default')

    // Поля base_config рендерятся только при активном табе base
    await wrapper.get('[data-testid="correction-config-tab-base"]').trigger('click')
    await wrapper.get('[data-testid="correction-config-base-controllers.ph.kp"]').setValue('7.25')
    await wrapper.get('[data-testid="correction-config-save"]').trigger('click')
    await flushPromises()

    expect(updateDocumentMock).toHaveBeenCalledWith(
      'zone',
      5,
      'zone.correction',
      expect.objectContaining({
        preset_id: null,
        base_config: expect.objectContaining({
          controllers: expect.objectContaining({
            ph: expect.objectContaining({
              kp: 7.25,
            }),
          }),
        }),
        phase_overrides: expect.any(Object),
      }),
    )
    expect(getHistoryMock).toHaveBeenCalledTimes(2)
    expect(wrapper.emitted('saved')).toHaveLength(1)

    expect(wrapper.text()).toContain('v5')
    expect(wrapper.text()).toContain('Custom Aggressive')

    wrapper.unmount()
  })

  it('поддерживает preset CRUD через authority API без legacy helper paths', async () => {
    const newPreset = {
      id: 33,
      slug: 'custom-balanced',
      name: 'Custom Balanced',
      scope: 'custom',
      is_locked: false,
      is_active: false,
      description: 'Balanced preset',
      payload: {
        base: resolvedBase,
        phases: {
          solution_fill: resolvedBase,
          tank_recirc: resolvedBase,
          irrigation: resolvedBase,
        },
      },
      updated_by: 5,
      updated_at: '2026-03-17T10:06:00Z',
    }

    createPresetMock.mockResolvedValue(newPreset)
    updatePresetMock.mockResolvedValue({
      ...customPreset,
      updated_at: '2026-03-17T10:07:00Z',
    })
    deletePresetMock.mockResolvedValue(undefined)

    const wrapper = mount(CorrectionConfigForm, {
      props: { zoneId: 5 },
      global: {
        stubs: { teleport: true },
      },
    })

    await flushPromises()

    // ===== UPDATE =====
    // Активируем custom-пресет через pill — это откроет возможность update
    await wrapper.get(`[data-testid="correction-config-preset-${customPreset.id}"]`).trigger('click')
    await flushPromises()
    // Меняем поле base_config — кнопка update видна только для custom scope
    await wrapper.get('[data-testid="correction-config-tab-base"]').trigger('click')
    await wrapper.get('[data-testid="correction-config-base-controllers.ph.kp"]').setValue('8.4')
    await wrapper.get('[data-testid="correction-config-update-preset"]').trigger('click')
    await flushPromises()

    expect(updatePresetMock).toHaveBeenCalledWith(customPreset.id, expect.objectContaining({
      payload: expect.objectContaining({
        base: expect.any(Object),
        phases: expect.any(Object),
      }),
    }))

    // ===== DELETE =====
    await wrapper.get('[data-testid="correction-config-preset-menu"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="correction-config-delete-preset"]').trigger('click')
    await flushPromises()

    expect(deletePresetMock).toHaveBeenCalledWith(customPreset.id)

    // ===== CREATE =====
    await wrapper.get('[data-testid="correction-config-new-preset"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="correction-config-new-preset-name"]').setValue('Custom Balanced')
    await wrapper.get('[data-testid="correction-config-new-preset-description"]').setValue('Balanced preset')
    await wrapper.get('[data-testid="correction-config-save-preset"]').trigger('click')
    await flushPromises()

    expect(createPresetMock).toHaveBeenCalledWith('zone.correction', expect.objectContaining({
      name: 'Custom Balanced',
      description: 'Balanced preset',
      payload: expect.objectContaining({
        base: expect.any(Object),
        phases: expect.any(Object),
      }),
    }))

    wrapper.unmount()
  })
})
