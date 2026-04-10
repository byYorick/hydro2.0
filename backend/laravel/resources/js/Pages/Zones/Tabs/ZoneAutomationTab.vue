<template>
  <div class="space-y-4">
    <div
      v-if="!zoneId"
      class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 text-sm text-[color:var(--text-dim)]"
    >
      Нет данных зоны для автоматизации.
    </div>

    <template v-else>
      <!-- Полоса 1: Статус workflow -->
      <AutomationWorkflowCard
        :zone-id="zoneId"
        :fallback-tanks-count="waterForm.tanksCount"
        :fallback-system-type="waterForm.systemType"
        @state-snapshot="handleProcessStateSnapshot"
      />

      <!-- Полоса 2: Режим управления + быстрые действия -->
      <ZoneAutomationOpsPanel
        :can-operate-automation="canOperateAutomation"
        :quick-actions="quickActions"
        :automation-control-mode="automationControlMode"
        :allowed-manual-steps="allowedManualSteps"
        :automation-control-mode-loading="automationControlModeLoading"
        :automation-control-mode-saving="automationControlModeSaving"
        :manual-step-loading="manualStepLoading"
        :pending-control-mode-value="pendingControlModeValue"
        :automation-state-meta-label="automationStateMetaLabel"
        @select-mode="onControlModeSelect"
        @run-manual-step="runManualStep"
        @manual-irrigation="runManualIrrigation"
        @manual-lighting="runManualLighting"
        @manual-ph="runManualPh"
        @manual-ec="runManualEc"
      />

      <!-- Аккордеон 1: Профиль зоны -->
      <ZoneAutomationAccordionSection
        title="Профиль зоны"
        :default-open="true"
      >
        <AutomationProfileCard
          :can-configure-automation="canConfigureAutomation"
          :telemetry-label="telemetryLabel"
          :water-topology-label="waterTopologyLabel"
          :water-form="waterForm"
          :lighting-form="lightingForm"
          :zone-climate-enabled="zoneClimateForm.enabled"
          @edit="showEditWizard = true"
        />

        <p
          v-if="isSystemTypeLocked"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Тип системы зафиксирован для активного цикла.
        </p>

        <div class="border-t border-[color:var(--border-muted)] pt-4 space-y-4">
          <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
            <div>
              <p class="text-sm font-medium text-[color:var(--text-primary)]">
                Применение профиля автоматики
              </p>
              <p class="text-xs text-[color:var(--text-dim)] mt-0.5">
                Профиль сначала сохраняется в БД, затем отправляется `GROWTH_CYCLE_CONFIG` (`mode=adjust`, `profile_mode`).
              </p>
            </div>
            <div class="text-xs text-[color:var(--text-muted)] shrink-0">
              <span v-if="lastAppliedAt">Применён: {{ formatDateTime(lastAppliedAt) }}</span>
              <span v-else>Профиль ещё не применялся</span>
            </div>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-[220px,1fr] gap-3 items-end">
            <label class="text-xs text-[color:var(--text-muted)]">
              Режим профиля
              <select
                v-model="automationLogicMode"
                class="input-select mt-1 w-full"
                :disabled="!canConfigureAutomation || isApplyingProfile || isSyncingAutomationLogicProfile"
              >
                <option value="setup">setup</option>
                <option value="working">working</option>
              </select>
            </label>
            <div class="text-xs text-[color:var(--text-muted)]">
              <span v-if="isSyncingAutomationLogicProfile">Синхронизация профиля с бэкендом...</span>
              <span v-else-if="lastAutomationLogicSyncAt">Профиль в БД обновлён: {{ formatDateTime(lastAutomationLogicSyncAt) }}</span>
              <span v-else>Профиль в БД ещё не синхронизирован</span>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              :disabled="!canConfigureAutomation || isApplyingProfile || isSyncingAutomationLogicProfile"
              @click="applyAutomationProfile"
            >
              {{ isApplyingProfile ? 'Отправка профиля...' : (isSyncingAutomationLogicProfile ? 'Сохранение профиля...' : 'Применить профиль автоматики') }}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              :disabled="isApplyingProfile || isSyncingAutomationLogicProfile"
              @click="resetToRecommended"
            >
              Восстановить рекомендуемые значения
            </Button>
          </div>
        </div>
      </ZoneAutomationAccordionSection>

      <!-- Аккордеон 2: Коррекция и калибровка -->
      <ZoneAutomationAccordionSection title="Коррекция и калибровка">
        <ZoneCorrectionCalibrationStack
          :zone-id="Number(zoneId)"
          :sensor-calibration-settings="sensorCalibrationSettings"
          :phase-targets="currentRecipePhaseTargets"
          :save-success-seq="props.pumpCalibrationSaveSeq ?? 0"
          :run-success-seq="props.pumpCalibrationRunSeq ?? 0"
          @open-pump-calibration="emit('open-pump-calibration')"
        />
      </ZoneAutomationAccordionSection>

      <!-- Аккордеон 3: Настройки Automation Engine -->
      <ZoneAutomationAccordionSection title="Настройки Automation Engine">
        <template #badge>
          <Badge variant="info">
            {{ automationEngineKeySettings.length }} параметров
          </Badge>
        </template>

        <p class="text-xs text-[color:var(--text-dim)]">
          Здесь только low-level runtime параметры AE и zone-level override, которые не должны дублировать верхнеуровневый профиль зоны.
        </p>

        <section class="space-y-4">
          <div
            v-for="group in automationEngineSettingGroups"
            :key="group.key"
            class="rounded-xl border border-[color:var(--border-muted)] p-4 space-y-4"
          >
            <div>
              <div class="text-sm font-semibold text-[color:var(--text-primary)]">
                {{ group.label }}
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1">
                {{ group.description }}
              </div>
            </div>

            <dl class="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2">
              <template
                v-for="item in group.items"
                :key="item.key"
              >
                <dt class="text-xs text-[color:var(--text-muted)]">
                  {{ item.label }}
                </dt>
                <dd class="space-y-1">
                  <div class="text-sm font-mono text-[color:var(--text-primary)] break-all">
                    {{ formatAutomationEngineSettingValue(item) }}
                  </div>
                  <p
                    v-if="item.description"
                    class="text-xs text-[color:var(--text-dim)]"
                  >
                    {{ item.description }}
                  </p>
                </dd>
              </template>
            </dl>
          </div>
        </section>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            v-if="canConfigureAutomation"
            size="sm"
            @click="showEditWizard = true"
          >
            Редактировать конфиг зоны
          </Button>
          <Button
            size="sm"
            variant="secondary"
            @click="showRuntimePayload = !showRuntimePayload"
          >
            {{ showRuntimePayload ? 'Скрыть payload JSON' : 'Показать payload JSON' }}
          </Button>
        </div>
        <p
          v-if="!canConfigureAutomation"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Редактирование конфига доступно ролям `agronomist` и `admin`. Текущая роль: {{ role }}.
        </p>
        <pre
          v-if="showRuntimePayload"
          class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs text-[color:var(--text-primary)] overflow-auto max-h-[520px]"
        >{{ automationEngineRuntimePayloadPretty }}</pre>

        <AIPredictionsSection
          :zone-id="zoneId"
          :targets="predictionTargets"
          :horizon-minutes="60"
          :auto-refresh="true"
          :default-expanded="false"
        />
      </ZoneAutomationAccordionSection>

      <ZoneAutomationEditWizard
        :open="showEditWizard"
        :climate-form="climateForm"
        :water-form="waterForm"
        :lighting-form="lightingForm"
        :zone-climate-form="zoneClimateForm"
        :is-applying="isApplyingProfile"
        :is-system-type-locked="isSystemTypeLocked"
        :current-recipe-phase="props.currentRecipePhase ?? null"
        @close="showEditWizard = false"
        @apply="onApplyFromWizard"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import AIPredictionsSection from '@/Components/AIPredictionsSection.vue'
