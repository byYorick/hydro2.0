<template>
  <div class="zone-automation-profile-sections space-y-4">
    <RequiredDevicesSection
      v-if="showRequiredDevicesSection && !isZoneBlockLayout"
      v-model:assignments="assignments"
      :irrigation-candidates="irrigationCandidates"
      :ph-candidates="phCandidates"
      :ec-candidates="ecCandidates"
      :selected-count="requiredDevicesSelectedCount"
      :save-allowed="canSaveRequiredDevices"
    />

    <WaterContourSection
      v-if="showWaterContourSection"
      v-model:water-form="waterForm"
      v-model:assignments="assignments"
      :irrigation-candidates="irrigationCandidates"
      :ph-candidates="phCandidates"
      :ec-candidates="ecCandidates"
      :soil-moisture-candidates="soilMoistureCandidates"
      :required-devices-selected-count="requiredDevicesSelectedCount"
      :recipe-irrigation-summary="recipeIrrigationSummary"
      :recipe-soil-moisture-targets="recipeSoilMoistureTargets"
      :recipe-chemistry-summary="recipeChemistrySummary"
      :save-allowed="canSaveContourSection"
      :is-system-type-locked="isSystemTypeLocked"
    />

    <IrrigationSection
      v-if="showIrrigationSection && !isZoneBlockLayout"
      v-model:water-form="waterForm"
      :recipe-irrigation-summary="recipeIrrigationSummary"
      :recipe-soil-moisture-targets="recipeSoilMoistureTargets"
      :save-allowed="canSaveIrrigationSection"
    />

    <SolutionCorrectionSection
      v-if="showSolutionCorrectionSection && !isZoneBlockLayout"
      v-model:water-form="waterForm"
      :recipe-chemistry-summary="recipeChemistrySummary"
      :save-allowed="canSaveCorrectionSection"
      :show-correction-calibration-stack="showCorrectionCalibrationStack"
      :zone-id="zoneId"
      :sensor-calibration-settings="sensorCalibrationSettings"
    />

    <LightingSection
      v-if="showLightingSection"
      v-model:lighting-form="lightingForm"
      v-model:assignments="assignments"
      :light-candidates="lightCandidates"
      :save-allowed="canSaveLightingSection"
      :show-enable-toggle="showLightingEnableToggle"
      :show-config-fields="showLightingConfigFields"
    />

    <ZoneClimateSection
      v-if="showZoneClimateSection"
      v-model:zone-climate-form="zoneClimateForm"
      v-model:assignments="assignments"
      :co2-sensor-candidates="co2SensorCandidates"
      :co2-actuator-candidates="co2ActuatorCandidates"
      :root-vent-candidates="rootVentCandidates"
      :save-allowed="canSaveZoneClimateSection"
      :show-enable-toggle="showZoneClimateEnableToggle"
      :show-config-fields="showZoneClimateConfigFields"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import IrrigationSection from '@/Components/ZoneAutomation/IrrigationSection.vue'
import LightingSection from '@/Components/ZoneAutomation/LightingSection.vue'
import RequiredDevicesSection from '@/Components/ZoneAutomation/RequiredDevicesSection.vue'
import SolutionCorrectionSection from '@/Components/ZoneAutomation/SolutionCorrectionSection.vue'
import WaterContourSection from '@/Components/ZoneAutomation/WaterContourSection.vue'
import ZoneClimateSection from '@/Components/ZoneAutomation/ZoneClimateSection.vue'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'
import type {
  LightingFormState,
  WaterFormState,
  ZoneAutomationBindRole,
  ZoneAutomationSectionAssignments,
  ZoneAutomationSectionSaveKey,
  ZoneClimateFormState,
} from '@/composables/zoneAutomationTypes'
import { useZoneAutomationNodeCandidates } from '@/composables/zoneAutomationNodeMatching'
import { provideZoneAutomationSectionContext } from '@/composables/useZoneAutomationSectionContext'

