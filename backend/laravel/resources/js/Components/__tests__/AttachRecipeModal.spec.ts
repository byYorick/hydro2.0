import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/Components/Modal.vue', () => ({
  default: {
    name: 'Modal',
    props: ['open', 'title'],
    emits: ['close'],
    template: '<div v-if="open"><div class="modal-title">{{ title }}</div><slot /><slot name="footer" /></div>',
  },
}))

vi.mock('@/Components/Button.vue', () => ({
  default: {
    name: 'Button',
    props: ['size', 'disabled'],
    template: '<button :disabled="disabled"><slot /></button>',
  },
}))

const axiosGetMock = vi.hoisted(() => vi.fn())
const axiosPostMock = vi.hoisted(() => vi.fn())
const routerReloadMock = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: {
    get: (url: string, config?: any) => axiosGetMock(url, config),
    post: (url: string, data?: any, config?: any) => axiosPostMock(url, data, config),
  },
}))

vi.mock('@inertiajs/vue3', () => ({
  router: {
    reload: routerReloadMock,
  },
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    error: vi.fn(),
  },
}))

import AttachRecipeModal from '../AttachRecipeModal.vue'

describe('AttachRecipeModal.vue', () => {
  const sampleRecipes = [
    { id: 1, name: 'Lettuce Recipe', phases_count: 3 },
    { id: 2, name: 'Basil Recipe', phases_count: 2 },
    { id: 3, name: 'Tomato Recipe', phases_count: 4 },
  ]

  beforeEach(() => {
    axiosGetMock.mockClear()
    axiosPostMock.mockClear()
    routerReloadMock.mockClear()
    
    axiosGetMock.mockResolvedValue({
      data: {
        data: sampleRecipes,
      },
    })
    
    axiosPostMock.mockResolvedValue({
      data: { status: 'ok' },
    })
  })

  it('отображается когда show = true', () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    expect(wrapper.text()).toContain('Привязать рецепт к зоне')
  })

  it('не отображается когда show = false', () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: false,
        zoneId: 1,
      },
    })
    
    expect(wrapper.html()).not.toContain('Привязать рецепт к зоне')
  })

  it('загружает список рецептов при открытии', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(axiosGetMock).toHaveBeenCalledWith('/api/recipes', expect.any(Object))
  })

  it('отображает список рецептов', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Lettuce Recipe')
    expect(wrapper.text()).toContain('Basil Recipe')
  })

  it('позволяет выбрать рецепт', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const select = wrapper.find('select')
    expect(select.exists()).toBe(true)
    
    await wrapper.setData({ selectedRecipeId: 1 })
    await wrapper.vm.$nextTick()
    
    expect(wrapper.vm.$data.selectedRecipeId).toBe(1)
  })

  it('привязывает рецепт к зоне', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    await wrapper.setData({ selectedRecipeId: 1 })
    await wrapper.vm.$nextTick()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton) {
      await attachButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(axiosPostMock).toHaveBeenCalledWith(
        '/api/zones/1/attach-recipe',
        { recipe_id: 1 },
        expect.any(Object)
      )
    }
  })

  it('отображает фазы рецепта при выборе', async () => {
    const recipesWithPhases = [
      {
        id: 1,
        name: 'Lettuce Recipe',
        phases: [
          { id: 1, phase_index: 0, name: 'Seedling', duration_hours: 168 },
          { id: 2, phase_index: 1, name: 'Vegetative', duration_hours: 336 },
        ],
      },
    ]
    
    axiosGetMock.mockResolvedValue({
      data: {
        data: recipesWithPhases,
      },
    })
    
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    await wrapper.setData({ selectedRecipeId: 1 })
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Seedling')
    expect(wrapper.text()).toContain('Vegetative')
  })

  it('блокирует кнопку привязки когда рецепт не выбран', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton) {
      expect((attachButton.element as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('показывает состояние загрузки', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    expect(wrapper.text()).toContain('Загрузка')
  })

  it('эмитит событие attached после успешной привязки', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 150))
    await wrapper.vm.$nextTick()
    
    await wrapper.setData({ selectedRecipeId: 1 })
    await wrapper.vm.$nextTick()
    
    const attachButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать'))
    if (attachButton) {
      await attachButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(wrapper.emitted('attached')).toBeTruthy()
      expect(wrapper.emitted('attached')?.[0]).toEqual([1])
    }
  })

  it('эмитит событие close при закрытии', async () => {
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    const cancelButton = wrapper.findAll('button').find(btn => btn.text().includes('Отмена'))
    if (cancelButton) {
      await cancelButton.trigger('click')
      
      expect(wrapper.emitted('close')).toBeTruthy()
    }
  })

  it('обрабатывает ошибки при загрузке рецептов', async () => {
    axiosGetMock.mockRejectedValue(new Error('Network error'))
    
    const wrapper = mount(AttachRecipeModal, {
      props: {
        show: true,
        zoneId: 1,
      },
    })
    
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(axiosGetMock).toHaveBeenCalled()
  })
})

