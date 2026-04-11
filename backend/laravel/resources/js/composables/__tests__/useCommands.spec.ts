import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCommands } from '../useCommands'
import { api } from '@/services/api'

// Mock the typed API layer
vi.mock('@/services/api', () => ({
  api: {
    commands: {
      sendZoneCommand: vi.fn(),
      sendNodeCommand: vi.fn(),
      getStatus: vi.fn(),
    },
  },
}))

// Mock useErrorHandler
vi.mock('../useErrorHandler', () => ({
  useErrorHandler: vi.fn(() => ({
    handleError: vi.fn((err) => {
      if (err instanceof Error) return err
      return new Error(err?.message || 'Unknown error')
    }),
    clearError: vi.fn(),
    isErrorType: vi.fn(),
    lastError: { value: null },
    errorContext: { value: null }
  }))
}))

// Mock router
vi.mock('@inertiajs/vue3', () => ({
  router: {
    reload: vi.fn()
  }
}))

describe('useCommands', () => {
  const mountUseCommands = (showToast?: (msg: string, type?: string, timeout?: number) => number) => {
    let handle: ReturnType<typeof useCommands> | null = null
    const wrapper = mount(defineComponent({
      setup() {
        handle = useCommands(showToast as never)
        return () => null
      },
    }))

    if (!handle) {
      throw new Error('useCommands not initialized')
    }

    return { wrapper, commands: handle }
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should initialize with loading false', () => {
    const { wrapper, commands } = mountUseCommands()
    expect(commands.loading.value).toBe(false)
    wrapper.unmount()
  })

  it('should send zone command', async () => {
    vi.mocked(api.commands.sendZoneCommand).mockResolvedValue({
      id: 1,
      type: 'FORCE_IRRIGATION',
      status: 'QUEUED',
    } as never)

    const { wrapper, commands } = mountUseCommands()
    const result = await commands.sendZoneCommand(1, 'FORCE_IRRIGATION', { duration_sec: 10 })

    expect(result).toMatchObject({ id: 1, status: 'QUEUED' })
    expect(api.commands.sendZoneCommand).toHaveBeenCalledWith(1, {
      type: 'FORCE_IRRIGATION',
      params: { duration_sec: 10 },
    })
    wrapper.unmount()
  })

  it('should update command status', async () => {
    vi.mocked(api.commands.sendZoneCommand).mockResolvedValue({
      id: 1,
      type: 'FORCE_IRRIGATION',
    } as never)

    const { wrapper, commands } = mountUseCommands()

    // First send a command to add it to pending
    await commands.sendZoneCommand(1, 'FORCE_IRRIGATION', { duration_sec: 10 })

    // Update status
    commands.updateCommandStatus(1, 'DONE', 'Success')

    // Check that command status was updated
    const pendingList = commands.pendingCommands.value
    const command = pendingList.find(c => c.id === 1)
    expect(command).toBeDefined()
    expect(command?.status).toBe('DONE')
    wrapper.unmount()
  })

  it('should send sensor mode commands via system channel', async () => {
    vi.mocked(api.commands.sendNodeCommand).mockResolvedValue({
      id: 7,
      type: 'activate_sensor_mode',
      status: 'QUEUED',
    } as never)

    const { wrapper, commands } = mountUseCommands()

    await commands.sendNodeCommand(42, 'activate_sensor_mode', {})
    expect(api.commands.sendNodeCommand).toHaveBeenCalledWith(42, {
      type: 'activate_sensor_mode',
      channel: 'system',
      params: {},
    })

    await commands.sendNodeCommand(42, 'deactivate_sensor_mode', {})
    expect(api.commands.sendNodeCommand).toHaveBeenCalledWith(42, {
      type: 'deactivate_sensor_mode',
      channel: 'system',
      params: {},
    })

    wrapper.unmount()
  })

  it('локализует сообщение об ошибке завершения команды', async () => {
    vi.mocked(api.commands.sendZoneCommand).mockResolvedValue({
      id: 77,
      type: 'FORCE_IRRIGATION',
      status: 'QUEUED',
    } as never)

    const showToast = vi.fn()
    const { wrapper, commands } = mountUseCommands(showToast)

    await commands.sendZoneCommand(1, 'FORCE_IRRIGATION', { duration_sec: 10 })
    commands.updateCommandStatus(77, 'ERROR', 'TIMEOUT')

    expect(showToast).toHaveBeenLastCalledWith(
      'Команда "FORCE_IRRIGATION" завершилась с ошибкой: Превышено время ожидания выполнения команды.',
      'error',
      5000,
    )

    wrapper.unmount()
  })
})
