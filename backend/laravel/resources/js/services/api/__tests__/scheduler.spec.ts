import { beforeEach, expect, it, vi } from 'vitest'
import { zonesApi } from '../zones'
import { systemApi } from '../system'
import { apiGet, apiPost } from '../_client'
vi.mock('../_client', () => ({ apiClient: {}, apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(), apiDelete: vi.fn(), apiPatch: vi.fn(), apiPostVoid: vi.fn() }))
beforeEach(() => vi.clearAllMocks())
it('passes inline-error ownership through observer requests without changing URLs or query parameters', async () => {
  await zonesApi.scheduleWorkspace(7, { horizon: '7d' }, { skipErrorToast: true })
  expect(apiGet).toHaveBeenLastCalledWith('/zones/7/schedule-workspace', { params: { horizon: '7d' }, skipErrorToast: true })
  await zonesApi.getState(7, { skipErrorToast: true })
  expect(apiGet).toHaveBeenLastCalledWith('/zones/7/state', { skipErrorToast: true })
  await zonesApi.getExecution(7, '81', { skipErrorToast: true })
  expect(apiGet).toHaveBeenLastCalledWith('/zones/7/executions/81', { skipErrorToast: true })
  await zonesApi.schedulerDiagnostics(7, { skipErrorToast: true })
  expect(apiGet).toHaveBeenLastCalledWith('/zones/7/scheduler-diagnostics', { skipErrorToast: true })
})
it('uses the authenticated JSON view and delegates retry errors to the action handler', async () => {
  await systemApi.schedulerObservability()
  expect(apiGet).toHaveBeenLastCalledWith('/system/scheduler/observability', { skipErrorToast: true })
  await zonesApi.retryExecution(7, '81')
  expect(apiPost).toHaveBeenLastCalledWith('/zones/7/executions/81/retry', {}, { skipErrorToast: true })
})