import AutomationProfileCard from '@/Components/AutomationProfileCard.vue'
import AutomationWorkflowCard from '@/Components/AutomationWorkflowCard.vue'
import ZoneCorrectionCalibrationStack from '@/Components/ZoneCorrectionCalibrationStack.vue'
import ZoneAutomationAccordionSection from '@/Components/ZoneAutomationAccordionSection.vue'
import ZoneAutomationOpsPanel from '@/Components/ZoneAutomationOpsPanel.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import ZoneAutomationEditWizard from '@/Pages/Zones/Tabs/ZoneAutomationEditWizard.vue'
import { useAutomationCommandTemplates } from '@/composables/useAutomationCommandTemplates'
import { useAutomationDefaults } from '@/composables/useAutomationDefaults'
import { resolveRecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import { useSensorCalibrationSettings } from '@/composables/useSensorCalibrationSettings'
import { buildGrowthCycleConfigPayload } from '@/composables/zoneAutomationFormLogic'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
  ZoneAutomationTabProps,
} from '@/composables/zoneAutomationTypes'
import { useZoneAutomationTab } from '@/composables/useZoneAutomationTab'
import type { AutomationState } from '@/types/Automation'
import {
  AUTOMATION_ENGINE_SETTING_DESCRIPTORS,
  AUTOMATION_ENGINE_SETTING_GROUP_META,
  formatAutomationEngineSettingValue,
  type AutomationEngineSettingDescriptor,
  type AutomationEngineSettingItem,
} from '@/constants/automationEngineSettings'
import { readByPath } from '@/utils/object'

interface ZoneAutomationWizardApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm: { enabled: boolean }
}

