import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useCommands } from '../useCommands'

// Mock useApi
vi.mock('../useApi', () => ({
  useApi: vi.fn(() => ({
    api: {
      post: vi.fn(),
      get: vi.fn()
    }
  }))
}))

// Mock useErrorHandler
vi.mock('../useErrorHandler', () => ({
  useErrorHandler: vi.fn(() => ({
    handleError: vi.fn((err) => {
      // Return normalized error
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
  const mountUseCommands = () => {
    let api: ReturnType<typeof useCommands> | null = null
    const wrapper = mount(defineComponent({
      setup() {
        api = useCommands()
        return () => null
      },
    }))

    if (!api) {
      throw new Error('useCommands not initialized')
    }

    return { wrapper, api }
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should initialize with loading false', () => {
    const { wrapper, api } = mountUseCommands()
    expect(api.loading.value).toBe(false)
    wrapper.unmount()
  })

  it('should send zone command', async () => {
    const { useApi } = await import('../useApi')
    const mockApi = {
      api: {
        post: vi.fn().mockResolvedValue({
          data: { data: { id: 1, status: 'QUEUED' } }
        })
      }
    }
    vi.mocked(useApi).mockReturnValue(mockApi)

    const { wrapper, api } = mountUseCommands()
    const result = await api.sendZoneCommand(1, 'FORCE_IRRIGATION', { duration_sec: 10 })

    expect(result).toEqual({ id: 1, status: 'QUEUED' })
    expect(mockApi.api.post).toHaveBeenCalledWith('/api/zones/1/commands', {
      type: 'FORCE_IRRIGATION',
      params: { duration_sec: 10 }
    })
    wrapper.unmount()
  })

  it('should update command status', async () => {
    const { useApi } = await import('../useApi')
    const mockApi = {
      api: {
        post: vi.fn().mockResolvedValue({
          data: { data: { id: 1 } }
        })
      }
    }
    vi.mocked(useApi).mockReturnValue(mockApi)

    const { wrapper, api } = mountUseCommands()
    
    // First send a command to add it to pending
    await api.sendZoneCommand(1, 'FORCE_IRRIGATION', { duration_sec: 10 })

    // Update status
    api.updateCommandStatus(1, 'DONE', 'Success')

    // Check that command status was updated
    const commands = api.pendingCommands.value
    const command = commands.find(c => c.id === 1)
    expect(command).toBeDefined()
    expect(command?.status).toBe('DONE')
    wrapper.unmount()
  })
})
