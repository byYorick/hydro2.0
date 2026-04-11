/**
 * Automation bundles API client.
 *
 * Compiled + validated bundles для automation configs (correction, pid, etc.).
 */
import { apiGet, apiPost } from './_client'

export type AutomationBundleScope = 'system' | 'greenhouse' | 'zone' | 'grow_cycle'

export interface AutomationBundle {
  scope_type: AutomationBundleScope
  scope_id: number
  bundle_revision: string
  status: string
  config: Record<string, unknown>
  violations: unknown[]
  compiled_at: string | null
}

export const automationBundlesApi = {
  get(scope: AutomationBundleScope, id: number): Promise<AutomationBundle> {
    return apiGet<AutomationBundle>(`/automation-bundles/${scope}/${id}`)
  },

  validate(scope: AutomationBundleScope, id: number): Promise<AutomationBundle> {
    return apiPost<AutomationBundle>(`/automation-bundles/${scope}/${id}/validate`)
  },
}
