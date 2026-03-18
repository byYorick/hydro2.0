import { flushPromises, mount } from '@vue/test-utils'
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

    apiGetMock.mockImplementation((url: string) => {
      if (url === '/plant-taxonomies') {
        return Promise.resolve({
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
      }

      if (url === '/nutrient-products') {
        return Promise.resolve({ data: { status: 'ok', data: [] } })
      }

      return Promise.resolve({ data: { status: 'ok', data: [] } })
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

  it('создает растение и рецепт через атомарный backend flow', async () => {
    apiPostMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          plant: { id: 10, name: 'Салат' },
          recipe: { id: 20, name: 'Салат — полный цикл' },
          revision: { id: 30 },
        },
      },
    })

    const wrapper = mount(PlantCreateModal, {
      props: { show: false },
    })
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.find('#plant-name').setValue('Салат')
    await wrapper.find('#plant-system').setValue('nft')
    const nextButton = wrapper.findAll('button').find((button) => button.text() === 'Далее')
    await nextButton?.trigger('click')
    await flushPromises()

    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('Создать культуру и рецепт'))
    await submitButton?.trigger('click')
    await flushPromises()

    expect(apiPostMock).toHaveBeenCalledWith('/plants/with-recipe', expect.objectContaining({
      plant: expect.objectContaining({
        name: 'Салат',
        growing_system: 'nft',
      }),
      recipe: expect.objectContaining({
        name: 'Салат — полный цикл',
        phases: expect.any(Array),
      }),
    }))

    const payload = apiPostMock.mock.calls[0]?.[1]
    expect(payload.recipe.phases).toHaveLength(1)
    expect(payload.recipe.phases[0]).toEqual(expect.objectContaining({
      extensions: expect.objectContaining({
        day_night: expect.any(Object),
        subsystems: expect.objectContaining({
          irrigation: expect.objectContaining({
            targets: expect.objectContaining({
              system_type: 'drip',
            }),
          }),
        }),
      }),
    }))
    expect(routerReloadMock).toHaveBeenCalledWith({ only: ['plants'] })
  })

  it('требует выбор системы выращивания перед переходом к шагу рецепта', async () => {
    const wrapper = mount(PlantCreateModal, {
      props: { show: false },
    })
    await wrapper.setProps({ show: true })
    await flushPromises()

    await wrapper.find('#plant-name').setValue('Салат')
    const nextButton = wrapper.findAll('button').find((button) => button.text() === 'Далее')
    expect(nextButton).toBeTruthy()
    expect((nextButton?.element as HTMLButtonElement).disabled).toBe(true)
  })
})
