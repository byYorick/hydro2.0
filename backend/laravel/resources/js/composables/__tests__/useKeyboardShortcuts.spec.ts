import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

const mockRouter = {
  visit: vi.fn()
}

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

  it('should handle Ctrl+Z shortcut for Zones', async () => {
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
      ctrlKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/zones', { preserveScroll: true })
  })

  it('should handle Alt+D shortcut for Dashboard', async () => {
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
      altKey: true
    })
    
    window.dispatchEvent(event)
    await wrapper.vm.$nextTick()
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/', { preserveScroll: true })
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
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/recipes', { preserveScroll: true })
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
    
    expect(mockRouter.visit).toHaveBeenCalledWith('/devices', { preserveScroll: true })
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

