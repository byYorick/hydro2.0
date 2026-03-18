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

vi.mock('@/Components/GreenhouseClimateConfiguration.vue', () => ({
  default: {
    name: 'GreenhouseClimateConfiguration',
    props: ['enabled', 'applying'],
    emits: ['update:enabled', 'apply'],
    template: `
      <div data-test="greenhouse-climate-stub">
        <label>
          Управлять климатом
          <input
            data-test="greenhouse-climate-toggle"
            :checked="enabled"
            type="checkbox"
            @change="$emit('update:enabled', $event.target.checked)"
          />
        </label>
        <button data-test="apply-greenhouse-climate" @click="$emit('apply')">save greenhouse climate</button>
      </div>
    `,
  },
}))

vi.mock('@/Components/ZoneAutomationProfileSections.vue', () => ({
  default: {
    name: 'ZoneAutomationProfileSections',
    props: ['assignments', 'lightingForm', 'zoneClimateForm'],
    template: `
      <div data-test="zone-automation-sections">
        <label>
          Управлять освещением
          <input
            data-test="lighting-toggle"
            :checked="lightingForm.enabled"
            type="checkbox"
            @change="lightingForm.enabled = $event.target.checked"
          />
        </label>
        <label>
          Управлять климатом зоны
          <input
            data-test="zone-climate-toggle"
            :checked="zoneClimateForm.enabled"
            type="checkbox"
            @change="zoneClimateForm.enabled = $event.target.checked"
          />
        </label>
        <select data-test="irrigation-select" :value="assignments.irrigation ?? ''" @change="assignments.irrigation = Number($event.target.value) || null">
          <option value="">none</option>
          <option value="101">irrig</option>
        </select>
        <select data-test="ph-select" :value="assignments.ph_correction ?? ''" @change="assignments.ph_correction = Number($event.target.value) || null">
          <option value="">none</option>
          <option value="102">ph</option>
        </select>
        <select data-test="ec-select" :value="assignments.ec_correction ?? ''" @change="assignments.ec_correction = Number($event.target.value) || null">
          <option value="">none</option>
          <option value="104">ec</option>
        </select>
        <select data-test="light-select" :value="assignments.light ?? ''" @change="assignments.light = Number($event.target.value) || null">
          <option value="">none</option>
          <option value="105">light</option>
        </select>
        <select data-test="co2-sensor-select" :value="assignments.co2_sensor ?? ''" @change="assignments.co2_sensor = Number($event.target.value) || null">
          <option value="">none</option>
          <option value="106">co2</option>
        </select>
      </div>
    `,
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
      sensorCalibrationSettings: null,
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
    warn: vi.fn(),
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

function mockDefaultGet(url: string) {
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
          phases: [{
            phase_index: 0,
            ph_target: 5.9,
            ec_target: 1.7,
            irrigation_mode: 'RECIRC',
            extensions: {
              subsystems: {
                irrigation: {
                  targets: {
                    system_type: 'substrate_trays',
                  },
                },
              },
            },
          }],
        }],
      },
    })
  }

  if (url === '/api/nodes') {
    return Promise.resolve({
      data: {
        status: 'ok',
        data: [
          { id: 101, uid: 'nd-irrig-1', type: 'irrig', channels: [{ channel: 'pump_irrigation' }] },
          { id: 102, uid: 'nd-ph-1', type: 'ph', channels: [{ channel: 'pump_acid' }, { channel: 'ph_sensor' }] },
          { id: 104, uid: 'nd-ec-1', type: 'ec', channels: [{ channel: 'pump_a' }, { channel: 'ec_sensor' }] },
          { id: 105, uid: 'nd-light-1', type: 'light', channels: [{ channel: 'light_main' }] },
          { id: 106, uid: 'nd-co2-1', type: 'climate', channels: [{ channel: 'co2_ppm' }] },
        ],
      },
    })
  }

  return Promise.resolve({
    data: {
      status: 'ok',
      data: [],
    },
  })
}

