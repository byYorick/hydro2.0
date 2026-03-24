import { logger } from '@/utils/logger'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import { useAutomationCommandTemplates } from '@/composables/useAutomationCommandTemplates'
import { useAutomationDefaults } from '@/composables/useAutomationDefaults'
import {
  payloadFromZoneLogicDocument,
  resolveZoneLogicProfileEntry,
  upsertZoneLogicProfilePayload,
} from '@/composables/zoneLogicProfileAuthority'
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

// ─── Private module-level helpers ─────────────────────────────────────────────

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
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
  const automationConfig = useAutomationConfig()
  const automationDefaults = useAutomationDefaults()
  const automationCommandTemplates = useAutomationCommandTemplates()
  const { showToast, sendZoneCommand } = deps
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
  function applyServerProfileToForms(documentPayload: Record<string, unknown>): void {
    const payload = payloadFromZoneLogicDocument({
      namespace: 'zone.logic_profile',
      scope_type: 'zone',
      scope_id: Number(props.zoneId ?? 0),
      schema_version: 1,
      payload: documentPayload,
      status: 'valid',
      updated_at: null,
      updated_by: null,
    })
    const selectedEntry = resolveZoneLogicProfileEntry(payload, normalizeAutomationLogicMode(payload.active_mode, automationLogicMode.value))
    if (!selectedEntry) {
      return
    }

    automationLogicMode.value = normalizeAutomationLogicMode(payload.active_mode, selectedEntry.mode)
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
      const document = await automationConfig.getDocument<Record<string, unknown>>('zone', requestedZoneId, 'zone.logic_profile')
      if (props.zoneId !== requestedZoneId) return
      applyServerProfileToForms(document.payload ?? {})
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
      const currentDocument = await automationConfig.getDocument<Record<string, unknown>>('zone', props.zoneId, 'zone.logic_profile')
      const nextPayload = upsertZoneLogicProfilePayload(
        payloadFromZoneLogicDocument(currentDocument),
        automationLogicMode.value,
        subsystems,
        true
      )
      const updatedDocument = await automationConfig.updateDocument('zone', props.zoneId, 'zone.logic_profile', nextPayload as unknown as Record<string, unknown>)
      applyServerProfileToForms(updatedDocument.payload ?? {})
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
