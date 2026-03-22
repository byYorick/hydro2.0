import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const roleState = vi.hoisted(() => ({ role: 'agronomist' }))
const pagePropsState = vi.hoisted(() => ({ sensorCalibrationSettings: null as Record<string, unknown> | null }))
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

vi.mock('@/Components/ZoneCorrectionCalibrationStack.vue', () => ({
  default: {
    name: 'ZoneCorrectionCalibrationStack',
    props: ['showRuntimeReadiness'],
    emits: ['open-pump-calibration'],
    template: '<div data-test="zone-correction-calibration-stack">{{ showRuntimeReadiness }}<button data-test="open-pump-calibration" @click="$emit(\'open-pump-calibration\')">open pump</button></div>',
  },
}))

vi.mock('@/Components/CorrectionRuntimeReadinessCard.vue', () => ({
  default: {
    name: 'CorrectionRuntimeReadinessCard',
    emits: ['focus-process-calibration', 'open-pump-calibration'],
    template: '<div data-test="correction-runtime-readiness-card">runtime readiness</div>',
  },
}))

vi.mock('@/Components/PumpCalibrationModal.vue', () => ({
  default: {
    name: 'PumpCalibrationModal',
    props: ['show', 'zoneId', 'devices', 'loadingRun', 'loadingSave', 'saveSuccessSeq'],
    emits: ['close', 'start', 'save'],
    template: '<div data-test="pump-calibration-modal">pump calibration modal</div>',
  },
}))

