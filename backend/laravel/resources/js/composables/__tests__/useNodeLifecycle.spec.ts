import { describe, it, expect, beforeEach, vi } from 'vitest'

vi.mock('@/utils/logger', () => ({
  logger: {
    warn: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}))

const mockLifecycleTransition = vi.hoisted(() => vi.fn())
const mockGetLifecycleAllowedTransitions = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    nodes: {
      lifecycleTransition: mockLifecycleTransition,
      getLifecycleAllowedTransitions: mockGetLifecycleAllowedTransitions,
    },
  },
}))

vi.mock('../useErrorHandler', () => ({
  useErrorHandler: () => ({
    handleError: vi.fn((err) => err),
  }),
}))

import {
  useNodeLifecycle,
  isAssignableLifecycleState,
  needsRebindConfirm,
  formatPendingBindAge,
} from '../useNodeLifecycle'

describe('useNodeLifecycle', () => {
  let mockShowToast: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockShowToast = vi.fn()
    mockLifecycleTransition.mockReset()
    mockGetLifecycleAllowedTransitions.mockReset()
  })

  it('should transition node to new state', async () => {
    const { transitionNode } = useNodeLifecycle(mockShowToast)

    mockLifecycleTransition.mockResolvedValue({
      node: { id: 1, lifecycle_state: 'ACTIVE' },
      previous_state: 'REGISTERED_BACKEND',
      current_state: 'ACTIVE',
    })

    const result = await transitionNode(1, 'ACTIVE', 'Test reason')

    expect(result).not.toBeNull()
    expect(result?.current_state).toBe('ACTIVE')
    expect(mockLifecycleTransition).toHaveBeenCalledWith(1, {
      target_state: 'ACTIVE',
      reason: 'Test reason',
    })
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.stringContaining('Узел переведен в состояние'),
      'success',
      3000
    )
  })

  it('should handle transition error', async () => {
    const { transitionNode } = useNodeLifecycle(mockShowToast)

    mockLifecycleTransition.mockRejectedValue(new Error('Transition failed'))

    const result = await transitionNode(1, 'ACTIVE', 'Test reason')

    expect(result).toBeNull()
  })

  it('should get allowed transitions', async () => {
    const { getAllowedTransitions } = useNodeLifecycle(mockShowToast)

    mockGetLifecycleAllowedTransitions.mockResolvedValue({
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
    })

    const transitions = await getAllowedTransitions(1)

    expect(transitions).not.toBeNull()
    expect(transitions?.allowed_transitions.length).toBe(2)
    expect(transitions?.current_state.value).toBe('REGISTERED_BACKEND')
    expect(mockGetLifecycleAllowedTransitions).toHaveBeenCalledWith(1)
  })

  it('should allow assign from REGISTERED_BACKEND', async () => {
    const { canAssignToZone } = useNodeLifecycle(mockShowToast)

    mockGetLifecycleAllowedTransitions.mockResolvedValue({
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
    })

    const canAssign = await canAssignToZone(1)

    expect(canAssign).toBe(true)
  })

  it('should allow assign/rebind from ACTIVE (NodeService canon)', async () => {
    const { canAssignToZone } = useNodeLifecycle(mockShowToast)

    mockGetLifecycleAllowedTransitions.mockResolvedValue({
      current_state: {
        value: 'ACTIVE',
        label: 'Активен',
        can_receive_telemetry: true,
        is_active: true,
      },
      allowed_transitions: [
        {
          value: 'REGISTERED_BACKEND',
          label: 'Зарегистрирован',
          can_receive_telemetry: false,
          is_active: false,
        },
      ],
    })

    expect(await canAssignToZone(1)).toBe(true)
  })

  it('should allow assign/rebind from ASSIGNED_TO_ZONE', async () => {
    const { canAssignToZone } = useNodeLifecycle(mockShowToast)

    mockGetLifecycleAllowedTransitions.mockResolvedValue({
      current_state: {
        value: 'ASSIGNED_TO_ZONE',
        label: 'Привязан к зоне',
        can_receive_telemetry: false,
        is_active: false,
      },
      allowed_transitions: [],
    })

    expect(await canAssignToZone(1)).toBe(true)
  })

  it('should return false for DEGRADED (not assignable by NodeService)', async () => {
    const { canAssignToZone } = useNodeLifecycle(mockShowToast)

    mockGetLifecycleAllowedTransitions.mockResolvedValue({
      current_state: {
        value: 'DEGRADED',
        label: 'С проблемами',
        can_receive_telemetry: true,
        is_active: true,
      },
      allowed_transitions: [
        {
          value: 'ACTIVE',
          label: 'Активен',
          can_receive_telemetry: true,
          is_active: true,
        },
      ],
    })

    expect(await canAssignToZone(1)).toBe(false)
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

  it('isAssignableLifecycleState matches NodeService gate', () => {
    expect(isAssignableLifecycleState('REGISTERED_BACKEND')).toBe(true)
    expect(isAssignableLifecycleState('ASSIGNED_TO_ZONE')).toBe(true)
    expect(isAssignableLifecycleState('ACTIVE')).toBe(true)
    expect(isAssignableLifecycleState('DEGRADED')).toBe(false)
    expect(isAssignableLifecycleState('MAINTENANCE')).toBe(false)
    expect(isAssignableLifecycleState(null)).toBe(false)
  })

  it('needsRebindConfirm for already assigned nodes', () => {
    expect(needsRebindConfirm({ zone_id: 5, lifecycle_state: 'ACTIVE' })).toBe(true)
    expect(needsRebindConfirm({ zone_id: null, lifecycle_state: 'ASSIGNED_TO_ZONE' })).toBe(true)
    expect(needsRebindConfirm({ zone_id: null, lifecycle_state: 'REGISTERED_BACKEND' })).toBe(false)
  })

  it('formatPendingBindAge returns human age', () => {
    const fiveMinAgo = new Date(Date.now() - 5 * 60_000).toISOString()
    expect(formatPendingBindAge(fiveMinAgo)).toBe('5 мин')
    expect(formatPendingBindAge(null)).toBeNull()
    expect(formatPendingBindAge('not-a-date')).toBeNull()
  })

  it('should track loading state', async () => {
    const { transitionNode } = useNodeLifecycle(mockShowToast)

    mockLifecycleTransition.mockImplementation(
      () => new Promise(resolve => setTimeout(() => resolve({ node: {}, previous_state: null, current_state: 'ACTIVE' }), 100))
    )

    const promise = transitionNode(1, 'ACTIVE')
    await promise
  })
})
