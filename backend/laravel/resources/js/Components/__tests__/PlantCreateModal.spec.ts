import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiGetMock = vi.hoisted(() => vi.fn())
const apiPostMock = vi.hoisted(() => vi.fn())
const routerReloadMock = vi.hoisted(() => vi.fn())

vi.mock('@/Components/Modal.vue', () => ({
  default: {
    name: 'Modal',
    props: ['open', 'title', 'size'],
    template: '<div v-if="open"><slot /><slot name="footer" /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['type', 'variant', 'size', 'disabled'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}))

vi.mock('@/Components/TaxonomyWizardModal.vue', () => ({
  default: { name: 'TaxonomyWizardModal', template: '<div />' },
}))

vi.mock('@inertiajs/vue3', () => ({
  router: {
    reload: routerReloadMock,
  },
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: apiGetMock,
      post: apiPostMock,
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
    info: vi.fn(),
    error: vi.fn(),
  },
}))

import PlantCreateModal from '../PlantCreateModal.vue'

describe('PlantCreateModal', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    apiPostMock.mockReset()
    routerReloadMock.mockReset()

    apiGetMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          substrate_type: [{ id: 'coco', label: 'Кокос' }],
          growing_system: [
            { id: 'nft', label: 'NFT', uses_substrate: false },
            { id: 'drip', label: 'Капельный полив', uses_substrate: true },
          ],
          photoperiod_preset: [],
          seasonality: [],
        },
      },
    })
  })

  it('показывает субстрат только для систем где он применим', async () => {
    const wrapper = mount(PlantCreateModal, {
      props: { show: false },
    })
    await wrapper.setProps({ show: true })
    await flushPromises()

    expect(apiGetMock).toHaveBeenCalledWith('/plant-taxonomies')
    expect(wrapper.find('#plant-substrate').exists()).toBe(false)

    await wrapper.find('#plant-system').setValue('nft')
    await flushPromises()
    expect(wrapper.find('#plant-substrate').exists()).toBe(false)

    await wrapper.find('#plant-system').setValue('drip')
    await flushPromises()
    expect(wrapper.find('#plant-substrate').exists()).toBe(true)
  })

  it('создает рецепт с ревизией и фазами полного цикла', async () => {
    apiPostMock.mockImplementation((url: string) => {
      if (url === '/plants') {
        return Promise.resolve({ data: { status: 'ok', data: { id: 10, name: 'Салат' } } })
      }
      if (url === '/recipes') {
        return Promise.resolve({ data: { status: 'ok', data: { id: 20 } } })
      }
      if (url === '/recipes/20/revisions') {
        return Promise.resolve({ data: { status: 'ok', data: { id: 30 } } })
      }
      if (url.startsWith('/recipe-revisions/30/phases')) {
        return Promise.resolve({ data: { status: 'ok', data: { id: 1 } } })
      }
      if (url === '/recipe-revisions/30/publish') {
        return Promise.resolve({ data: { status: 'ok' } })
      }
      return Promise.resolve({ data: { status: 'ok' } })
    })

    const wrapper = mount(PlantCreateModal, {
      props: { show: false },
    })
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.find('#plant-name').setValue('Салат')
    const nextButton = wrapper.findAll('button').find((button) => button.text() === 'Далее')
    await nextButton?.trigger('click')
    await flushPromises()

    const createButton = wrapper.findAll('button').find((button) => button.text().includes('Создать культуру и рецепт'))
    await createButton?.trigger('click')
    await flushPromises()

    const phaseCalls = apiPostMock.mock.calls.filter(([url]) => url === '/recipe-revisions/30/phases')
    expect(phaseCalls.length).toBeGreaterThanOrEqual(3)
    expect(phaseCalls[0]?.[1]).toEqual(expect.objectContaining({
      extensions: expect.objectContaining({
        day_night: expect.any(Object),
      }),
      lighting_start_time: expect.any(String),
      lighting_photoperiod_hours: expect.any(Number),
    }))
    expect(apiPostMock).toHaveBeenCalledWith('/recipe-revisions/30/publish')
  })
})
