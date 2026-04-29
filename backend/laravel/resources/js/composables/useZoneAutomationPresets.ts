import { ref, type Ref } from 'vue'
import { api } from '@/services/api'
import type {
  ZoneAutomationPreset,
  ZoneAutomationPresetConfig,
  ZoneAutomationPresetCreatePayload,
  ZoneAutomationPresetFilters,
  IrrigationSystemType,
  CorrectionProfile,
  StartupFailSafeGuardsConfig,
} from '@/types/ZoneAutomationPreset'
import type { WaterFormState } from './zoneAutomationTypes'
import { FALLBACK_AUTOMATION_DEFAULTS } from './useAutomationDefaults'

function resolvePresetStartupFailSafe(
  startup: ZoneAutomationPresetConfig['startup'],
): StartupFailSafeGuardsConfig {
  const fb = FALLBACK_AUTOMATION_DEFAULTS
  const g = startup.fail_safe_guards
  return {
    clean_fill_min_check_delay_ms: g?.clean_fill_min_check_delay_ms ?? fb.water_clean_fill_min_check_delay_ms,
    solution_fill_clean_min_check_delay_ms:
      g?.solution_fill_clean_min_check_delay_ms ?? fb.water_solution_fill_clean_min_check_delay_ms,
    solution_fill_solution_min_check_delay_ms:
      g?.solution_fill_solution_min_check_delay_ms ?? fb.water_solution_fill_solution_min_check_delay_ms,
    recirculation_stop_on_solution_min:
      g?.recirculation_stop_on_solution_min ?? fb.water_recirculation_stop_on_solution_min,
    irrigation_stop_on_solution_min:
      g?.irrigation_stop_on_solution_min ?? fb.water_irrigation_stop_on_solution_min,
    estop_debounce_ms: g?.estop_debounce_ms ?? fb.water_estop_debounce_ms,
  }
}

export function useZoneAutomationPresets() {
  const presets: Ref<ZoneAutomationPreset[]> = ref([])
  const loading: Ref<boolean> = ref(false)
  const error: Ref<string | null> = ref(null)

  async function loadPresets(filters?: ZoneAutomationPresetFilters): Promise<void> {
    loading.value = true
    error.value = null
    try {
      presets.value = await api.zoneAutomationPresets.list(filters)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to load presets'
    } finally {
      loading.value = false
    }
  }

  async function createPreset(payload: ZoneAutomationPresetCreatePayload): Promise<ZoneAutomationPreset | null> {
    loading.value = true
    error.value = null
    try {
      const created = await api.zoneAutomationPresets.create(payload)
      presets.value = [...presets.value, created]
      return created
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to create preset'
      return null
    } finally {
      loading.value = false
    }
  }

  async function deletePreset(id: number): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      await api.zoneAutomationPresets.delete(id)
      presets.value = presets.value.filter(p => p.id !== id)
      return true
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to delete preset'
      return false
    } finally {
      loading.value = false
    }
  }

  async function duplicatePreset(id: number): Promise<ZoneAutomationPreset | null> {
    loading.value = true
    error.value = null
    try {
      const created = await api.zoneAutomationPresets.duplicate(id)
      presets.value = [...presets.value, created]
      return created
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Failed to duplicate preset'
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    presets,
    loading,
    error,
    loadPresets,
    createPreset,
    deletePreset,
    duplicatePreset,
  }
}

/**
 * Применить preset config к WaterFormState.
 * Изменяет только поля, которые есть в preset.config — остальные нетронуты.
 */
export function applyPresetToWaterForm(
  preset: ZoneAutomationPreset,
  form: WaterFormState,
): WaterFormState {
  const cfg = preset.config
  const failSafe = resolvePresetStartupFailSafe(cfg.startup)

  return {
    ...form,
    // Irrigation
    durationSeconds: cfg.irrigation.duration_sec,
    intervalMinutes: Math.round(cfg.irrigation.interval_sec / 60),
    correctionDuringIrrigation: cfg.irrigation.correction_during_irrigation,
    // Irrigation decision
    irrigationDecisionStrategy: cfg.irrigation_decision.strategy,
    irrigationDecisionLookbackSeconds: cfg.irrigation_decision.config?.lookback_sec ?? form.irrigationDecisionLookbackSeconds,
    irrigationDecisionMinSamples: cfg.irrigation_decision.config?.min_samples ?? form.irrigationDecisionMinSamples,
    irrigationDecisionStaleAfterSeconds: cfg.irrigation_decision.config?.stale_after_sec ?? form.irrigationDecisionStaleAfterSeconds,
    irrigationDecisionHysteresisPct: cfg.irrigation_decision.config?.hysteresis_pct ?? form.irrigationDecisionHysteresisPct,
    irrigationDecisionSpreadAlertThresholdPct: cfg.irrigation_decision.config?.spread_alert_threshold_pct ?? form.irrigationDecisionSpreadAlertThresholdPct,
    // Startup
    startupCleanFillTimeoutSeconds: cfg.startup.clean_fill_timeout_sec,
    startupSolutionFillTimeoutSeconds: cfg.startup.solution_fill_timeout_sec,
    startupPrepareRecirculationTimeoutSeconds: cfg.startup.prepare_recirculation_timeout_sec,
    startupCleanFillRetryCycles: cfg.startup.clean_fill_retry_cycles,
    cleanFillMinCheckDelayMs: failSafe.clean_fill_min_check_delay_ms,
    solutionFillCleanMinCheckDelayMs: failSafe.solution_fill_clean_min_check_delay_ms,
    solutionFillSolutionMinCheckDelayMs: failSafe.solution_fill_solution_min_check_delay_ms,
    recirculationStopOnSolutionMin: failSafe.recirculation_stop_on_solution_min,
    stopOnSolutionMin: failSafe.irrigation_stop_on_solution_min,
    estopDebounceMs: failSafe.estop_debounce_ms,
    // System type from preset
    tanksCount: preset.tanks_count,
  }
}