const props = withDefaults(defineProps<{
  currentRecipePhase?: unknown | null
  layoutMode?: 'legacy' | 'zone_blocks'
  canConfigure?: boolean
  isSystemTypeLocked?: boolean
  showNodeBindings?: boolean
  showBindButtons?: boolean
  showRefreshButtons?: boolean
  bindDisabled?: boolean
  bindingInProgress?: boolean
  refreshDisabled?: boolean
  refreshingNodes?: boolean
  availableNodes?: SetupWizardNode[]
  showCorrectionCalibrationStack?: boolean
  zoneId?: number | null
  sensorCalibrationSettings?: SensorCalibrationSettings | null
  showSectionSaveButtons?: boolean
  saveDisabled?: boolean
  savingSection?: ZoneAutomationSectionSaveKey | null
  showRequiredDevicesSection?: boolean
  showWaterContourSection?: boolean
  showIrrigationSection?: boolean
  showSolutionCorrectionSection?: boolean
  showLightingSection?: boolean
  showLightingEnableToggle?: boolean
  showLightingConfigFields?: boolean
  showZoneClimateSection?: boolean
  showZoneClimateEnableToggle?: boolean
  showZoneClimateConfigFields?: boolean
}>(), {
  layoutMode: 'legacy',
  canConfigure: true,
  isSystemTypeLocked: false,
  currentRecipePhase: null,
  showNodeBindings: false,
  showBindButtons: false,
  showRefreshButtons: false,
  bindDisabled: false,
  bindingInProgress: false,
  refreshDisabled: false,
  refreshingNodes: false,
  availableNodes: () => [],
  showCorrectionCalibrationStack: false,
  zoneId: null,
  sensorCalibrationSettings: null,
  showSectionSaveButtons: false,
  saveDisabled: false,
  savingSection: null,
  showRequiredDevicesSection: true,
  showWaterContourSection: true,
  showIrrigationSection: true,
  showSolutionCorrectionSection: true,
  showLightingSection: true,
  showLightingEnableToggle: true,
  showLightingConfigFields: true,
  showZoneClimateSection: true,
  showZoneClimateEnableToggle: true,
  showZoneClimateConfigFields: true,
})

