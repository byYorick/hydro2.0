/**
 * Сводка настроек EC-коррекции для фазы irrigation (AE3 zone.correction), для UI.
 */
export interface IrrigationCorrectionSummary {
  ec_dosing_mode: string
  ec_excluded_components: string[]
  ec_component_ratios: Record<string, unknown>
  ec_component_policy_irrigation: Record<string, unknown>
  dose_ec_channel: string | null
  correction_during_irrigation: boolean | null
}
