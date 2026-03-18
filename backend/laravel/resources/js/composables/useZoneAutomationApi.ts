import { logger } from '@/utils/logger'
import { useAutomationCommandTemplates } from '@/composables/useAutomationCommandTemplates'
import { useAutomationDefaults } from '@/composables/useAutomationDefaults'
import {
  applyAutomationFromRecipe,
  buildGrowthCycleConfigPayload,
  resetToRecommended as resetFormsToRecommended,
  validateForms,
  type ClimateFormState,
  type LightingFormState,
  type WaterFormState,
  type ZoneClimateFormState,
} from '@/composables/zoneAutomationFormLogic'
import { normalizeAutomationLogicMode, parseIsoDate, type AutomationLogicMode } from '@/composables/zoneAutomationUtils'
import type { Ref, ComputedRef } from 'vue'
import type { ZoneAutomationTabProps } from '@/composables/zoneAutomationTypes'
import type { ToastVariant } from '@/composables/useToast'

// ─── Internal types ───────────────────────────────────────────────────────────

interface AutomationLogicProfileEntry {
  mode: string
  is_active: boolean
  subsystems?: Record<string, unknown>
  updated_at?: string | null
}

interface AutomationLogicProfilesResponse {
  status: string
  data?: {
    active_mode?: string | null
    profiles?: Record<string, AutomationLogicProfileEntry>
  }
}

// ─── Private module-level helpers ─────────────────────────────────────────────

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function toAutomationLogicProfileEntry(value: unknown): AutomationLogicProfileEntry | null {
  const record = asRecord(value)
  if (!record) {
    return null
  }

  const mode = typeof record.mode === 'string' ? record.mode : null
  const isActive = typeof record.is_active === 'boolean' ? record.is_active : null
  if (!mode || isActive === null) {
    return null
  }

  const subsystems = asRecord(record.subsystems ?? null) ?? undefined
  let updatedAt: string | null = null
  if (typeof record.updated_at === 'string') {
    updatedAt = record.updated_at
  }

  return {
    mode,
    is_active: isActive,
    subsystems,
    updated_at: updatedAt,
  }
}

// ─── State interface ──────────────────────────────────────────────────────────

export interface ZoneAutomationApiState {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm: ZoneClimateFormState
  isApplyingProfile: Ref<boolean>
  isHydratingProfile: Ref<boolean>
  isSyncingAutomationLogicProfile: Ref<boolean>
  lastAppliedAt: Ref<string | null>
  automationLogicMode: Ref<AutomationLogicMode>
  lastAutomationLogicSyncAt: Ref<string | null>
  isSystemTypeLocked: ComputedRef<boolean>
  canConfigureAutomation: ComputedRef<boolean>
  loadProfileFromStorage: () => void
}

