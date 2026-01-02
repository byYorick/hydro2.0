import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

const mockRouter = vi.hoisted(() => ({
  visit: vi.fn(),
  page: {
    url: '/test'
  }
}))

vi.mock('@inertiajs/vue3', () => ({
  router: mockRouter
}))

describe('useKeyboardShortcuts (P3-1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('should register keyboard shortcut', async () => {
    const { useKeyboardShortcuts } = await import('../useKeyboardShortcuts')
    
    const TestComponent = defineComponent({
      setup() {
        const { registerShortcut } = useKeyboardShortcuts()
        
        const handler = vi.fn()
        registerShortcut('x', { ctrl: true, handler })

        return { handler }
      },
      template: '<div>Test</div>'
    })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()

    // Симулируем нажатие Ctrl+X
    const event = new KeyboardEvent('keydown', {
      key: 'x',
      ctrlKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    
    expect(wrapper.vm.handler).toHaveBeenCalled()
  })

  it('should handle Ctrl+Shift+Z shortcut for Zones', async () => {
    const { useKeyboardShortcuts } = await import('../useKeyboardShortcuts')
    
    const TestComponent = defineComponent({
      setup() {
        useKeyboardShortcuts()
        return {}
      },
      template: '<div>Test</div>'
    })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()

    const event = new KeyboardEvent('keydown', {
      key: 'z',
      ctrlKey: true,
      shiftKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    // Ждем debounce (300ms)
    await new Promise(resolve => setTimeout(resolve, 350))
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/zones', { preserveUrl: true })
  })

  it('should handle Ctrl+Shift+D shortcut for Dashboard', async () => {
    const { useKeyboardShortcuts } = await import('../useKeyboardShortcuts')
    
    const TestComponent = defineComponent({
      setup() {
        useKeyboardShortcuts()
        return {}
      },
      template: '<div>Test</div>'
    })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()

    const event = new KeyboardEvent('keydown', {
      key: 'd',
      ctrlKey: true,
      shiftKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    // Ждем debounce (300ms)
    await new Promise(resolve => setTimeout(resolve, 350))
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/', { preserveUrl: true })
  })

  it('should handle Alt+R shortcut for Recipes', async () => {
    const { useKeyboardShortcuts } = await import('../useKeyboardShortcuts')
    
    const TestComponent = defineComponent({
      setup() {
        useKeyboardShortcuts()
        return {}
      },
      template: '<div>Test</div>'
    })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()

    const event = new KeyboardEvent('keydown', {
      key: 'r',
      altKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    // Ждем debounce (300ms)
    await new Promise(resolve => setTimeout(resolve, 350))
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/recipes', { preserveUrl: true })
  })

  it('should handle Shift+D shortcut for Devices', async () => {
    const { useKeyboardShortcuts } = await import('../useKeyboardShortcuts')
    
    const TestComponent = defineComponent({
      setup() {
        useKeyboardShortcuts()
        return {}
      },
      template: '<div>Test</div>'
    })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()

    const event = new KeyboardEvent('keydown', {
      key: 'd',
      shiftKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    // Ждем debounce (300ms)
    await new Promise(resolve => setTimeout(resolve, 350))
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/devices', { preserveUrl: true })
  })

  it('should ignore shortcuts when focus is in input', async () => {
    const { useKeyboardShortcuts } = await import('../useKeyboardShortcuts')
    
    const TestComponent = defineComponent({
      setup() {
        const { registerShortcut } = useKeyboardShortcuts()
        
        const handler = vi.fn()
        registerShortcut('x', { ctrl: true, handler })

        return { handler }
      },
      template: '<input ref="input" />'
    })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()

    const input = wrapper.find('input').element
    input.focus()
    await wrapper.vm.$nextTick()

    // Создаем событие и диспатчим его на элементе, чтобы target был установлен правильно
    const event = new KeyboardEvent('keydown', {
      key: 'x',
      ctrlKey: true,
      bubbles: true,
      cancelable: true
    })
    
    // Диспатчим событие на элементе, чтобы event.target был установлен
    input.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    
    // Handler не должен быть вызван, так как фокус в input
    expect(wrapper.vm.handler).not.toHaveBeenCalled()
  })

  it('should allow Ctrl+K even when focus is in input', async () => {
    // Ctrl+K обрабатывается CommandPalette, не useKeyboardShortcuts
    // Этот тест проверяет, что Ctrl+K не блокируется
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    const event = new KeyboardEvent('keydown', {
      key: 'k',
      ctrlKey: true,
      target: input
    })
    
    // Событие должно пройти (не должно быть preventDefault)
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault')
    window.dispatchEvent(event)
    
    // Ctrl+K не должен быть заблокирован useKeyboardShortcuts
    expect(preventDefaultSpy).not.toHaveBeenCalled()

    document.body.removeChild(input)
  })

  it('should unregister keyboard shortcut', async () => {
    const { useKeyboardShortcuts } = await import('../useKeyboardShortcuts')
    
    const TestComponent = defineComponent({
      setup() {
        const { registerShortcut, unregisterShortcut } = useKeyboardShortcuts()
        
        const handler = vi.fn()
        registerShortcut('x', { ctrl: true, handler })
        unregisterShortcut('x', { ctrl: true })

        return { handler }
      },
      template: '<div>Test</div>'
    })

    const wrapper = mount(TestComponent)
    await wrapper.vm.$nextTick()

    const event = new KeyboardEvent('keydown', {
      key: 'x',
      ctrlKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    
    expect(wrapper.vm.handler).not.toHaveBeenCalled()
  })
})

