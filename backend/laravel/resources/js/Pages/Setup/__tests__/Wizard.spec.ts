import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const roleState = vi.hoisted(() => ({ role: 'agronomist' }))

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn())
const apiPatchMock = vi.hoisted(() => vi.fn())
const routerVisitMock = vi.hoisted(() => vi.fn())

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

import Wizard from '../Wizard.vue'

describe('Setup/Wizard.vue', () => {
  beforeEach(() => {
    roleState.role = 'agronomist'
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    apiPatchMock.mockReset()
    routerVisitMock.mockReset()

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

    apiPatchMock.mockResolvedValue({
      data: {
        status: 'ok',
      },
    })
  })

  it('рендерит заголовок и шаги мастера', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    expect(wrapper.text()).toContain('Мастер настройки системы')
    expect(wrapper.text()).toContain('1. Теплица')
    expect(wrapper.text()).toContain('2. Зона')
    expect(wrapper.text()).toContain('3. Растение')
    expect(wrapper.text()).toContain('4. Рецепт')
    expect(wrapper.text()).toContain('5. Устройства')
    expect(wrapper.text()).toContain('6. Логика автоматики')
    expect(wrapper.text()).toContain('7. Запуск и контроль')
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

    const createToggle = wrapper.findAll('button').find((btn) => btn.text() === 'Создать')
    expect(createToggle).toBeTruthy()
    await createToggle?.trigger('click')

    const greenhouseNameInput = wrapper.find('input[placeholder="Название теплицы"]')
    expect(greenhouseNameInput.exists()).toBe(true)
    await greenhouseNameInput.setValue('Main GH')

    const createButton = wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))
    expect(createButton).toBeTruthy()
    await createButton?.trigger('click')

    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith(
      '/api/greenhouses',
      expect.objectContaining({
        name: 'Main GH',
      }),
      undefined
    )
  })

  it('применяет логику автоматики через команду зоны', async () => {
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

    const createToggle = wrapper.findAll('button').find((btn) => btn.text() === 'Создать')
    await createToggle?.trigger('click')

    const greenhouseNameInput = wrapper.find('input[placeholder="Название теплицы"]')
    await greenhouseNameInput.setValue('Main GH')

    const createGreenhouseButton = wrapper.findAll('button').find((btn) => btn.text().includes('Создать теплицу'))
    await createGreenhouseButton?.trigger('click')
    await flushPromises()

    const createZoneButton = wrapper.findAll('button').find((btn) => btn.text().includes('Создать зону'))
    await createZoneButton?.trigger('click')
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

  it('не позволяет запуск до завершения обязательных шагов', async () => {
    const wrapper = mount(Wizard)
    await flushPromises()

    const openLaunchButton = wrapper.findAll('button').find((btn) => btn.text().includes('Открыть мастер запуска цикла'))
    expect(openLaunchButton).toBeTruthy()
    expect((openLaunchButton?.element as HTMLButtonElement).disabled).toBe(true)
  })
})