async function createGreenhouseAndZone(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('[data-test="toggle-greenhouse-create"]').trigger('click')
  await wrapper.find('input[placeholder="Название теплицы"]').setValue('Main GH')
  await wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))?.trigger('click')
  await flushPromises()

  await wrapper.find('[data-test="toggle-zone-create"]').trigger('click')
  await flushPromises()
  await wrapper.find('input[placeholder="Название зоны"]').setValue('Zone A')
  await wrapper.findAll('button').find((btn) => btn.text().includes('Создать зону'))?.trigger('click')
  await flushPromises()
}

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

    apiGetMock.mockImplementation((url: string) => mockDefaultGet(url))

    apiPostMock.mockImplementation((url: string) => {
      if (url === '/api/greenhouses') {
        return Promise.resolve({
          data: { status: 'ok', data: { id: 10, uid: 'gh-main', name: 'Main GH' } },
        })
      }

      if (url === '/api/zones') {
        return Promise.resolve({
          data: { status: 'ok', data: { id: 20, name: 'Zone A', greenhouse_id: 10 } },
        })
      }

      return Promise.resolve({
        data: { status: 'ok', data: { id: 99 } },
      })
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

  it('рендерит заголовок и новый набор шагов мастера', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    expect(wrapper.text()).toContain('Мастер настройки системы')
    expect(wrapper.text()).toContain('1. Теплица')
    expect(wrapper.text()).toContain('2. Зона')
    expect(wrapper.text()).toContain('3. Культура и рецепт')
    expect(wrapper.text()).toContain('4. Автоматизация и устройства зоны')
    expect(wrapper.text()).toContain('5. Запуск')
    expect(wrapper.text()).not.toContain('6. Запуск и контроль')
  })

  it('показывает inline-блок климата после выбора теплицы', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    await createGreenhouseAndZone(wrapper)

    expect(wrapper.find('[data-test="greenhouse-climate-stub"]').exists()).toBe(true)
  })

  it('показывает режим только для просмотра для оператора', async () => {
    roleState.role = 'operator'
    const wrapper = mount(Wizard)
    await flushPromises()

    expect(wrapper.text()).toContain('Режим только для просмотра')
  })

  it('создаёт теплицу в режиме create', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    await wrapper.find('[data-test="toggle-greenhouse-create"]').trigger('click')
    await wrapper.find('input[placeholder="Название теплицы"]').setValue('Main GH')
    await wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/greenhouses',
      expect.objectContaining({
        name: 'Main GH',
      }),
      undefined,
    )
  })

  it('сохраняет unified шаг зоны: bindings + automation profile + команду', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    await createGreenhouseAndZone(wrapper)

    const plantSelect = wrapper.findAll('select').find((item) => item.text().includes('Tomato'))
    await plantSelect?.setValue('5')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('Используется рецепт: Tomato recipe')

    await wrapper.find('[data-test="lighting-toggle"]').setValue(false)
    await wrapper.find('[data-test="irrigation-select"]').setValue('101')
    await wrapper.find('[data-test="ph-select"]').setValue('102')
    await wrapper.find('[data-test="ec-select"]').setValue('104')
    await flushPromises()

    await wrapper.findAll('button').find((btn) => btn.text().includes('Сохранить автоматику и устройства зоны'))?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/setup-wizard/validate-devices',
      expect.objectContaining({
        zone_id: 20,
        assignments: expect.objectContaining({
          irrigation: 101,
          accumulation: 101,
          ph_correction: 102,
          ec_correction: 104,
        }),
      }),
      undefined,
    )

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/zones/20/automation-logic-profile',
      expect.objectContaining({
        mode: 'setup',
        activate: true,
        subsystems: expect.objectContaining({
          lighting: expect.objectContaining({ enabled: false }),
        }),
      }),
      undefined,
    )

    const automationCall = apiPostMock.mock.calls.find(([url]) => url === '/api/zones/20/automation-logic-profile')
    expect(automationCall?.[1]?.subsystems?.climate).toBeUndefined()
    expect(automationCall?.[1]?.subsystems?.irrigation?.execution?.system_type).toBe('substrate_trays')

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/zones/20/commands',
      expect.objectContaining({
        type: 'GROWTH_CYCLE_CONFIG',
        params: expect.objectContaining({
          mode: 'adjust',
          profile_mode: 'setup',
        }),
      }),
      undefined,
    )
  })

  it('отправляет флаги света и zone climate из объединённого шага', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    await createGreenhouseAndZone(wrapper)

    const plantSelect = wrapper.findAll('select').find((item) => item.text().includes('Tomato'))
    await plantSelect?.setValue('5')
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('Используется рецепт: Tomato recipe')

    await wrapper.find('[data-test="lighting-toggle"]').setValue(false)
    await wrapper.find('[data-test="zone-climate-toggle"]').setValue(true)
    await wrapper.find('[data-test="irrigation-select"]').setValue('101')
    await wrapper.find('[data-test="ph-select"]').setValue('102')
    await wrapper.find('[data-test="ec-select"]').setValue('104')
    await wrapper.find('[data-test="co2-sensor-select"]').setValue('106')
    await flushPromises()

    await wrapper.findAll('button').find((btn) => btn.text().includes('Сохранить автоматику и устройства зоны'))?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/zones/20/automation-logic-profile',
      expect.objectContaining({
        subsystems: expect.objectContaining({
          lighting: expect.objectContaining({ enabled: false }),
          zone_climate: expect.objectContaining({ enabled: true }),
        }),
      }),
      undefined,
    )
  })

  it('не позволяет запуск до завершения обязательных шагов', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    const openLaunchButton = wrapper.findAll('button').find((btn) => btn.text().includes('Открыть мастер запуска цикла'))
    expect(openLaunchButton).toBeTruthy()
    expect((openLaunchButton?.element as HTMLButtonElement).disabled).toBe(true)
  })

  it('обновляет список доступных нод по кнопке "Обновить ноды"', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()
    await createGreenhouseAndZone(wrapper)

    apiGetMock.mockClear()

    await wrapper.findAll('button').find((btn) => btn.text().includes('Обновить ноды'))?.trigger('click')
    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/api/nodes', {
      params: {
        zone_id: 20,
        include_unassigned: true,
      },
    })
  })
})
