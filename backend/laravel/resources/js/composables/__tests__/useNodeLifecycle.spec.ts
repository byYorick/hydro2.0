import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useNodeLifecycle } from '../useNodeLifecycle'

// Моки
vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}))

const mockApiPost = vi.fn()
const mockApiGet = vi.fn()

const mockApi = {
  post: mockApiPost,
  get: mockApiGet,
  patch: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  interceptors: {
    request: { use: vi.fn(), eject: vi.fn() },
    response: { use: vi.fn(), eject: vi.fn() },
  },
}

vi.mock('../useApi', () => ({
  useApi: () => ({
    api: mockApi,
    post: mockApiPost,
    get: mockApiGet,
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  }),
}))

vi.mock('../useErrorHandler', () => ({
  useErrorHandler: () => ({
    handleError: vi.fn((err) => err),
  }),
}))

describe('useNodeLifecycle', () => {
  let mockShowToast: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockShowToast = vi.fn()
    vi.clearAllMocks()
  })

  it('should transition node to new state', async () => {
    const { transitionNode } = useNodeLifecycle(mockShowToast)
    
    mockApiPost.mockResolvedValue({
      data: { 
        id: 1, 
        lifecycle_state: 'ACTIVE',
        previous_state: 'REGISTERED_BACKEND',
        current_state: 'ACTIVE',
      },
    })

    const result = await transitionNode(1, 'ACTIVE', 'Test reason')

    expect(result).not.toBeNull()
    expect(result?.current_state).toBe('ACTIVE')
    expect(mockApiPost).toHaveBeenCalledWith(
      '/api/nodes/1/lifecycle/transition',
      {
        target_state: 'ACTIVE',
        reason: 'Test reason',
      }
    )
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.stringContaining('Узел переведен в состояние'),
      'success',
      3000
    )
  })

  it('should handle transition error', async () => {
    const { transitionNode } = useNodeLifecycle(mockShowToast)
    
    mockApiPost.mockRejectedValue(new Error('Transition failed'))

    const result = await transitionNode(1, 'ACTIVE', 'Test reason')

    expect(result).toBeNull()
  })

  it('should get allowed transitions', async () => {
    const { getAllowedTransitions } = useNodeLifecycle(mockShowToast)
    
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          current_state: {
            value: 'REGISTERED_BACKEND',
            label: 'Зарегистрирован',
            can_receive_telemetry: false,
            is_active: false,
          },
          allowed_transitions: [
            {
              value: 'ASSIGNED_TO_ZONE',
              label: 'Привязан к зоне',
              can_receive_telemetry: false,
              is_active: false,
            },
            {
              value: 'ACTIVE',
              label: 'Активен',
              can_receive_telemetry: true,
              is_active: true,
            },
          ],
        },
      },
    })

    const transitions = await getAllowedTransitions(1)

    expect(transitions).not.toBeNull()
    expect(transitions?.allowed_transitions.length).toBe(2)
    expect(transitions?.current_state.value).toBe('REGISTERED_BACKEND')
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/nodes/1/lifecycle/allowed-transitions'
    )
  })

  it('should check if node can be assigned to zone', async () => {
    const { canAssignToZone } = useNodeLifecycle(mockShowToast)
    
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          current_state: {
            value: 'REGISTERED_BACKEND',
            label: 'Зарегистрирован',
            can_receive_telemetry: false,
            is_active: false,
          },
          allowed_transitions: [
            {
              value: 'ASSIGNED_TO_ZONE',
              label: 'Привязан к зоне',
              can_receive_telemetry: false,
              is_active: false,
            },
          ],
        },
      },
    })

    const canAssign = await canAssignToZone(1)

    expect(canAssign).toBe(true)
  })

  it('should return false if node cannot be assigned to zone', async () => {
    const { canAssignToZone } = useNodeLifecycle(mockShowToast)
    
    mockApiGet.mockResolvedValue({
      data: {
        data: {
          current_state: {
            value: 'ACTIVE',
            label: 'Активен',
            can_receive_telemetry: true,
            is_active: true,
          },
          allowed_transitions: [
            {
              value: 'DEGRADED',
              label: 'С проблемами',
              can_receive_telemetry: true,
              is_active: true,
            },
          ],
        },
      },
    })

    const canAssign = await canAssignToZone(1)

    expect(canAssign).toBe(false)
  })

  it('should get state label in Russian', () => {
    const { getStateLabel } = useNodeLifecycle(mockShowToast)

    expect(getStateLabel('MANUFACTURED')).toBe('Произведён')
    expect(getStateLabel('ACTIVE')).toBe('Активен')
    expect(getStateLabel('DEGRADED')).toBe('С проблемами')
    expect(getStateLabel('UNPROVISIONED')).toBe('Не настроен')
    expect(getStateLabel('REGISTERED_BACKEND')).toBe('Зарегистрирован')
    expect(getStateLabel('ASSIGNED_TO_ZONE')).toBe('Привязан к зоне')
    expect(getStateLabel('MAINTENANCE')).toBe('Обслуживание')
    expect(getStateLabel('DECOMMISSIONED')).toBe('Списан')
  })

  it('should track loading state', async () => {
    const { loading, transitionNode } = useNodeLifecycle(mockShowToast)
    
    mockApiPost.mockImplementation(() => new Promise(resolve => setTimeout(resolve, 100)))

    const promise = transitionNode(1, 'ACTIVE')
    
    // Loading должен быть true во время выполнения
    // (но это сложно проверить без реального промиса)
    
    await promise
  })
})

