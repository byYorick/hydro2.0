import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const roleState = vi.hoisted(() => ({ role: 'agronomist' }))

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn())
const apiPatchMock = vi.hoisted(() => vi.fn())
const routerVisitMock = vi.hoisted(() => vi.fn())
const canAssignToZoneMock = vi.hoisted(() => vi.fn())
const getStateLabelMock = vi.hoisted(() => vi.fn())

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'variant', 'disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

vi.mock('@/Components/Badge.vue', () => ({
  default: {
    name: 'Badge',
    props: ['variant'],
    template: '<span><slot /></span>',
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  Link: { name: 'Link', props: ['href'], template: '<a :href="href"><slot /></a>' },
  usePage: () => ({
    props: {
      auth: {
        user: {
          role: roleState.role,
        },
      },
    },
  }),
  router: {
    visit: routerVisitMock,
  },
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: (url: string, config?: any) => {
        const finalUrl = url.startsWith('/api/') ? url : `/api${url}`
        return apiGetMock(finalUrl, config)
      },
      post: (url: string, data?: any, config?: any) => {
        const finalUrl = url.startsWith('/api/') ? url : `/api${url}`
        return apiPostMock(finalUrl, data, config)
      },
      patch: (url: string, data?: any, config?: any) => {
        const finalUrl = url.startsWith('/api/') ? url : `/api${url}`
        return apiPatchMock(finalUrl, data, config)
      },
    },
  }),
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

vi.mock('@/composables/useNodeLifecycle', () => ({
  useNodeLifecycle: () => ({
    canAssignToZone: canAssignToZoneMock,
    getStateLabel: getStateLabelMock,
  }),
}))

vi.mock('@/composables/useErrorHandler', () => ({
  useErrorHandler: () => ({
    handleError: vi.fn(),
  }),
}))

import Wizard from '../Wizard.vue'

describe('Setup/Wizard.vue', () => {
  beforeEach(() => {
    roleState.role = 'agronomist'
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    apiPatchMock.mockReset()
    routerVisitMock.mockReset()
    canAssignToZoneMock.mockReset()
    getStateLabelMock.mockReset()

    canAssignToZoneMock.mockResolvedValue(true)
    getStateLabelMock.mockReturnValue('Зарегистрирован')

    apiGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [],
      },
    })

    apiPostMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: { id: 1 },
      },
    })

    apiPatchMock.mockImplementation((url: string) => {
      const nodeId = Number(url.split('/').pop())
      return Promise.resolve({
        data: {
          status: 'ok',
          data: {
            id: Number.isFinite(nodeId) ? nodeId : 0,
            zone_id: 20,
            pending_zone_id: null,
            lifecycle_state: 'ASSIGNED_TO_ZONE',
          },
        },
      })
    })
  })

  it('рендерит заголовок и шаги мастера', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    expect(wrapper.text()).toContain('Мастер настройки системы')
    expect(wrapper.text()).toContain('1. Теплица')
    expect(wrapper.text()).toContain('2. Зона')
    expect(wrapper.text()).toContain('3. Культура и рецепт')
    expect(wrapper.text()).toContain('4. Устройства')
    expect(wrapper.text()).toContain('5. Логика автоматики')
    expect(wrapper.text()).toContain('6. Запуск и контроль')
  })

  it('показывает режим только для просмотра для оператора', async () => {
    roleState.role = 'operator'
    const wrapper = mount(Wizard)
    await flushPromises()

    expect(wrapper.text()).toContain('Режим только для просмотра')
  })

  it('создает теплицу в режиме create', async () => {
    apiPostMock.mockResolvedValueOnce({
      data: {
        status: 'ok',
        data: { id: 10, uid: 'gh-main', name: 'Main GH' },
      },
    })

    const wrapper = mount(Wizard)
    await flushPromises()

    const createToggle = wrapper.find('[data-test="toggle-greenhouse-create"]')
    expect(createToggle).toBeTruthy()
    await createToggle.trigger('click')

    const greenhouseNameInput = wrapper.find('input[placeholder="Название теплицы"]')
    expect(greenhouseNameInput.exists()).toBe(true)
    await greenhouseNameInput.setValue('Main GH')

    const createButton = wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))
    expect(createButton).toBeTruthy()
    await createButton?.trigger('click')

    await flushPromises()

    expect(wrapper.find('input[placeholder="Название теплицы"]').exists()).toBe(false)

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/greenhouses',
      expect.objectContaining({
        name: 'Main GH',
      }),
      undefined
    )
  })

  it('применяет логику автоматики через команду зоны', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/plants') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [{ id: 5, name: 'Tomato' }],
          },
        })
      }

      if (url === '/api/recipes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [{
              id: 30,
              name: 'Tomato recipe',
              plants: [{ id: 5, name: 'Tomato' }],
              phases: [{ phase_index: 0, ph_target: 5.9, ec_target: 1.7, irrigation_mode: 'RECIRC' }],
            }],
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    apiPostMock
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 10, uid: 'gh-main', name: 'Main GH' },
        },
      })
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 20, name: 'Zone A', greenhouse_id: 10 },
        },
      })
      .mockResolvedValue({
        data: {
          status: 'ok',
          data: { id: 99 },
        },
      })

    const wrapper = mount(Wizard)
    await flushPromises()

    const createToggle = wrapper.find('[data-test="toggle-greenhouse-create"]')
    await createToggle.trigger('click')

    const greenhouseNameInput = wrapper.find('input[placeholder="Название теплицы"]')
    await greenhouseNameInput.setValue('Main GH')

    const createGreenhouseButton = wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))
    await createGreenhouseButton?.trigger('click')
    await flushPromises()

    const openZoneCreateButton = wrapper.find('[data-test="toggle-zone-create"]')
    expect(openZoneCreateButton).toBeTruthy()
    await openZoneCreateButton.trigger('click')
    await flushPromises()

    const zoneNameInput = wrapper.find('input[placeholder="Название зоны"]')
    expect(zoneNameInput.exists()).toBe(true)
    await zoneNameInput.setValue('Zone A')

    const createZoneButton = wrapper.findAll('button').find((btn) => btn.text().includes('Создать зону'))
    expect(createZoneButton).toBeTruthy()
    await createZoneButton?.trigger('click')
    await flushPromises()

    expect(wrapper.find('input[placeholder="Название зоны"]').exists()).toBe(false)

    const plantSelect = wrapper.findAll('select').find((item) => item.text().includes('Tomato'))
    expect(plantSelect).toBeTruthy()
    await plantSelect?.setValue('5')
    await flushPromises()

    const applyAutomationButton = wrapper.findAll('button').find((btn) => btn.text().includes('Применить логику автоматики'))
    expect(applyAutomationButton).toBeTruthy()
    await applyAutomationButton?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/zones/20/commands',
      expect.objectContaining({
        type: 'GROWTH_CYCLE_CONFIG',
      }),
      undefined
    )
  })

  it('отправляет флаги управления климатом и светом из переключателей', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/plants') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [{ id: 5, name: 'Tomato' }],
          },
        })
      }

      if (url === '/api/recipes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [{
              id: 30,
              name: 'Tomato recipe',
              plants: [{ id: 5, name: 'Tomato' }],
              phases: [{ phase_index: 0, ph_target: 5.9, ec_target: 1.7, irrigation_mode: 'RECIRC' }],
            }],
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    apiPostMock
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 10, uid: 'gh-main', name: 'Main GH' },
        },
      })
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 20, name: 'Zone A', greenhouse_id: 10 },
        },
      })
      .mockResolvedValue({
        data: {
          status: 'ok',
          data: { id: 99 },
        },
      })

    const wrapper = mount(Wizard)
    await flushPromises()

    const createToggle = wrapper.find('[data-test="toggle-greenhouse-create"]')
    await createToggle.trigger('click')
    await wrapper.find('input[placeholder="Название теплицы"]').setValue('Main GH')
    await wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))?.trigger('click')
    await flushPromises()

    await wrapper.find('[data-test="toggle-zone-create"]').trigger('click')
    await flushPromises()
    await wrapper.find('input[placeholder="Название зоны"]').setValue('Zone A')
    await wrapper.findAll('button').find((btn) => btn.text().includes('Создать зону'))?.trigger('click')
    await flushPromises()

    const plantSelect = wrapper.findAll('select').find((item) => item.text().includes('Tomato'))
    expect(plantSelect).toBeTruthy()
    await plantSelect?.setValue('5')
    await flushPromises()

    const climateToggle = wrapper.findAll('label').find((item) => item.text().includes('Управлять климатом'))
    const lightingToggle = wrapper.findAll('label').find((item) => item.text().includes('Управлять освещением'))
    await climateToggle?.find('input').setValue(false)
    await lightingToggle?.find('input').setValue(false)

    await wrapper.findAll('button').find((btn) => btn.text().includes('Применить логику автоматики'))?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/zones/20/commands',
      expect.objectContaining({
        params: expect.objectContaining({
          subsystems: expect.objectContaining({
            climate: expect.objectContaining({ enabled: false }),
            lighting: expect.objectContaining({ enabled: false }),
          }),
        }),
      }),
      undefined
    )
  })

  it('не позволяет запуск до завершения обязательных шагов', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    const openLaunchButton = wrapper.findAll('button').find((btn) => btn.text().includes('Открыть мастер запуска цикла'))
    expect(openLaunchButton).toBeTruthy()
    expect((openLaunchButton?.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('обновляет список доступных нод по кнопке Обновить', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    apiGetMock.mockClear()

    const refreshNodesButton = wrapper.findAll('button').find((btn) => btn.text().includes('Обновить'))
    expect(refreshNodesButton).toBeTruthy()
    await refreshNodesButton?.trigger('click')
    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/nodes', { params: { unassigned: true } })
  })

  it('перед привязкой нод вызывает серверную валидацию обязательных ролей', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/nodes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [
              { id: 101, uid: 'nd-test-irrig-1', type: 'pump_node', channels: [{ channel: 'pump_irrigation' }] },
              { id: 102, uid: 'nd-test-ph-1', type: 'ph_node', channels: [{ channel: 'pump_acid' }, { channel: 'ph_sensor' }] },
              { id: 104, uid: 'nd-test-ec-1', type: 'ec_node', channels: [{ channel: 'pump_a' }, { channel: 'ec_sensor' }] },
              { id: 103, uid: 'nd-test-tank-1', type: 'water_sensor_node', channels: [{ channel: 'water_level' }, { channel: 'pump_in' }] },
            ],
          },
        })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
    })

    apiPostMock
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 10, uid: 'gh-main', name: 'Main GH' },
        },
      })
      .mockResolvedValueOnce({
        data: {
          status: 'ok',
          data: { id: 20, name: 'Zone A', greenhouse_id: 10 },
        },
      })
      .mockResolvedValue({
        data: {
          status: 'ok',
          data: { validated: true },
        },
      })

    apiPatchMock.mockImplementation((url: string) => {
      const nodeId = Number(url.split('/').pop())
      return Promise.resolve({
        data: {
          status: 'ok',
          data: {
            id: Number.isFinite(nodeId) ? nodeId : 0,
            zone_id: 20,
            pending_zone_id: null,
            lifecycle_state: 'ASSIGNED_TO_ZONE',
          },
        },
      })
    })

    const wrapper = mount(Wizard)
    await flushPromises()

    await wrapper.find('[data-test="toggle-greenhouse-create"]').trigger('click')
    await wrapper.find('input[placeholder="Название теплицы"]').setValue('Main GH')
    await wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))?.trigger('click')
    await flushPromises()

    await wrapper.find('[data-test="toggle-zone-create"]').trigger('click')
    await flushPromises()
    await wrapper.find('input[placeholder="Название зоны"]').setValue('Zone A')
    await wrapper.findAll('button').find((btn) => btn.text().includes('Создать зону'))?.trigger('click')
    await flushPromises()

    const irrigationSelect = wrapper.findAll('select').find((item) => item.text().includes('Выберите узел полива'))
    const phCorrectionSelect = wrapper.findAll('select').find((item) => item.text().includes('Выберите узел коррекции pH'))
    const ecCorrectionSelect = wrapper.findAll('select').find((item) => item.text().includes('Выберите узел коррекции EC'))
    const accumulationSelect = wrapper.findAll('select').find((item) => item.text().includes('Выберите накопительный узел'))

    expect(irrigationSelect).toBeTruthy()
    expect(phCorrectionSelect).toBeTruthy()
    expect(ecCorrectionSelect).toBeTruthy()
    expect(accumulationSelect).toBeTruthy()

    await irrigationSelect?.setValue('101')
    await phCorrectionSelect?.setValue('102')
    await ecCorrectionSelect?.setValue('104')
    await accumulationSelect?.setValue('103')

    await wrapper.findAll('button').find((btn) => btn.text().includes('Привязать ноды зоны'))?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/setup-wizard/validate-devices',
      expect.objectContaining({
        zone_id: 20,
        assignments: expect.objectContaining({
          irrigation: 101,
          ph_correction: 102,
          ec_correction: 104,
          accumulation: 103,
        }),
      }),
      undefined
    )

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/setup-wizard/apply-device-bindings',
      expect.objectContaining({
        zone_id: 20,
        assignments: expect.objectContaining({
          irrigation: 101,
          ph_correction: 102,
          ec_correction: 104,
          accumulation: 103,
        }),
      }),
      undefined
    )

    expect(apiPatchMock).toHaveBeenCalledTimes(4)
  })
})