const waterForm = defineModel<WaterFormState>('waterForm', { required: true })
const lightingForm = defineModel<LightingFormState>('lightingForm', { required: true })
const zoneClimateForm = defineModel<ZoneClimateFormState>('zoneClimateForm', { required: true })
const assignments = defineModel<ZoneAutomationSectionAssignments | null>('assignments', { default: null })

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function toNullablePercent(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function toNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

const recipeSoilMoistureTargets = computed(() => {
  const phase = asRecord(props.currentRecipePhase)
  const extensions = asRecord(phase?.extensions)
  const dayNight = asRecord(extensions?.day_night)
  const soil = asRecord(dayNight?.soil_moisture)

  return {
    day: toNullablePercent(soil?.day),
    night: toNullablePercent(soil?.night),
  }
})

const recipeChemistrySummary = computed(() => {
  const phase = asRecord(props.currentRecipePhase)
  const targets = asRecord(phase?.targets)
  const phBand = asRecord(targets?.ph)
  const ecBand = asRecord(targets?.ec)

  return {
    phTarget: toNullableNumber(phase?.ph_target),
    phMin: toNullableNumber(phase?.ph_min ?? phBand?.min),
    phMax: toNullableNumber(phase?.ph_max ?? phBand?.max),
    ecTarget: toNullableNumber(phase?.ec_target),
    ecMin: toNullableNumber(phase?.ec_min ?? ecBand?.min),
    ecMax: toNullableNumber(phase?.ec_max ?? ecBand?.max),
    nutrientMode: typeof phase?.nutrient_mode === 'string' ? phase.nutrient_mode : null,
  }
})

const recipeIrrigationSummary = computed(() => {
  const phase = asRecord(props.currentRecipePhase)

  return {
    mode: typeof phase?.irrigation_mode === 'string' ? phase.irrigation_mode : null,
    intervalSec: toNullableNumber(phase?.irrigation_interval_sec),
    durationSec: toNullableNumber(phase?.irrigation_duration_sec),
  }
})

const emit = defineEmits<{
  (e: 'bind-devices', roles: ZoneAutomationBindRole[]): void
  (e: 'refresh-nodes'): void
  (e: 'save-section', section: ZoneAutomationSectionSaveKey): void
}>()

const isZoneBlockLayout = computed(() => props.layoutMode === 'zone_blocks')

function canBindSelected(value: number | null | undefined): boolean {
  return (
    Boolean(props.canConfigure)
    && !props.bindDisabled
    && !props.bindingInProgress
    && typeof value === 'number'
    && Number.isInteger(value)
    && value > 0
  )
}

const canRefreshNodes = computed(() => {
  return Boolean(props.canConfigure) && !props.refreshDisabled && !props.bindingInProgress
})

const {
  irrigation: irrigationCandidates,
  ph: phCandidates,
  ec: ecCandidates,
  light: lightCandidates,
  soilMoisture: soilMoistureCandidates,
  co2Sensor: co2SensorCandidates,
  co2Actuator: co2ActuatorCandidates,
  rootVent: rootVentCandidates,
} = useZoneAutomationNodeCandidates(() => props.availableNodes)

const requiredDevicesSelectedCount = computed(() => {
  const current = assignments.value
  if (!current) {
    return 0
  }

  return [
    current.irrigation,
    current.ph_correction,
    current.ec_correction,
  ].filter((value): value is number => typeof value === 'number' && value > 0).length
})

const hasLightingBinding = computed(() => {
  if (!lightingForm.value.enabled) {
    return true
  }

  const current = assignments.value
  return typeof current?.light === 'number' && current.light > 0
})

const hasZoneClimateBinding = computed(() => {
  if (!zoneClimateForm.value.enabled) {
    return true
  }

  const current = assignments.value
  return [
    current?.co2_sensor,
    current?.co2_actuator,
    current?.root_vent_actuator,
  ].some((value) => typeof value === 'number' && value > 0)
})

const baseSaveAllowed = computed(() => Boolean(props.canConfigure) && !props.saveDisabled)

const canSaveRequiredDevices = computed(() => {
  return baseSaveAllowed.value && requiredDevicesSelectedCount.value === 3
})

const canSaveContourSection = computed(() => {
  return baseSaveAllowed.value && (!isZoneBlockLayout.value || requiredDevicesSelectedCount.value === 3)
})

const canSaveIrrigationSection = computed(() => {
  return baseSaveAllowed.value
})

const canSaveCorrectionSection = computed(() => {
  return baseSaveAllowed.value
})

const canSaveLightingSection = computed(() => {
  return baseSaveAllowed.value && hasLightingBinding.value
})

const canSaveZoneClimateSection = computed(() => {
  return baseSaveAllowed.value && hasZoneClimateBinding.value
})

// ─── Section context provider ─────────────────────────────────────────────────
provideZoneAutomationSectionContext({
  canConfigure: computed(() => Boolean(props.canConfigure)),
  isZoneBlockLayout,
  showNodeBindings: computed(() => Boolean(props.showNodeBindings)),
  showBindButtons: computed(() => Boolean(props.showBindButtons)),
  showRefreshButtons: computed(() => Boolean(props.showRefreshButtons)),
  bindingInProgress: computed(() => Boolean(props.bindingInProgress)),
  refreshingNodes: computed(() => Boolean(props.refreshingNodes)),
  canRefreshNodes,
  canBindSelected,
  showSectionSaveButtons: computed(() => Boolean(props.showSectionSaveButtons)),
  savingSection: computed(() => props.savingSection ?? null),
  emitBindDevices: (roles) => emit('bind-devices', roles),
  emitRefreshNodes: () => emit('refresh-nodes'),
  emitSaveSection: (section) => emit('save-section', section),
})
</script>

<style scoped>
.zone-automation-profile-sections :deep(label.text-xs) {
  display: grid;
  gap: 0.32rem;
  line-height: 1.35;
}

.zone-automation-profile-sections :deep(.input-field),
.zone-automation-profile-sections :deep(.input-select) {
  height: 2.2rem;
  padding: 0 0.7rem;
  font-size: 0.78rem;
  border-radius: 0.72rem;
}

.zone-automation-profile-sections :deep(input[type='checkbox']) {
  width: 0.95rem;
  height: 0.95rem;
}
</style>
