import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/Layouts/AppLayout.vue', () => ({
  default: { name: 'AppLayout', template: '<div><slot /></div>' },
}))

vi.mock('@/Components/Card.vue', () => ({
  default: { name: 'Card', template: '<div class="card"><slot /></div>' },
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
}))

const axiosGetMock = vi.hoisted(() => vi.fn())
const axiosPostMock = vi.hoisted(() => vi.fn())
const axiosPatchMock = vi.hoisted(() => vi.fn())

vi.mock('axios', () => ({
  default: {
    get: (url: string, config?: any) => axiosGetMock(url, config),
    post: (url: string, data?: any, config?: any) => axiosPostMock(url, data, config),
    patch: (url: string, data?: any, config?: any) => axiosPatchMock(url, data, config),
  },
}))

vi.mock('@/utils/logger', () => ({
  logger: {
    info: vi.fn(),
    error: vi.fn(),
  },
}))

import SetupWizard from '../Wizard.vue'

describe('Setup/Wizard.vue', () => {
  beforeEach(() => {
    axiosGetMock.mockClear()
    axiosPostMock.mockClear()
    axiosPatchMock.mockClear()
    
    axiosPostMock.mockResolvedValue({
      data: {
        data: { id: 1 },
      },
    })
    
    axiosGetMock.mockResolvedValue({
      data: {
        data: [],
      },
    })
    
    axiosPatchMock.mockResolvedValue({
      data: { status: 'ok' },
    })
  })

  it('отображает заголовок мастера настройки', () => {
    const wrapper = mount(SetupWizard)
    
    expect(wrapper.text()).toContain('Мастер настройки системы')
  })

  it('отображает все шаги', () => {
    const wrapper = mount(SetupWizard)
    
    expect(wrapper.text()).toContain('Шаг 1: Создать теплицу')
    expect(wrapper.text()).toContain('Шаг 2: Создать рецепт с фазами')
    expect(wrapper.text()).toContain('Шаг 3: Создать зону')
    expect(wrapper.text()).toContain('Шаг 4: Привязать рецепт к зоне')
    expect(wrapper.text()).toContain('Шаг 5: Привязать узлы к зоне')
  })

  it('позволяет создать теплицу на шаге 1', async () => {
    const wrapper = mount(SetupWizard)
    
    const createButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать теплицу'))
    if (createButton) {
      await createButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(axiosPostMock).toHaveBeenCalledWith(
        '/api/greenhouses',
        expect.objectContaining({
          uid: 'gh-main',
          name: 'Main Greenhouse',
        }),
        expect.any(Object)
      )
    }
  })

  it('блокирует шаг 2 пока шаг 1 не выполнен', async () => {
    const wrapper = mount(SetupWizard)
    
    const createRecipeButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать рецепт'))
    if (createRecipeButton) {
      expect((createRecipeButton.element as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('разблокирует шаг 2 после создания теплицы', async () => {
    axiosPostMock.mockResolvedValueOnce({
      data: {
        data: { id: 1, uid: 'gh-main', name: 'Main Greenhouse' },
      },
    })
    
    const wrapper = mount(SetupWizard)
    
    const createGreenhouseButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать теплицу'))
    if (createGreenhouseButton) {
      await createGreenhouseButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 150))
      await wrapper.vm.$nextTick()
      
      const createRecipeButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать рецепт'))
      if (createRecipeButton) {
        expect((createRecipeButton.element as HTMLButtonElement).disabled).toBe(false)
      }
    }
  })

  it('позволяет добавить фазу рецепта', async () => {
    const wrapper = mount(SetupWizard)
    
    // Сначала создаем теплицу
    axiosPostMock.mockResolvedValueOnce({
      data: {
        data: { id: 1, uid: 'gh-main', name: 'Main Greenhouse' },
      },
    })
    
    const createGreenhouseButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать теплицу'))
    if (createGreenhouseButton) {
      await createGreenhouseButton.trigger('click')
      await new Promise(resolve => setTimeout(resolve, 100))
      await wrapper.vm.$nextTick()
    }
    
    const addPhaseButton = wrapper.findAll('button').find(btn => btn.text().includes('Добавить фазу'))
    if (addPhaseButton) {
      const phasesBefore = wrapper.vm.$data.recipeForm.phases.length
      await addPhaseButton.trigger('click')
      await wrapper.vm.$nextTick()
      
      expect(wrapper.vm.$data.recipeForm.phases.length).toBeGreaterThan(phasesBefore)
    }
  })

  it('создает рецепт с фазами на шаге 2', async () => {
    // Создаем теплицу
    axiosPostMock.mockResolvedValueOnce({
      data: {
        data: { id: 1, uid: 'gh-main', name: 'Main Greenhouse' },
      },
    })
    
    // Создаем рецепт
    axiosPostMock.mockResolvedValueOnce({
      data: {
        data: { id: 1, name: 'Test Recipe' },
      },
    })
    
    // Получаем рецепт с фазами
    axiosGetMock.mockResolvedValueOnce({
      data: {
        data: {
          id: 1,
          name: 'Test Recipe',
          phases: [
            { id: 1, phase_index: 0, name: 'Phase 1', duration_hours: 24 },
          ],
        },
      },
    })
    
    const wrapper = mount(SetupWizard)
    
    // Шаг 1
    const createGreenhouseButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать теплицу'))
    if (createGreenhouseButton) {
      await createGreenhouseButton.trigger('click')
      await new Promise(resolve => setTimeout(resolve, 100))
      await wrapper.vm.$nextTick()
    }
    
    // Шаг 2
    const createRecipeButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать рецепт'))
    if (createRecipeButton) {
      await createRecipeButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 200))
      
      expect(axiosPostMock).toHaveBeenCalledWith(
        '/api/recipes',
        expect.objectContaining({
          name: 'Lettuce NFT Recipe',
          description: 'Standard NFT recipe for lettuce',
        }),
        expect.any(Object)
      )
      
      // Проверяем, что фазы создаются
      const phaseCalls = axiosPostMock.mock.calls.filter(call => 
        call[0]?.includes('/api/recipes/') && call[0]?.includes('/phases')
      )
      expect(phaseCalls.length).toBeGreaterThan(0)
    }
  })

  it('создает зону на шаге 3', async () => {
    // Настраиваем моки для предыдущих шагов
    axiosPostMock
      .mockResolvedValueOnce({ data: { data: { id: 1 } } }) // Greenhouse
      .mockResolvedValueOnce({ data: { data: { id: 1 } } }) // Recipe
      .mockResolvedValueOnce({ data: { data: { id: 1 } } }) // Zone
    
    axiosGetMock.mockResolvedValueOnce({
      data: {
        data: {
          id: 1,
          name: 'Test Recipe',
          phases: [],
        },
      },
    })
    
    const wrapper = mount(SetupWizard)
    
    // Выполняем шаги последовательно
    await wrapper.setData({ createdGreenhouse: { id: 1 } })
    await wrapper.setData({ createdRecipe: { id: 1, phases: [] } })
    await wrapper.vm.$nextTick()
    
    const createZoneButton = wrapper.findAll('button').find(btn => btn.text().includes('Создать зону'))
    if (createZoneButton) {
      await createZoneButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(axiosPostMock).toHaveBeenCalledWith(
        '/api/zones',
        expect.objectContaining({
          name: 'Zone A',
          greenhouse_id: 1,
        }),
        expect.any(Object)
      )
    }
  })

  it('привязывает рецепт к зоне на шаге 4', async () => {
    const wrapper = mount(SetupWizard)
    
    await wrapper.setData({
      createdGreenhouse: { id: 1 },
      createdRecipe: { id: 1 },
      createdZone: { id: 1 },
    })
    await wrapper.vm.$nextTick()
    
    const attachRecipeButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать рецепт к зоне'))
    if (attachRecipeButton) {
      await attachRecipeButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(axiosPostMock).toHaveBeenCalledWith(
        '/api/zones/1/attach-recipe',
        expect.objectContaining({
          recipe_id: 1,
        }),
        expect.any(Object)
      )
    }
  })

  it('загружает доступные узлы на шаге 5', async () => {
    axiosGetMock.mockResolvedValue({
      data: {
        data: [
          { id: 1, uid: 'node-1', type: 'sensor' },
          { id: 2, uid: 'node-2', type: 'actuator' },
        ],
      },
    })
    
    const wrapper = mount(SetupWizard)
    
    await new Promise(resolve => setTimeout(resolve, 100))
    
    expect(axiosGetMock).toHaveBeenCalledWith('/api/nodes?unassigned=true', expect.any(Object))
  })

  it('привязывает узлы к зоне на шаге 5', async () => {
    axiosGetMock.mockResolvedValue({
      data: {
        data: [
          { id: 1, uid: 'node-1' },
          { id: 2, uid: 'node-2' },
        ],
      },
    })
    
    const wrapper = mount(SetupWizard)
    
    await wrapper.setData({
      createdGreenhouse: { id: 1 },
      createdRecipe: { id: 1 },
      createdZone: { id: 1 },
      selectedNodeIds: [1, 2],
    })
    await wrapper.vm.$nextTick()
    
    const attachNodesButton = wrapper.findAll('button').find(btn => btn.text().includes('Привязать узлы'))
    if (attachNodesButton) {
      await attachNodesButton.trigger('click')
      
      await new Promise(resolve => setTimeout(resolve, 100))
      
      expect(axiosPatchMock).toHaveBeenCalledTimes(2)
      expect(axiosPatchMock.mock.calls[0][0]).toBe('/api/nodes/1')
      expect(axiosPatchMock.mock.calls[0][1]).toMatchObject({ zone_id: 1 })
    }
  })

  it('показывает финальное сообщение после завершения всех шагов', async () => {
    const wrapper = mount(SetupWizard)
    
    await wrapper.setData({
      createdGreenhouse: { id: 1 },
      createdRecipe: { id: 1, phases: [] },
      createdZone: { id: 1 },
      attachedNodesCount: 2,
    })
    await wrapper.vm.$nextTick()
    
    expect(wrapper.text()).toContain('Система настроена!')
    expect(wrapper.text()).toContain('Зона создана, рецепт привязан')
  })

  it('отображает ссылки на зону и главную после завершения', async () => {
    const wrapper = mount(SetupWizard)
    
    await wrapper.setData({
      createdGreenhouse: { id: 1 },
      createdRecipe: { id: 1, phases: [] },
      createdZone: { id: 1 },
      attachedNodesCount: 2,
    })
    await wrapper.vm.$nextTick()
    
    const links = wrapper.findAllComponents({ name: 'Link' })
    expect(links.length).toBeGreaterThanOrEqual(2)
    
    const zoneLink = links.find(link => link.attributes('href')?.includes('/zones/1'))
    const homeLink = links.find(link => link.attributes('href') === '/')
    
    expect(zoneLink).toBeTruthy()
    expect(homeLink).toBeTruthy()
  })
})