/**
 * Собрать preset payload из текущих значений WaterFormState.
 */
export function buildPresetFromWaterForm(
  form: WaterFormState,
  meta: {
    name: string
    description?: string | null
    irrigationSystemType: IrrigationSystemType
    correctionPresetId?: number | null
    correctionProfile?: CorrectionProfile | null
  },
): ZoneAutomationPresetCreatePayload {
  const fb = FALLBACK_AUTOMATION_DEFAULTS
  const config: ZoneAutomationPresetConfig = {
    irrigation: {
      duration_sec: form.durationSeconds,
      interval_sec: form.intervalMinutes * 60,
      correction_during_irrigation: form.correctionDuringIrrigation,
      correction_slack_sec: 30,
    },
    irrigation_decision: {
      strategy: form.irrigationDecisionStrategy ?? 'task',
      ...(form.irrigationDecisionStrategy === 'smart_soil_v1'
        ? {
            config: {
              lookback_sec: form.irrigationDecisionLookbackSeconds,
              min_samples: form.irrigationDecisionMinSamples,
              stale_after_sec: form.irrigationDecisionStaleAfterSeconds,
              hysteresis_pct: form.irrigationDecisionHysteresisPct,
              spread_alert_threshold_pct: form.irrigationDecisionSpreadAlertThresholdPct,
            },
          }
        : {}),
    },
    startup: {
      clean_fill_timeout_sec: form.startupCleanFillTimeoutSeconds ?? 1200,
      solution_fill_timeout_sec: form.startupSolutionFillTimeoutSeconds ?? 1800,
      prepare_recirculation_timeout_sec: form.startupPrepareRecirculationTimeoutSeconds ?? 1200,
      level_poll_interval_sec: 60,
      clean_fill_retry_cycles: form.startupCleanFillRetryCycles ?? 1,
      fail_safe_guards: {
        clean_fill_min_check_delay_ms: form.cleanFillMinCheckDelayMs ?? fb.water_clean_fill_min_check_delay_ms,
        solution_fill_clean_min_check_delay_ms:
          form.solutionFillCleanMinCheckDelayMs ?? fb.water_solution_fill_clean_min_check_delay_ms,
        solution_fill_solution_min_check_delay_ms:
          form.solutionFillSolutionMinCheckDelayMs ?? fb.water_solution_fill_solution_min_check_delay_ms,
        recirculation_stop_on_solution_min:
          form.recirculationStopOnSolutionMin ?? fb.water_recirculation_stop_on_solution_min,
        irrigation_stop_on_solution_min: form.stopOnSolutionMin ?? fb.water_irrigation_stop_on_solution_min,
        estop_debounce_ms: form.estopDebounceMs ?? fb.water_estop_debounce_ms,
      },
    },
    climate: null,
    lighting: null,
  }

  return {
    name: meta.name,
    description: meta.description,
    tanks_count: (form.tanksCount === 3 ? 3 : 2) as 2 | 3,
    irrigation_system_type: meta.irrigationSystemType,
    correction_preset_id: meta.correctionPresetId,
    correction_profile: meta.correctionProfile,
    config,
  }
}

/**
 * Проверить изменился ли WaterFormState относительно применённого пресета.
 */
export function isPresetModified(
  preset: ZoneAutomationPreset,
  form: WaterFormState,
): boolean {
  const cfg = preset.config
  const fb = FALLBACK_AUTOMATION_DEFAULTS
  const failSafe = resolvePresetStartupFailSafe(cfg.startup)
  const cleanFillDelay = form.cleanFillMinCheckDelayMs ?? fb.water_clean_fill_min_check_delay_ms
  const solutionCleanDelay = form.solutionFillCleanMinCheckDelayMs ?? fb.water_solution_fill_clean_min_check_delay_ms
  const solutionMinDelay = form.solutionFillSolutionMinCheckDelayMs ?? fb.water_solution_fill_solution_min_check_delay_ms
  const recircStop = form.recirculationStopOnSolutionMin ?? fb.water_recirculation_stop_on_solution_min
  const irrigStop = form.stopOnSolutionMin ?? fb.water_irrigation_stop_on_solution_min
  const estopMs = form.estopDebounceMs ?? fb.water_estop_debounce_ms
  return (
    form.durationSeconds !== cfg.irrigation.duration_sec
    || Math.round(cfg.irrigation.interval_sec / 60) !== form.intervalMinutes
    || form.correctionDuringIrrigation !== cfg.irrigation.correction_during_irrigation
    || (form.irrigationDecisionStrategy ?? 'task') !== cfg.irrigation_decision.strategy
    || form.startupCleanFillTimeoutSeconds !== cfg.startup.clean_fill_timeout_sec
    || form.startupSolutionFillTimeoutSeconds !== cfg.startup.solution_fill_timeout_sec
    || form.startupPrepareRecirculationTimeoutSeconds !== cfg.startup.prepare_recirculation_timeout_sec
    || cleanFillDelay !== failSafe.clean_fill_min_check_delay_ms
    || solutionCleanDelay !== failSafe.solution_fill_clean_min_check_delay_ms
    || solutionMinDelay !== failSafe.solution_fill_solution_min_check_delay_ms
    || recircStop !== failSafe.recirculation_stop_on_solution_min
    || irrigStop !== failSafe.irrigation_stop_on_solution_min
    || estopMs !== failSafe.estop_debounce_ms
    || form.tanksCount !== preset.tanks_count
  )
}
