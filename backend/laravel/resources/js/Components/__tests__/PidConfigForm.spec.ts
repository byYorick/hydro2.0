import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PidConfigForm from '@/Components/PidConfigForm.vue'

const getPidConfigMock = vi.hoisted(() => vi.fn())
const getAllPidConfigsMock = vi.hoisted(() => vi.fn())
const updatePidConfigMock = vi.hoisted(() => vi.fn())
const apiGetMock = vi.hoisted(() => vi.fn())

vi.mock('@/composables/usePidConfig', () => ({
  usePidConfig: () => ({
    getPidConfig: getPidConfigMock,
    getAllPidConfigs: getAllPidConfigsMock,
    updatePidConfig: updatePidConfigMock,
    loading: ref(false),
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
    updatePidConfigMock.mockReset()
    apiGetMock.mockReset()

    getPidConfigMock.mockResolvedValue({
      type: 'ph',
      config: {
        target: 9.9,
        dead_zone: 0.05,
        close_zone: 0.3,
        far_zone: 1.0,
        zone_coeffs: {
          close: { kp: 5, ki: 0.05, kd: 0 },
          far: { kp: 8, ki: 0.02, kd: 0 },
        },
        max_output: 20,
        min_interval_ms: 90_000,
        max_integral: 20,
      },
      is_default: false,
    })
    getAllPidConfigsMock.mockResolvedValue({ ph: null, ec: null })
    updatePidConfigMock.mockImplementation(async (_zoneId: number, type: 'ph' | 'ec', config: Record<string, unknown>) => ({
      type,
      config,
      is_default: false,
    }))
    apiGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {},
      },
    })
  })

  it('сохраняет target из recipe phase, а не из существующего PID-документа', async () => {
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

    const targetInput = wrapper.get('[data-testid="pid-config-input-target"]')
    expect((targetInput.element as HTMLInputElement).value).toBe('5.7')

    await wrapper.get('form').trigger('submit.prevent')

    expect(updatePidConfigMock).toHaveBeenCalledWith(
      7,
      'ph',
      expect.objectContaining({ target: 5.7 })
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

    expect(wrapper.find('[data-testid="pid-config-phase-target-missing"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="pid-config-save"]').attributes('disabled')).toBeDefined()
    expect(updatePidConfigMock).not.toHaveBeenCalled()
  })
})