const props = defineProps<ZoneAutomationTabProps>()
const currentRecipePhaseTargets = computed(() => resolveRecipePhasePidTargets(props.currentRecipePhase ?? null))
const emit = defineEmits<{
  (e: 'open-pump-calibration'): void
}>()
const sensorCalibrationSettings = useSensorCalibrationSettings()
const automationDefaults = useAutomationDefaults()
const automationCommandTemplates = useAutomationCommandTemplates()

const {
  role,
  canConfigureAutomation,
  canOperateAutomation,
  isSystemTypeLocked,
  climateForm,
  waterForm,
  lightingForm,
  zoneClimateForm,
  quickActions,
  isApplyingProfile,
  isSyncingAutomationLogicProfile,
  lastAppliedAt,
  automationLogicMode,
  lastAutomationLogicSyncAt,
  predictionTargets,
  telemetryLabel,
  waterTopologyLabel,
  applyAutomationProfile,
  resetToRecommended,
  runManualIrrigation,
  runManualLighting,
  runManualPh,
  runManualEc,
  automationControlMode,
  allowedManualSteps,
  automationControlModeLoading,
  automationControlModeSaving,
  manualStepLoading,
  setAutomationControlMode,
  syncControlModeFromAutomationState,
  runManualStep,
  formatDateTime,
} = useZoneAutomationTab(props)

const zoneId = toRef(props, 'zoneId')
const showEditWizard = ref(false)
const showRuntimePayload = ref(false)
const lastAutomationSnapshot = ref<AutomationState | null>(null)
const pendingControlModeValue = ref<'auto' | 'semi' | 'manual' | null>(null)
const automationEngineRuntimePayload = computed(() => {
  return buildGrowthCycleConfigPayload(
    {
      climateForm,
      waterForm,
      lightingForm,
      zoneClimateForm,
    },
    {
      includeSystemType: !isSystemTypeLocked.value,
      includeClimateSubsystem: false,
      automationDefaults: automationDefaults.value,
      automationCommandTemplates: automationCommandTemplates.value,
    }
  )
})
const automationEngineRuntimePayloadPretty = computed(() => {
  return JSON.stringify(automationEngineRuntimePayload.value, null, 2)
})
const automationEngineKeySettings = computed<AutomationEngineSettingItem[]>(() => {
  const payload = automationEngineRuntimePayload.value
  return AUTOMATION_ENGINE_SETTING_DESCRIPTORS
    .map((descriptor) => ({
      key: descriptor.key,
      label: descriptor.label,
      unit: descriptor.unit,
      description: descriptor.description,
      value: readByPath(payload, descriptor.key),
    }))
    .filter((item) => item.value !== null && item.value !== undefined)
})
const automationEngineSettingGroups = computed(() => {
  return (Object.keys(AUTOMATION_ENGINE_SETTING_GROUP_META) as Array<AutomationEngineSettingDescriptor['group']>)
    .map((groupKey) => ({
      key: groupKey,
      label: AUTOMATION_ENGINE_SETTING_GROUP_META[groupKey].label,
      description: AUTOMATION_ENGINE_SETTING_GROUP_META[groupKey].description,
      items: automationEngineKeySettings.value.filter((item) => {
        const descriptor = AUTOMATION_ENGINE_SETTING_DESCRIPTORS.find((candidate) => candidate.key === item.key)
        return descriptor?.group === groupKey
      }),
    }))
    .filter((group) => group.items.length > 0)
})

const automationStateMetaLabel = computed(() => {
  const snapshot = lastAutomationSnapshot.value
  if (!snapshot?.state_meta) return null
  const source = snapshot.state_meta.source === 'cache' ? 'кэш' : 'live'
  const stale = snapshot.state_meta.is_stale ? ' (stale)' : ''
  return `Состояние: ${snapshot.state_label || snapshot.state} · источник ${source}${stale}`
})

function handleProcessStateSnapshot(snapshot: AutomationState): void {
  lastAutomationSnapshot.value = snapshot
  syncControlModeFromAutomationState(snapshot)
}

async function onApplyFromWizard(payload: ZoneAutomationWizardApplyPayload): Promise<void> {
  Object.assign(climateForm, payload.climateForm)
  Object.assign(waterForm, payload.waterForm)
  Object.assign(lightingForm, payload.lightingForm)
  Object.assign(zoneClimateForm, payload.zoneClimateForm)

  const success = await applyAutomationProfile()
  if (success) {
    showEditWizard.value = false
  }
}

async function onControlModeSelect(mode: 'auto' | 'semi' | 'manual'): Promise<void> {
  if (mode === automationControlMode.value || automationControlModeSaving.value) return
  pendingControlModeValue.value = mode
  try {
    await setAutomationControlMode(mode)
  } finally {
    pendingControlModeValue.value = null
  }
}
</script>
