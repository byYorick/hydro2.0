import { mount } from '@vue/test-utils'
import { describe, it, expect, vi } from 'vitest'
import ErrorBoundary from '../ErrorBoundary.vue'

// Mock router
vi.mock('@inertiajs/vue3', () => ({
  router: {
    visit: vi.fn()
  }
}))

describe('ErrorBoundary (P1-3)', () => {
  it('renders slot content when no error occurs', () => {
    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: '<div>Test Content</div>'
      }
    })

    expect(wrapper.text()).toContain('Test Content')
    expect(wrapper.find('.text-red-400').exists()).toBe(false)
  })

  it('catches and displays error when child component throws', async () => {
    const ThrowError = {
      setup() {
        throw new Error('Test error')
      },
      template: '<div>Should not render</div>'
    }

    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: ThrowError
      }
    })

    await wrapper.vm.$nextTick()

    // ErrorBoundary должен отобразить fallback UI
    expect(wrapper.text()).toContain('Произошла ошибка')
    expect(wrapper.find('.text-red-400').exists()).toBe(true)
  })

  it('displays error message in fallback UI', async () => {
    const ThrowError = {
      setup() {
        throw new Error('Custom error message')
      },
      template: '<div>Should not render</div>'
    }

    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: ThrowError
      }
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Custom error message')
  })

  it('shows stack trace in development mode', async () => {
    const originalEnv = import.meta.env.MODE
    // @ts-ignore
    import.meta.env.MODE = 'development'

    const ThrowError = {
      setup() {
        throw new Error('Test error')
      },
      template: '<div>Should not render</div>'
    }

    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: ThrowError
      }
    })

    await wrapper.vm.$nextTick()

    // В development режиме должен показываться stack trace
    const stackTrace = wrapper.find('pre')
    expect(stackTrace.exists()).toBe(true)

    // @ts-ignore
    import.meta.env.MODE = originalEnv
  })

  it('has "Try Again" button that resets error state', async () => {
    // Мокируем window.location.reload
    const reloadSpy = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { reload: reloadSpy },
      writable: true
    })

    const ThrowError = {
      setup() {
        throw new Error('Test error')
      },
      template: '<div>Should not render</div>'
    }

    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: ThrowError
      }
    })

    await wrapper.vm.$nextTick()

    const tryAgainButton = wrapper.find('button')
    expect(tryAgainButton.exists()).toBe(true)
    expect(tryAgainButton.text()).toContain('Попробовать снова')

    // При клике должна быть вызвана reload
    await tryAgainButton.trigger('click')
    
    // Проверяем, что reload был вызван
    expect(reloadSpy).toHaveBeenCalled()
  })

  it('has "Go Home" button', async () => {
    const ThrowError = {
      setup() {
        throw new Error('Test error')
      },
      template: '<div>Should not render</div>'
    }

    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: ThrowError
      }
    })

    await wrapper.vm.$nextTick()

    const buttons = wrapper.findAll('button')
    const goHomeButton = buttons.find(btn => btn.text().includes('На главную'))
    expect(goHomeButton).toBeDefined()
  })

  it('handles multiple errors correctly', async () => {
    let throwCount = 0
    const ThrowError = {
      setup() {
        throwCount++
        throw new Error(`Error ${throwCount}`)
      },
      template: '<div>Should not render</div>'
    }

    const wrapper = mount(ErrorBoundary, {
      slots: {
        default: ThrowError
      }
    })

    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('Error 1')

    // Сбрасываем ошибку
    const tryAgainButton = wrapper.find('button')
    await tryAgainButton.trigger('click')
    await wrapper.vm.$nextTick()

    // Ошибка должна снова произойти
    await wrapper.vm.$nextTick()
    expect(throwCount).toBeGreaterThan(1)
  })
})

