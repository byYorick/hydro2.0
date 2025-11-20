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
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should initialize with loading false', () => {
    const { loading } = useCommands()
    expect(loading.value).toBe(false)
  })

  it('should send zone command', async () => {
    const { useApi } = await import('../useApi')
    const mockApi = {
      api: {
        post: vi.fn().mockResolvedValue({
          data: { data: { id: 1, status: 'pending' } }
        })
      }
    }
    vi.mocked(useApi).mockReturnValue(mockApi)

    const { sendZoneCommand } = useCommands()
    const result = await sendZoneCommand(1, 'FORCE_IRRIGATION', { duration_sec: 10 })

    expect(result).toEqual({ id: 1, status: 'pending' })
    expect(mockApi.api.post).toHaveBeenCalledWith('/api/zones/1/commands', {
      type: 'FORCE_IRRIGATION',
      params: { duration_sec: 10 }
    })
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

    const { sendZoneCommand, updateCommandStatus, pendingCommands } = useCommands()
    
    // First send a command to add it to pending
    await sendZoneCommand(1, 'FORCE_IRRIGATION', { duration_sec: 10 })

    // Update status
    updateCommandStatus(1, 'completed', 'Success')

    // Check that command status was updated
    const commands = pendingCommands.value
    const command = commands.find(c => c.id === 1)
    expect(command).toBeDefined()
    expect(command?.status).toBe('completed')
  })
})

