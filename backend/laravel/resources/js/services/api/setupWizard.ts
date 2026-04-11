/**
 * Setup Wizard domain API client.
 *
 * Эндпоинты:
 *   POST /api/setup-wizard/validate-devices
 *   POST /api/setup-wizard/apply-device-bindings
 *   POST /api/setup-wizard/validate-greenhouse-climate-devices
 *   POST /api/setup-wizard/apply-greenhouse-climate-bindings
 */
import { apiPost } from './_client'

export type SetupWizardBindingsPayload = Record<string, unknown>

export const setupWizardApi = {
  validateDevices(payload: SetupWizardBindingsPayload): Promise<unknown> {
    return apiPost<unknown>('/setup-wizard/validate-devices', payload)
  },

  applyDeviceBindings(payload: SetupWizardBindingsPayload): Promise<unknown> {
    return apiPost<unknown>('/setup-wizard/apply-device-bindings', payload)
  },

  validateGreenhouseClimateDevices(payload: SetupWizardBindingsPayload): Promise<unknown> {
    return apiPost<unknown>('/setup-wizard/validate-greenhouse-climate-devices', payload)
  },

  applyGreenhouseClimateBindings(payload: SetupWizardBindingsPayload): Promise<unknown> {
    return apiPost<unknown>('/setup-wizard/apply-greenhouse-climate-bindings', payload)
  },
}