export interface ZoneAutomationApiDeps {
  get: <T = unknown>(url: string, config?: unknown) => Promise<{ data: T }>
  post: <T = unknown>(url: string, data?: unknown) => Promise<{ data: T }>
  showToast: (message: string, variant?: ToastVariant) => void
  sendZoneCommand: (zoneId: number, type: string, params?: Record<string, unknown>) => Promise<unknown>
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useZoneAutomationApi(
  props: ZoneAutomationTabProps,
  state: ZoneAutomationApiState,
  deps: ZoneAutomationApiDeps
) {
  const automationDefaults = useAutomationDefaults()
  const automationCommandTemplates = useAutomationCommandTemplates()
  const { get, post, showToast, sendZoneCommand } = deps
  const {
    climateForm,
    waterForm,
    lightingForm,
    zoneClimateForm,
    isApplyingProfile,
    isHydratingProfile,
    isSyncingAutomationLogicProfile,
    lastAppliedAt,
    automationLogicMode,
    lastAutomationLogicSyncAt,
    isSystemTypeLocked,
    canConfigureAutomation,
    loadProfileFromStorage,
  } = state

  // ─── Private functions ─────────────────────────────────────────────────────

  function resolveAutomationProfileEntry(
    data: AutomationLogicProfilesResponse['data']
  ): AutomationLogicProfileEntry | null {
    const profiles = asRecord(data?.profiles ?? null)
    if (!profiles) {
      return null
    }

    const activeMode = normalizeAutomationLogicMode(data?.active_mode, automationLogicMode.value)
    automationLogicMode.value = activeMode
    const activeEntry = toAutomationLogicProfileEntry(profiles[activeMode])
    if (activeEntry) {
      return activeEntry
    }

    const workingEntry = toAutomationLogicProfileEntry(profiles.working)
    if (workingEntry) {
      automationLogicMode.value = 'working'
      return workingEntry
    }

    const setupEntry = toAutomationLogicProfileEntry(profiles.setup)
    if (setupEntry) {
      automationLogicMode.value = 'setup'
      return setupEntry
    }

    return null
  }

  function applyServerProfileToForms(data: AutomationLogicProfilesResponse['data']): void {
    const selectedEntry = resolveAutomationProfileEntry(data)
    if (!selectedEntry) {
      return
    }

    const subsystems = asRecord(selectedEntry.subsystems ?? null)
    if (!subsystems) {
      return
    }

    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems,
        },
      },
      { climateForm, waterForm, lightingForm }
    )
    zoneClimateForm.enabled = Boolean(asRecord(subsystems.zone_climate)?.enabled ?? false)

    const syncedAt = parseIsoDate(selectedEntry.updated_at ?? null)
    lastAutomationLogicSyncAt.value = syncedAt ? syncedAt.toISOString() : null
  }

  // ─── Public functions ──────────────────────────────────────────────────────

  async function fetchAutomationLogicProfileFromServer(): Promise<void> {
    if (!props.zoneId) return

    const requestedZoneId = props.zoneId
    try {
      const response = await get<AutomationLogicProfilesResponse>(`/api/zones/${requestedZoneId}/automation-logic-profile`)
      if (props.zoneId !== requestedZoneId) return
      applyServerProfileToForms((response.data as AutomationLogicProfilesResponse)?.data)
    } catch (error) {
      if (props.zoneId !== requestedZoneId) return
      logger.warn('[ZoneAutomationTab] Failed to fetch automation logic profile', { error, zoneId: requestedZoneId })
    }
  }

  async function persistAutomationLogicProfile(subsystems: Record<string, unknown>): Promise<boolean> {
    if (!props.zoneId) {
      return false
    }

    isSyncingAutomationLogicProfile.value = true
    try {
      const response = await post<AutomationLogicProfilesResponse>(
        `/api/zones/${props.zoneId}/automation-logic-profile`,
        {
          mode: automationLogicMode.value,
          activate: true,
          subsystems,
        }
      )
      applyServerProfileToForms((response.data as AutomationLogicProfilesResponse)?.data)
      return true
    } catch (error) {
      logger.error('[ZoneAutomationTab] Failed to persist automation logic profile', {
        error,
        zoneId: props.zoneId,
        mode: automationLogicMode.value,
      })
      return false
    } finally {
      isSyncingAutomationLogicProfile.value = false
    }
  }

  async function hydrateAutomationProfileFromCurrentZone(options?: { includeTargets?: boolean }): Promise<void> {
    const includeTargets = options?.includeTargets ?? true
    isHydratingProfile.value = true
    try {
      resetFormsToRecommended({ climateForm, waterForm, lightingForm }, automationDefaults.value)
      zoneClimateForm.enabled = false
      lastAppliedAt.value = null
      lastAutomationLogicSyncAt.value = null
      automationLogicMode.value = 'working'
      loadProfileFromStorage()
      if (includeTargets) {
        applyAutomationFromRecipe(props.targets, { climateForm, waterForm, lightingForm })
      }
      await fetchAutomationLogicProfileFromServer()
    } finally {
      isHydratingProfile.value = false
    }
  }

  async function applyAutomationProfile(): Promise<boolean> {
    if (!props.zoneId || isApplyingProfile.value) return false

    if (!canConfigureAutomation.value) {
      showToast('Изменение профиля доступно только агроному.', 'warning')
      return false
    }

    const validationError = validateForms({ climateForm, waterForm })
    if (validationError) {
      showToast(validationError, 'error')
      return false
    }

    isApplyingProfile.value = true

    try {
      const payload = buildGrowthCycleConfigPayload(
        { climateForm, waterForm, lightingForm, zoneClimateForm },
        {
          includeSystemType: !isSystemTypeLocked.value,
          includeClimateSubsystem: false,
          automationDefaults: automationDefaults.value,
          automationCommandTemplates: automationCommandTemplates.value,
        }
      )
      const payloadRecord = asRecord(payload)
      const subsystems = asRecord(payloadRecord?.subsystems ?? null)
      if (!subsystems) {
        showToast('Невозможно собрать subsystems из профиля автоматики.', 'error')
        return false
      }

      const persisted = await persistAutomationLogicProfile(subsystems)
      if (!persisted) {
        showToast('Не удалось сохранить профиль логики автоматики в бэкенд.', 'error')
        return false
      }

      await sendZoneCommand(props.zoneId, 'GROWTH_CYCLE_CONFIG', {
        mode: 'adjust',
        profile_mode: automationLogicMode.value,
      })
      lastAppliedAt.value = new Date().toISOString()
      showToast('Профиль автоматики отправлен в scheduler.', 'success')
      return true
    } catch (error) {
      logger.error('[ZoneAutomationTab] Failed to apply automation profile', { error })
      return false
    } finally {
      isApplyingProfile.value = false
    }
  }

  return {
    applyAutomationProfile,
    hydrateAutomationProfileFromCurrentZone,
  }
}
