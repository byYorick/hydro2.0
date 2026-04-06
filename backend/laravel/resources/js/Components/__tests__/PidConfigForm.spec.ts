import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PidConfigForm from '@/Components/PidConfigForm.vue'

const getPidConfigMock = vi.hoisted(() => vi.fn())
const getAllPidConfigsMock = vi.hoisted(() => vi.fn())
const getDocumentMock = vi.hoisted(() => vi.fn())
const updateDocumentMock = vi.hoisted(() => vi.fn())
const apiGetMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/usePidConfig', () => ({
  usePidConfig: () => ({
    getPidConfig: getPidConfigMock,
    getAllPidConfigs: getAllPidConfigsMock,
    loading: ref(false),
  }),
}))

vi.mock('@/composables/useAutomationConfig', () => ({
  useAutomationConfig: () => ({
    getDocument: getDocumentMock,
    updateDocument: updateDocumentMock,
  }),
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: apiGetMock,
    },
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
  },
}))

describe('PidConfigForm.vue', () => {
  beforeEach(() => {
    getPidConfigMock.mockReset()
    getAllPidConfigsMock.mockReset()
    getDocumentMock.mockReset()
    updateDocumentMock.mockReset()
    apiGetMock.mockReset()

    getPidConfigMock.mockResolvedValue({
      type: 'ph',
      config: {
        dead_zone: 0.05,
        close_zone: 0.3,
        far_zone: 1.0,
        zone_coeffs: {
          close: { kp: 5, ki: 0.05, kd: 0 },
          far: { kp: 8, ki: 0.02, kd: 0 },
        },
        max_integral: 20,
      },
      is_default: false,
    })
    getAllPidConfigsMock.mockResolvedValue({ ph: null, ec: null })
    getDocumentMock.mockResolvedValue({
      namespace: 'zone.runtime_tuning_bundle',
      scope_type: 'zone',
      scope_id: 7,
      schema_version: 1,
      payload: {
        selected_preset_key: 'system_default',
        presets: [
          {
            key: 'system_default',
            name: 'Системный preset',
            description: 'PID и process calibration по умолчанию.',
            process_calibration: {
              generic: {},
              solution_fill: {},
              tank_recirc: {},
              irrigation: {},
            },
            pid: {
              ph: {
                dead_zone: 0.04,
                close_zone: 0.18,
                far_zone: 0.65,
                zone_coeffs: {
                  close: { kp: 0.18, ki: 0.01, kd: 0 },
                  far: { kp: 0.28, ki: 0.015, kd: 0 },
                },
                max_integral: 12,
              },
              ec: {
                dead_zone: 0.06,
                close_zone: 0.25,
                far_zone: 0.9,
                zone_coeffs: {
                  close: { kp: 0.35, ki: 0.02, kd: 0 },
                  far: { kp: 0.55, ki: 0.03, kd: 0 },
                },
                max_integral: 20,
              },
            },
          },
        ],
        advanced_overrides: {},
        resolved_preview: {
          process_calibration: {
            generic: {},
            solution_fill: {},
            tank_recirc: {},
            irrigation: {},
          },
          pid: {
            ph: {
              dead_zone: 0.04,
              close_zone: 0.18,
              far_zone: 0.65,
              zone_coeffs: {
                close: { kp: 0.18, ki: 0.01, kd: 0 },
                far: { kp: 0.28, ki: 0.015, kd: 0 },
              },
              max_integral: 12,
            },
            ec: {
              dead_zone: 0.06,
              close_zone: 0.25,
              far_zone: 0.9,
              zone_coeffs: {
                close: { kp: 0.35, ki: 0.02, kd: 0 },
                far: { kp: 0.55, ki: 0.03, kd: 0 },
              },
              max_integral: 20,
            },
          },
        },
      },
      status: 'valid',
      updated_at: '2026-03-17T10:00:00Z',
      updated_by: 5,
    })
    updateDocumentMock.mockImplementation(async (_scopeType: string, _scopeId: number, _namespace: string, payload: Record<string, unknown>) => ({
      namespace: 'zone.runtime_tuning_bundle',
      scope_type: 'zone',
      scope_id: 7,
      schema_version: 1,
      payload,
      status: 'valid',
      updated_at: '2026-03-17T10:00:00Z',
      updated_by: 5,
    }))
    apiGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {},
      },
    })
  })

  it('сохраняет только canonical PID tuning и не отправляет target в PID-документ', async () => {
    const wrapper = mount(PidConfigForm, {
      props: {
        zoneId: 7,
        phaseTargets: {
          ph: 5.7,
          ec: 1.4,
          phaseLabel: 'Вега',
        },
      },
      global: {
        stubs: {
          Card: { template: '<div><slot /></div>' },
          Button: { props: ['disabled', 'type'], template: '<button :disabled="disabled" :type="type || \'button\'"><slot /></button>' },
        },
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="pid-config-toggle-advanced"]').trigger('click')

    const targetInput = wrapper.get('[data-testid="pid-config-input-target"]')
    expect((targetInput.element as HTMLInputElement).value).toBe('5.7')

    await wrapper.get('form').trigger('submit.prevent')

    expect(updateDocumentMock).toHaveBeenCalledWith(
      'zone',
      7,
      'zone.runtime_tuning_bundle',
      expect.objectContaining({
        advanced_overrides: expect.objectContaining({
          pid: expect.objectContaining({
            ph: expect.not.objectContaining({ target: expect.anything() }),
          }),
        }),
      })
    )
    expect(updateDocumentMock).toHaveBeenCalledWith(
      'zone',
      7,
      'zone.runtime_tuning_bundle',
      expect.objectContaining({
        advanced_overrides: expect.objectContaining({
          pid: expect.objectContaining({
            ph: expect.objectContaining({
              dead_zone: 0.05,
              max_integral: 20,
            }),
          }),
        }),
      })
    )
  })

  it('блокирует сохранение, если в актуальной phase нет recipe target', async () => {
    const wrapper = mount(PidConfigForm, {
      props: {
        zoneId: 7,
      },
      global: {
        stubs: {
          Card: { template: '<div><slot /></div>' },
          Button: { props: ['disabled', 'type'], template: '<button :disabled="disabled" :type="type || \'button\'"><slot /></button>' },
        },
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="pid-config-toggle-advanced"]').trigger('click')

    expect(wrapper.find('[data-testid="pid-config-phase-target-missing"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="pid-config-save"]').attributes('disabled')).toBeDefined()
    expect(updateDocumentMock).not.toHaveBeenCalled()
  })
})
