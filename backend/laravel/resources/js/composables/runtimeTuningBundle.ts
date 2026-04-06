import type { AutomationDocument } from '@/composables/useAutomationConfig'
import type { ProcessCalibrationMode } from '@/types/ProcessCalibration'
import type { PidConfig } from '@/types/PidConfig'

export const RUNTIME_TUNING_BUNDLE_NAMESPACE = 'zone.runtime_tuning_bundle'

export interface RuntimeTuningPreset {
  key: string
  name: string
  description?: string | null
  process_calibration: Record<ProcessCalibrationMode, Record<string, unknown>>
  pid: Record<'ph' | 'ec', PidConfig>
}

export interface RuntimeTuningBundlePayload {
  selected_preset_key: string
  presets: RuntimeTuningPreset[]
  advanced_overrides: {
    process_calibration?: Partial<Record<ProcessCalibrationMode, Record<string, unknown>>>
    pid?: Partial<Record<'ph' | 'ec', Record<string, unknown>>>
  }
  resolved_preview: {
    process_calibration: Record<ProcessCalibrationMode, Record<string, unknown>>
    pid: Record<'ph' | 'ec', PidConfig>
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function clonePidConfig(raw: unknown): PidConfig {
  return clone(raw) as PidConfig
}

function normalizePreset(input: unknown): RuntimeTuningPreset | null {
  if (!isRecord(input)) {
    return null
  }

  const processCalibration = isRecord(input.process_calibration) ? input.process_calibration : {}
  const pid = isRecord(input.pid) ? input.pid : {}

  return {
    key: typeof input.key === 'string' && input.key.trim() !== '' ? input.key : 'system_default',
    name: typeof input.name === 'string' && input.name.trim() !== '' ? input.name : 'Системный preset',
    description: typeof input.description === 'string' ? input.description : null,
    process_calibration: {
      generic: isRecord(processCalibration.generic) ? clone(processCalibration.generic) : {},
      solution_fill: isRecord(processCalibration.solution_fill) ? clone(processCalibration.solution_fill) : {},
      tank_recirc: isRecord(processCalibration.tank_recirc) ? clone(processCalibration.tank_recirc) : {},
      irrigation: isRecord(processCalibration.irrigation) ? clone(processCalibration.irrigation) : {},
    },
    pid: {
      ph: isRecord(pid.ph) ? clonePidConfig(pid.ph) : {} as PidConfig,
      ec: isRecord(pid.ec) ? clonePidConfig(pid.ec) : {} as PidConfig,
    },
  }
}

export function normalizeRuntimeTuningBundleDocument(
  document: AutomationDocument<unknown> | null | undefined,
): RuntimeTuningBundlePayload {
  const payload = isRecord(document?.payload) ? document.payload : {}
  const presets = Array.isArray(payload.presets)
    ? payload.presets.map((preset) => normalizePreset(preset)).filter((preset): preset is RuntimeTuningPreset => preset !== null)
    : []
  const selectedPresetKey = typeof payload.selected_preset_key === 'string' && payload.selected_preset_key.trim() !== ''
    ? payload.selected_preset_key
    : (presets[0]?.key ?? 'system_default')
  const advancedOverrides = isRecord(payload.advanced_overrides) ? clone(payload.advanced_overrides) : {}
  const resolvedPreview = isRecord(payload.resolved_preview) ? payload.resolved_preview : {}
  const resolvedProcessCalibration = isRecord(resolvedPreview.process_calibration) ? resolvedPreview.process_calibration : {}
  const resolvedPid = isRecord(resolvedPreview.pid) ? resolvedPreview.pid : {}

  return {
    selected_preset_key: selectedPresetKey,
    presets,
    advanced_overrides: {
      process_calibration: isRecord(advancedOverrides.process_calibration)
        ? clone(advancedOverrides.process_calibration)
        : {},
      pid: isRecord(advancedOverrides.pid)
        ? clone(advancedOverrides.pid)
        : {},
    },
    resolved_preview: {
      process_calibration: {
        generic: isRecord(resolvedProcessCalibration.generic) ? clone(resolvedProcessCalibration.generic) : {},
        solution_fill: isRecord(resolvedProcessCalibration.solution_fill) ? clone(resolvedProcessCalibration.solution_fill) : {},
        tank_recirc: isRecord(resolvedProcessCalibration.tank_recirc) ? clone(resolvedProcessCalibration.tank_recirc) : {},
        irrigation: isRecord(resolvedProcessCalibration.irrigation) ? clone(resolvedProcessCalibration.irrigation) : {},
      },
      pid: {
        ph: isRecord(resolvedPid.ph) ? clonePidConfig(resolvedPid.ph) : {} as PidConfig,
        ec: isRecord(resolvedPid.ec) ? clonePidConfig(resolvedPid.ec) : {} as PidConfig,
      },
    },
  }
}

export function selectedRuntimeTuningPreset(bundle: RuntimeTuningBundlePayload | null | undefined): RuntimeTuningPreset | null {
  if (!bundle) {
    return null
  }

  return bundle.presets.find((preset) => preset.key === bundle.selected_preset_key) ?? bundle.presets[0] ?? null
}

export function withProcessCalibrationOverride(
  bundle: RuntimeTuningBundlePayload,
  mode: ProcessCalibrationMode,
  payload: Record<string, unknown>,
): RuntimeTuningBundlePayload {
  const next = clone(bundle)
  const currentOverrides = isRecord(next.advanced_overrides.process_calibration)
    ? next.advanced_overrides.process_calibration
    : {}

  next.advanced_overrides.process_calibration = {
    ...currentOverrides,
    [mode]: clone(payload),
  }

  return next
}

export function withPidOverride(
  bundle: RuntimeTuningBundlePayload,
  type: 'ph' | 'ec',
  payload: Record<string, unknown>,
): RuntimeTuningBundlePayload {
  const next = clone(bundle)
  const currentOverrides = isRecord(next.advanced_overrides.pid)
    ? next.advanced_overrides.pid
    : {}

  next.advanced_overrides.pid = {
    ...currentOverrides,
    [type]: clone(payload),
  }

  return next
}
