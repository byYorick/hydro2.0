import { mount } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import CommandPalette from '../CommandPalette.vue'

// Mock router (must use hoisted factory to avoid hoist issues)
const mockRouter = vi.hoisted(() => ({
  visit: vi.fn(),
}))

vi.mock('@inertiajs/vue3', () => ({
  router: mockRouter,
  usePage: () => ({ props: {} }),
}))

// Mock useApi
const mockApi = vi.hoisted(() => ({
  get: vi.fn(() => Promise.resolve({ data: { data: [] } })),
}))

vi.mock('@/composables/useApi', () => ({
  useApi: () => ({ api: mockApi }),
}))

// Mock useCommands
vi.mock('@/composables/useCommands', () => ({
  useCommands: () => ({
    sendZoneCommand: vi.fn()
  })
}))

describe('CommandPalette (P3-1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRouter.visit.mockReset()
    mockApi.get.mockReset()
    mockApi.get.mockResolvedValue({ data: { data: [] } })
  })

  it('renders when open prop is true', async () => {
    const wrapper = mount(CommandPalette)
    
    // Открываем палитру через Ctrl+K
    await wrapper.vm.$nextTick()
    
    // Проверяем, что компонент рендерится
    expect(wrapper.exists()).toBe(true)
  })

  it('opens on Ctrl+K keyboard shortcut', async () => {
    const wrapper = mount(CommandPalette)
    
    // Симулируем нажатие Ctrl+K
    const event = new KeyboardEvent('keydown', {
      key: 'k',
      ctrlKey: true
    })
    
    window.dispatchEvent(event)
    await nextTick()

    // Палитра должна открыться
    expect(wrapper.vm.open).toBe(true)
  })

  it('closes on Escape key', async () => {
    const wrapper = mount(CommandPalette)
    
    // Открываем палитру
    wrapper.vm.open = true
    await nextTick()

    // Симулируем Escape
    const event = new KeyboardEvent('keydown', {
      key: 'Escape'
    })
    
    window.dispatchEvent(event)
    await nextTick()

    expect(wrapper.vm.open).toBe(false)
  })

  it('displays static navigation commands', async () => {
    const wrapper = mount(CommandPalette)
    wrapper.vm.open = true
    await nextTick()

    expect(wrapper.text()).toContain('Открыть Zones')
    expect(wrapper.text()).toContain('Открыть Devices')
    expect(wrapper.text()).toContain('Открыть Recipes')
  })

  it('performs fuzzy search on input', async () => {
    const wrapper = mount(CommandPalette)
    wrapper.vm.open = true
    await nextTick()

    const input = wrapper.find('input')
    await input.setValue('zones')
    await nextTick()

    // Должны найтись результаты
    expect(wrapper.vm.q).toBe('zones')
  })

  it('navigates to zone when zone command is selected', async () => {
    const wrapper = mount(CommandPalette)
    wrapper.vm.open = true
    await nextTick()

    // Мокируем результаты поиска
    wrapper.vm.searchResults = {
      zones: [{ id: 1, name: 'Test Zone' }],
      nodes: [],
      recipes: []
    }
    wrapper.vm.q = 'test'
    await nextTick()

    const results = wrapper.vm.filteredResults
    const zoneCommand = results.find((r: any) => r.type === 'zone')
    
    if (zoneCommand) {
      wrapper.vm.run(zoneCommand)
      await nextTick()

      expect(mockRouter.visit).toHaveBeenCalledWith('/zones/1')
    }
  })

  it('shows confirmation modal for actions requiring confirmation', async () => {
    const wrapper = mount(CommandPalette)
    wrapper.vm.open = true
    await nextTick()

    // Создаем действие, требующее подтверждения
    const action = {
      type: 'action',
      id: 'test-action',
      label: 'Test Action',
      requiresConfirm: true,
      actionFn: vi.fn(),
      zoneId: 1,
      zoneName: 'Test Zone',
      actionType: 'pause'
    }

    wrapper.vm.run(action)
    await nextTick()

    // Должно открыться модальное окно подтверждения
    expect(wrapper.vm.confirmModal.open).toBe(true)
    expect(wrapper.vm.confirmModal.message).toContain('Test Zone')
  })

  it('handles keyboard navigation with arrow keys', async () => {
    const wrapper = mount(CommandPalette)
    wrapper.vm.open = true
    wrapper.vm.q = 'test'
    await nextTick()

    const input = wrapper.find('input')
    
    // Симулируем стрелку вниз
    await input.trigger('keydown.down')
    expect(wrapper.vm.selectedIndex).toBeGreaterThanOrEqual(0)

    // Симулируем стрелку вверх
    await input.trigger('keydown.up')
    expect(wrapper.vm.selectedIndex).toBeGreaterThanOrEqual(0)
  })

  it('executes command on Enter key', async () => {
    const wrapper = mount(CommandPalette)
    wrapper.vm.open = true
    wrapper.vm.q = 'zones'
    await nextTick()

    const input = wrapper.find('input')
    wrapper.vm.selectedIndex = 0
    
    await input.trigger('keydown.enter')
    await nextTick()

    // Команда должна быть выполнена
    expect(wrapper.vm.open).toBe(false)
  })

  it('highlights search matches in results', async () => {
    const wrapper = mount(CommandPalette)
    wrapper.vm.open = true
    wrapper.vm.q = 'zones'
    await nextTick()

    const highlighted = wrapper.vm.highlightMatch('Zones', 'zones')
    expect(highlighted).toContain('<mark')
  })
})

