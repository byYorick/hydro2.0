import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const getDocumentMock = vi.hoisted(() => vi.fn())
const updateDocumentMock = vi.hoisted(() => vi.fn())
const resetDocumentMock = vi.hoisted(() => vi.fn())
const showToastMock = vi.hoisted(() => vi.fn())

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['disabled', 'variant', 'size', 'type'],
    emits: ['click'],
    template: '<button :disabled="disabled" :type="type" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div><slot /></div>' },
}))

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    getDocument: getDocumentMock,
    updateDocument: updateDocumentMock,
    resetDocument: resetDocumentMock,
    loading: ref(false),
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: showToastMock,
  }),
}))

import SystemSettings from '../SystemSettings.vue'

function makeDocument(namespace: string, payload: Record<string, unknown>) {
  return {
    namespace,
    scope_type: 'system',
    scope_id: 0,
    schema_version: 1,
    payload,
    status: 'valid',
    updated_at: '2026-03-24T10:00:00Z',
    updated_by: 5,
    meta: {
      defaults: payload,
      field_catalog: [
        {
          key: 'general',
          label: 'General',
          description: 'General settings',
          fields: Object.keys(payload).map((path) => ({
            path,
            label: path,
            description: `${path} description`,
            type: typeof payload[path] === 'boolean'
              ? 'boolean'
              : (Number.isInteger(payload[path]) ? 'integer' : 'number'),
          })),
        },
      ],
    },
  }
}

describe('SystemSettings.vue', () => {
  beforeEach(() => {
    vi.spyOn(window, 'confirm').mockReset().mockReturnValue(true)
    getDocumentMock.mockReset()
    updateDocumentMock.mockReset()
    resetDocumentMock.mockReset()
    showToastMock.mockReset()

    getDocumentMock.mockImplementation((_scopeType: string, _scopeId: number, namespace: string) => {
      if (namespace === 'system.pump_calibration_policy') {
        return Promise.resolve(makeDocument(namespace, {
          ml_per_sec_min: 0.01,
          calibration_duration_max_sec: 120,
        }))
      }

      return Promise.resolve(makeDocument(namespace, {
        sample_value: 1,
      }))
    })
    updateDocumentMock.mockResolvedValue(makeDocument('system.pump_calibration_policy', {
      ml_per_sec_min: 0.25,
      calibration_duration_max_sec: 120,
    }))
    resetDocumentMock.mockResolvedValue(makeDocument('system.pump_calibration_policy', {
      ml_per_sec_min: 0.01,
      calibration_duration_max_sec: 120,
    }))
  })

  it('загружает все system authority namespaces через useAutomationConfig', async () => {
    mount(SystemSettings)

    await flushPromises()

    const namespaces = getDocumentMock.mock.calls.map((call) => call[2]).sort()

    expect(namespaces).toEqual([
      'system.automation_defaults',
      'system.command_templates',
      'system.observability_thresholds',
      'system.process_calibration_defaults',
      'system.pump_calibration_policy',
      'system.sensor_calibration_policy',
    ].sort())
  })

  it('сохраняет и сбрасывает активный namespace через authority document API', async () => {
    const wrapper = mount(SystemSettings)

    await flushPromises()

    const pumpTab = wrapper.find('[data-testid="system-settings-tab-pump_calibration"]')
    await pumpTab.trigger('click')
    await flushPromises()

    const inputs = wrapper.findAll('input')
    await inputs[0]?.setValue('0.25')
    const saveButton = wrapper.findAll('button').find((button) => button.text() === 'Сохранить')
    await saveButton?.trigger('click')
    await flushPromises()

    expect(updateDocumentMock).toHaveBeenCalledWith(
      'system',
      0,
      'system.pump_calibration_policy',
      {
        ml_per_sec_min: 0.25,
        calibration_duration_max_sec: 120,
      },
    )

    const resetButton = wrapper.findAll('button').find((button) => button.text() === 'Восстановить значения по умолчанию')
    await resetButton?.trigger('click')
    await flushPromises()

    expect(resetDocumentMock).toHaveBeenCalledWith('system', 0, 'system.pump_calibration_policy')
  })
  it('does not turn an empty numeric field into zero on save', async () => {
    const wrapper = mount(SystemSettings)
    await flushPromises()
    await wrapper.findAll('input')[0].setValue('')
    expect(wrapper.text()).toContain('Введите число.')
    expect(wrapper.get('[data-testid="system-settings-save"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="system-settings-save"]').trigger('click')
    expect(updateDocumentMock).not.toHaveBeenCalled()
  })

  it('keeps the draft when the user cancels switching sections and can discard explicitly', async () => {
    const wrapper = mount(SystemSettings)
    await flushPromises()
    await wrapper.get('[data-testid="system-settings-tab-pump_calibration"]').trigger('click')
    await flushPromises()
    await wrapper.findAll('input')[0].setValue('0.25')
    vi.mocked(window.confirm).mockReturnValue(false)
    await wrapper.get('[data-testid="system-settings-tab-automation_defaults"]').trigger('click')
    expect(window.confirm).toHaveBeenCalled()
    expect(wrapper.findAll('input')[0].element.value).toBe('0.25')
    expect(wrapper.get('[data-testid="system-settings-dirty-count"]').text()).toContain('1')
    await wrapper.get('[data-testid="system-settings-discard"]').trigger('click')
    expect(wrapper.findAll('input')[0].element.value).toBe('0.01')
    expect(wrapper.find('[data-testid="system-settings-dirty-count"]').exists()).toBe(false)
  })

  it('shows a persistent loading failure rather than an empty settings screen', async () => {
    getDocumentMock.mockRejectedValue(new Error('Не удалось получить настройки'))
    const wrapper = mount(SystemSettings)
    await flushPromises()
    expect(wrapper.text()).toContain('Настройки не загружены')
    expect(wrapper.text()).toContain('Повторить загрузку')
  })

})
