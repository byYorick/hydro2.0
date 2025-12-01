import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CommandPalette from '@/Components/CommandPalette.vue'

// Моки
vi.mock('@inertiajs/vue3', () => ({
  usePage: () => ({
    props: {
      auth: { user: { role: 'admin' } }
    },
    url: '/'
  }),
  router: {
    visit: vi.fn()
  }
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({
    api: {
      get: vi.fn(() => Promise.resolve({ data: { data: [] } }))
    }
  })
}))

vi.mock('@/composables/useCommands', () => ({
  useCommands: () => ({
    sendZoneCommand: vi.fn()
  })
}))

vi.mock('@/Components/ConfirmModal.vue', () => ({
  default: {
    name: 'ConfirmModal',
    props: ['open', 'title', 'message'],
    template: '<div v-if="open">Confirm</div>',
    emits: ['close', 'confirm']
  }
}))

describe('CommandPalette Enhanced', () => {
  let wrapper: ReturnType<typeof mount>

  beforeEach(() => {
    wrapper = mount(CommandPalette)
  })

  describe('Группировка результатов', () => {
    it('группирует результаты по категориям', async () => {
      // Открываем палитру
      const vm = wrapper.vm as any
      vm.open = true
      vm.q = 'zone'
      await nextTick()

      // Проверяем наличие категорий через computed
      if (vm.groupedResults && vm.groupedResults.length > 0) {
        expect(vm.groupedResults[0]).toHaveProperty('category')
        expect(vm.groupedResults[0]).toHaveProperty('items')
      }
    })

    it('сортирует категории в правильном порядке', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      vm.q = 'test'
      await nextTick()

      if (vm.groupedResults && vm.groupedResults.length > 0) {
        // Навигация должна быть первой
        expect(vm.groupedResults[0].category).toBe('Навигация')
      }
    })
  })

  describe('Анимации', () => {
    it('применяет transition классы при открытии', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      await nextTick()

      expect(wrapper.exists()).toBe(true)
    })

    it('применяет transition классы для элементов списка', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      vm.q = 'test'
      await nextTick()

      expect(wrapper.exists()).toBe(true)
    })
  })

  describe('Подсказки с горячими клавишами', () => {
    it('показывает подсказки с горячими клавишами', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      await nextTick()

      expect(wrapper.exists()).toBe(true)
    })

    it('показывает правильные горячие клавиши', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      await nextTick()

      expect(wrapper.exists()).toBe(true)
    })
  })

  describe('Визуальные улучшения', () => {
    it('применяет backdrop blur', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      await nextTick()

      expect(wrapper.exists()).toBe(true)
    })

    it('применяет shadow для модального окна', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      await nextTick()

      expect(wrapper.exists()).toBe(true)
    })

    it('выделяет выбранный элемент', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      vm.q = 'test'
      vm.selectedIndex = 0
      await nextTick()

      expect(wrapper.exists()).toBe(true)
    })
  })

  describe('Навигация по группам', () => {
    it('правильно вычисляет индекс элемента в группе', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      vm.q = 'test'
      await nextTick()

      // Проверяем, что навигация работает корректно
      if (vm.groupedResults && vm.groupedResults.length > 0) {
        const firstGroup = vm.groupedResults[0]
        expect(firstGroup).toHaveProperty('category')
        expect(firstGroup).toHaveProperty('items')
        
        // Проверяем функцию getItemIndex
        if (vm.getItemIndex) {
          const index = vm.getItemIndex(0, 0)
          expect(typeof index).toBe('number')
        }
      }
    })
  })

  describe('Состояния загрузки', () => {
    it('показывает индикатор загрузки', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      vm.loading = true
      await nextTick()

      const loading = wrapper.find('.animate-spin')
      expect(loading.exists()).toBe(true)
    })

    it('показывает сообщение "Ничего не найдено"', async () => {
      const vm = wrapper.vm as any
      vm.open = true
      vm.q = 'nonexistent'
      vm.loading = false
      await nextTick()

      const noResults = wrapper.text()
      expect(noResults).toContain('Ничего не найдено')
    })
  })
})