vi.mock('@/Components/ZoneAutomationProfileSections.vue', () => ({
  default: {
    name: 'ZoneAutomationProfileSections',
    props: [
      'layoutMode',
      'assignments',
      'lightingForm',
      'zoneClimateForm',
      'showRequiredDevicesSection',
      'showWaterContourSection',
      'showIrrigationSection',
      'showSolutionCorrectionSection',
      'showLightingSection',
      'showLightingEnableToggle',
      'showZoneClimateSection',
      'showZoneClimateEnableToggle',
      'showNodeBindings',
    ],
    emits: ['save-section'],
    template: `
      <div data-test="zone-automation-sections">
        <label v-if="showLightingEnableToggle !== false">
          Управлять освещением
          <input
            data-test="lighting-toggle"
            :checked="lightingForm.enabled"
            type="checkbox"
            @change="lightingForm.enabled = $event.target.checked"
          />
        </label>
        <label v-if="showZoneClimateEnableToggle !== false">
          Управлять климатом зоны
          <input
            data-test="zone-climate-toggle"
            :checked="zoneClimateForm.enabled"
            type="checkbox"
            @change="zoneClimateForm.enabled = $event.target.checked"
          />
        </label>
        <select
          v-if="showRequiredDevicesSection !== false || layoutMode === 'zone_blocks'"
          data-test="irrigation-select"
          :value="assignments.irrigation ?? ''"
          @change="assignments.irrigation = Number($event.target.value) || null"
        >
          <option value="">none</option>
          <option value="101">irrig</option>
        </select>
        <select
          v-if="showRequiredDevicesSection !== false || layoutMode === 'zone_blocks'"
          data-test="ph-select"
          :value="assignments.ph_correction ?? ''"
          @change="assignments.ph_correction = Number($event.target.value) || null"
        >
          <option value="">none</option>
          <option value="102">ph</option>
        </select>
        <select
          v-if="showRequiredDevicesSection !== false || layoutMode === 'zone_blocks'"
          data-test="ec-select"
          :value="assignments.ec_correction ?? ''"
          @change="assignments.ec_correction = Number($event.target.value) || null"
        >
          <option value="">none</option>
          <option value="104">ec</option>
        </select>
        <select
          v-if="showLightingSection !== false && showNodeBindings"
          data-test="light-select"
          :value="assignments.light ?? ''"
          @change="assignments.light = Number($event.target.value) || null"
        >
          <option value="">none</option>
          <option value="105">light</option>
        </select>
        <select
          v-if="showZoneClimateSection !== false && showNodeBindings"
          data-test="co2-sensor-select"
          :value="assignments.co2_sensor ?? ''"
          @change="assignments.co2_sensor = Number($event.target.value) || null"
        >
          <option value="">none</option>
          <option value="106">co2</option>
        </select>
        <button
          v-if="showRequiredDevicesSection !== false"
          data-test="save-section-required-devices"
          @click="$emit('save-section', 'required_devices')"
        >save required</button>
        <button
          v-if="showWaterContourSection !== false"
          data-test="save-section-water-contour"
          @click="$emit('save-section', 'water_contour')"
        >save contour</button>
        <button
          v-if="showLightingSection !== false"
          data-test="save-section-lighting"
          @click="$emit('save-section', 'lighting')"
        >save lighting</button>
        <button
          v-if="showZoneClimateSection !== false"
          data-test="save-section-zone-climate"
          @click="$emit('save-section', 'zone_climate')"
        >save zone climate</button>
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
      sensorCalibrationSettings: pagePropsState.sensorCalibrationSettings,
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
    pagePropsState.sensorCalibrationSettings = null
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
    expect(wrapper.text()).toContain('4. Автоматика зоны')
    expect(wrapper.text()).toContain('5. Калибровка')
    expect(wrapper.text()).toContain('6. Проверка и запуск')
    expect(wrapper.text()).not.toContain('4. Устройства нод зоны')
    expect(wrapper.text()).not.toContain('5. Профиль автоматики')
  })

  it('открывает модалку калибровки насосов из шага 5', async () => {
    pagePropsState.sensorCalibrationSettings = {
      ph_point_1_value: 7,
      ph_point_2_value: 4.01,
      ec_point_1_tds: 1413,
      ec_point_2_tds: 707,
      reminder_days: 30,
      critical_days: 90,
      command_timeout_sec: 10,
      ph_reference_min: 1,
      ph_reference_max: 12,
      ec_tds_reference_max: 10000,
    }

    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/nodes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [
              { id: 101, uid: 'nd-irrig-bound', type: 'controller', zone_id: '20', channels: [{ binding_role: 'main_pump' }] },
              { id: 102, uid: 'nd-ph-bound', type: 'controller', zone_id: '20', channels: [{ binding_role: 'ph_acid_pump' }] },
              { id: 104, uid: 'nd-ec-bound', type: 'controller', zone_id: '20', channels: [{ binding_role: 'ec_npk_pump' }] },
            ],
          },
        })
      }

      return mockDefaultGet(url)
    })

    const wrapper = mount(Wizard)
    await flushPromises()
    await createGreenhouseAndZone(wrapper)
    await wrapper.findAll('select.input-select')[2]?.setValue('5')
    await flushPromises()
    await wrapper.find('[data-test="lighting-toggle"]').setValue(false)
    await wrapper.find('[data-test="irrigation-select"]').setValue('101')
    await wrapper.find('[data-test="ph-select"]').setValue('102')
    await wrapper.find('[data-test="ec-select"]').setValue('104')
    await flushPromises()
    await wrapper.get('[data-test="save-section-water-contour"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-test="open-pump-calibration"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="pump-calibration-modal"]').exists()).toBe(true)
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

  it('сохраняет блок водного контура: bindings и automation profile', async () => {
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

    await wrapper.find('[data-test="save-section-water-contour"]').trigger('click')
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
      }),
      undefined,
    )
  })

  it('подтягивает уже привязанные к зоне ноды в блок водного контура', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/nodes') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: [
              {
                id: 101,
                uid: 'nd-irrig-bound',
                type: 'controller',
                zone_id: '20',
                channels: [{ binding_role: 'main_pump' }],
              },
              {
                id: 102,
                uid: 'nd-ph-bound',
                type: 'controller',
                zone_id: '20',
                channels: [{ binding_role: 'ph_acid_pump' }],
              },
              {
                id: 104,
                uid: 'nd-ec-bound',
                type: 'controller',
                zone_id: '20',
                channels: [{ binding_role: 'ec_npk_pump' }],
              },
            ],
          },
        })
      }

      return mockDefaultGet(url)
    })

    const wrapper = mount(Wizard)
    await flushPromises()
    await createGreenhouseAndZone(wrapper)

    expect((wrapper.get('[data-test="irrigation-select"]').element as HTMLSelectElement).value).toBe('101')
    expect((wrapper.get('[data-test="ph-select"]').element as HTMLSelectElement).value).toBe('102')
    expect((wrapper.get('[data-test="ec-select"]').element as HTMLSelectElement).value).toBe('104')
  })

  it('после сохранения water block отправляет automation profile и команду применения', async () => {
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

    await wrapper.find('[data-test="save-section-water-contour"]').trigger('click')
    await flushPromises()

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

  it('не протаскивает несохранённые изменения освещения при сохранении water block', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    await createGreenhouseAndZone(wrapper)

    const plantSelect = wrapper.findAll('select').find((item) => item.text().includes('Tomato'))
    await plantSelect?.setValue('5')
    await flushPromises()
    await flushPromises()

    await wrapper.find('[data-test="lighting-toggle"]').setValue(true)
    await wrapper.find('[data-test="light-select"]').setValue('105')
    await wrapper.find('[data-test="irrigation-select"]').setValue('101')
    await wrapper.find('[data-test="ph-select"]').setValue('102')
    await wrapper.find('[data-test="ec-select"]').setValue('104')
    await flushPromises()

    await wrapper.find('[data-test="save-section-water-contour"]').trigger('click')
    await flushPromises()

    const automationCall = apiPostMock.mock.calls.find(([url]) => url === '/api/zones/20/automation-logic-profile')
    expect(automationCall?.[1]?.subsystems?.lighting?.enabled).toBe(false)
  })

  it('сохраняет уже загруженный профиль освещения при сохранении water block', async () => {
    apiGetMock.mockImplementation((url: string) => {
      if (url === '/api/zones/20/automation-logic-profile') {
        return Promise.resolve({
          data: {
            status: 'ok',
            data: {
              active_mode: 'setup',
              profiles: {
                setup: {
                  mode: 'setup',
                  is_active: true,
                  updated_at: '2026-03-22T12:00:00Z',
                  subsystems: {
                    ph: { enabled: true, execution: {} },
                    ec: { enabled: true, execution: {} },
                    irrigation: { enabled: true, execution: { system_type: 'substrate_trays' } },
                    lighting: { enabled: true, execution: { interval_sec: 1800 } },
                  },
                },
              },
            },
          },
        })
      }

      return mockDefaultGet(url)
    })

    const wrapper = mount(Wizard)
    await flushPromises()
    await createGreenhouseAndZone(wrapper)

    const plantSelect = wrapper.findAll('select').find((item) => item.text().includes('Tomato'))
    await plantSelect?.setValue('5')
    await flushPromises()
    await flushPromises()

    await wrapper.find('[data-test="irrigation-select"]').setValue('101')
    await wrapper.find('[data-test="ph-select"]').setValue('102')
    await wrapper.find('[data-test="ec-select"]').setValue('104')
    await flushPromises()

    await wrapper.find('[data-test="save-section-water-contour"]').trigger('click')
    await flushPromises()

    const automationCall = apiPostMock.mock.calls.find(([url]) => url === '/api/zones/20/automation-logic-profile')
    expect(automationCall?.[1]?.subsystems?.lighting?.enabled).toBe(true)
  })

  it('отправляет флаги света и zone climate из секции профиля', async () => {
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

    await wrapper.get('[data-test="save-section-zone-climate"]').trigger('click')
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

  it('снимает optional bindings при выключении света и климата зоны', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    await createGreenhouseAndZone(wrapper)

    const plantSelect = wrapper.findAll('select').find((item) => item.text().includes('Tomato'))
    await plantSelect?.setValue('5')
    await flushPromises()
    await flushPromises()

    await wrapper.find('[data-test="lighting-toggle"]').setValue(true)
    await wrapper.find('[data-test="zone-climate-toggle"]').setValue(true)
    await wrapper.find('[data-test="irrigation-select"]').setValue('101')
    await wrapper.find('[data-test="ph-select"]').setValue('102')
    await wrapper.find('[data-test="ec-select"]').setValue('104')
    await wrapper.find('[data-test="light-select"]').setValue('105')
    await wrapper.find('[data-test="co2-sensor-select"]').setValue('106')
    await flushPromises()

    await wrapper.find('[data-test="lighting-toggle"]').setValue(false)
    await wrapper.find('[data-test="zone-climate-toggle"]').setValue(false)
    await flushPromises()

    const saveLightingButtons = wrapper.findAll('[data-test="save-section-lighting"]')
    await saveLightingButtons[0]?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/setup-wizard/apply-device-bindings',
      expect.objectContaining({
        zone_id: 20,
        assignments: expect.objectContaining({
          irrigation: 101,
          accumulation: 101,
          ph_correction: 102,
          ec_correction: 104,
          light: null,
          co2_sensor: null,
          co2_actuator: null,
          root_vent_actuator: null,
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
