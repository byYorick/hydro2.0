import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import EnhancedToast from '@/Components/EnhancedToast.vue'

describe('EnhancedToast', () => {
  const mockToasts = [
    {
      id: 1,
      message: 'Test message',
      variant: 'success' as const,
      duration: 5000
    },
    {
      id: 2,
      message: 'Error message',
      variant: 'error' as const,
      duration: 5000
    }
  ]

  describe('Отображение', () => {
    it('отображает список toast-уведомлений', () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: mockToasts
        }
      })

      expect(wrapper.text()).toContain('Test message')
      expect(wrapper.text()).toContain('Error message')
    })

    it('показывает правильные иконки для разных вариантов', () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: [mockToasts[0]]
        }
      })

      // Проверяем наличие SVG иконок
      const svg = wrapper.find('svg')
      expect(svg.exists()).toBe(true)
    })
  })

  describe('Варианты', () => {
    it('применяет правильные классы для success', () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: [mockToasts[0]]
        }
      })

      const toast = wrapper.find('.bg-emerald-900\\/90')
      expect(toast.exists()).toBe(true)
    })

    it('применяет правильные классы для error', () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: [mockToasts[1]]
        }
      })

      const toast = wrapper.find('.bg-red-900\\/90')
      expect(toast.exists()).toBe(true)
    })
  })

  describe('События', () => {
    it('эмитит событие close при клике на кнопку закрытия', async () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: [mockToasts[0]]
        }
      })

      const closeButton = wrapper.find('button')
      await closeButton.trigger('click')

      expect(wrapper.emitted('close')).toBeTruthy()
      expect(wrapper.emitted('close')?.[0]).toEqual([1])
    })

    it('эмитит событие action при клике на действие', async () => {
      const toastWithAction = {
        ...mockToasts[0],
        actions: [
          {
            label: 'Action',
            handler: vi.fn()
          }
        ]
      }

      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: [toastWithAction]
        }
      })

      const actionButton = wrapper.find('button')
      await actionButton.trigger('click')

      expect(wrapper.emitted('action')).toBeTruthy()
    })
  })

  describe('Прогресс-бар', () => {
    it('показывает прогресс-бар при наличии duration', () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: [{
            ...mockToasts[0],
            showProgress: true,
            progress: 50
          }]
        }
      })

      const progressBar = wrapper.find('.bg-black\\/20')
      expect(progressBar.exists()).toBe(true)
    })

    it('применяет правильную ширину прогресс-бара', () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: [{
            ...mockToasts[0],
            showProgress: true,
            progress: 75
          }]
        }
      })

      const progressBar = wrapper.find('[style*="width"]')
      expect(progressBar.exists()).toBe(true)
    })
  })

  describe('Анимации', () => {
    it('использует TransitionGroup для анимаций', () => {
      const wrapper = mount(EnhancedToast, {
        props: {
          toasts: mockToasts
        }
      })

      const transitionGroup = wrapper.findComponent({ name: 'TransitionGroup' })
      expect(transitionGroup.exists()).toBe(true)
    })
  })
})

