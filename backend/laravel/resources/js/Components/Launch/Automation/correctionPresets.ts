/**
 * Hydroflow correction-profile presets — зеркало
 * `hydroflow/automation-hub.jsx::CORRECTION_PRESETS`.
 *
 * Из 13 полей preset'а реально применяются 5 (те, что есть в waterFormSchema).
 * Остальные 8 (deadband/step/maxDose/cooldown/recirc/maxStepsPerWindow/stepInterval)
 * хранятся в отдельном `automation_configs/zone.correction` doc и редактируются
 * на шаге «Калибровка» через CorrectionConfigForm.
 */
export type CorrectionProfileKey = 'safe' | 'balanced' | 'aggressive' | 'test'

export interface CorrectionPresetConfig {
  correctionDeadbandPh: number
  correctionDeadbandEc: number
  correctionStepPhMl: number
  correctionStepEcMl: number
  correctionMaxDosePhMl: number
  correctionMaxDoseEcMl: number
  correctionMaxStepsPerWindow: number
  correctionStepIntervalSec: number
  correctionCooldownSec: number
  correctionRecirculationBeforeDoseSec: number
  correctionStabilizationSec: number
  correctionMaxPhCorrectionAttempts: number
  correctionMaxEcCorrectionAttempts: number
  phPct: number
  ecPct: number
}

export interface CorrectionPreset {
  label: string
  desc: string
  config: CorrectionPresetConfig
}

export const CORRECTION_PRESETS: Record<CorrectionProfileKey, CorrectionPreset> = {
  safe: {
    label: 'Мягкий',
    desc: 'Большой deadband, маленькая доза, длинный кулдаун. Минимум вмешательства, медленная стабилизация.',
    config: {
      correctionDeadbandPh: 0.3, correctionDeadbandEc: 0.25,
      correctionStepPhMl: 1.0, correctionStepEcMl: 3.0,
      correctionMaxDosePhMl: 5.0, correctionMaxDoseEcMl: 15.0,
      correctionMaxStepsPerWindow: 4,
      correctionStepIntervalSec: 120, correctionCooldownSec: 600,
      correctionRecirculationBeforeDoseSec: 45,
      correctionStabilizationSec: 60,
      correctionMaxPhCorrectionAttempts: 3, correctionMaxEcCorrectionAttempts: 3,
      phPct: 8, ecPct: 8,
    },
  },
  balanced: {
    label: 'Оптимальный',
    desc: 'Сбалансированный профиль для большинства культур. Стандарт.',
    config: {
      correctionDeadbandPh: 0.2, correctionDeadbandEc: 0.15,
      correctionStepPhMl: 2.0, correctionStepEcMl: 5.0,
      correctionMaxDosePhMl: 8.0, correctionMaxDoseEcMl: 25.0,
      correctionMaxStepsPerWindow: 6,
      correctionStepIntervalSec: 90, correctionCooldownSec: 300,
      correctionRecirculationBeforeDoseSec: 30,
      correctionStabilizationSec: 45,
      correctionMaxPhCorrectionAttempts: 5, correctionMaxEcCorrectionAttempts: 5,
      phPct: 5, ecPct: 5,
    },
  },
  aggressive: {
    label: 'Агрессивный',
    desc: 'Малый deadband, крупные дозы, короткий кулдаун. Быстро держит цель, но риск перелива.',
    config: {
      correctionDeadbandPh: 0.1, correctionDeadbandEc: 0.08,
      correctionStepPhMl: 3.0, correctionStepEcMl: 8.0,
      correctionMaxDosePhMl: 12.0, correctionMaxDoseEcMl: 40.0,
      correctionMaxStepsPerWindow: 10,
      correctionStepIntervalSec: 60, correctionCooldownSec: 180,
      correctionRecirculationBeforeDoseSec: 20,
      correctionStabilizationSec: 30,
      correctionMaxPhCorrectionAttempts: 8, correctionMaxEcCorrectionAttempts: 8,
      phPct: 3, ecPct: 3,
    },
  },
  test: {
    label: 'Тестовый',
    desc: 'Малая доза, длинный stabilization. Для отладки PID и калибровки.',
    config: {
      correctionDeadbandPh: 0.15, correctionDeadbandEc: 0.10,
      correctionStepPhMl: 0.5, correctionStepEcMl: 1.0,
      correctionMaxDosePhMl: 2.0, correctionMaxDoseEcMl: 5.0,
      correctionMaxStepsPerWindow: 3,
      correctionStepIntervalSec: 180, correctionCooldownSec: 900,
      correctionRecirculationBeforeDoseSec: 60,
      correctionStabilizationSec: 120,
      correctionMaxPhCorrectionAttempts: 2, correctionMaxEcCorrectionAttempts: 2,
      phPct: 5, ecPct: 5,
    },
  },
}
