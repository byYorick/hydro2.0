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
        @manual-climate="runManualClimate"
        @manual-lighting="runManualLighting"
        @manual-ph="runManualPh"
        @manual-ec="runManualEc"
      />

      <!-- Аккордеон 1: Профиль зоны -->
      <ZoneAutomationAccordionSection title="Профиль зоны" :default-open="true">
        <AutomationProfileCard
          :can-configure-automation="canConfigureAutomation"
          :telemetry-label="telemetryLabel"
          :water-topology-label="waterTopologyLabel"
          :climate-form="climateForm"
          :water-form="waterForm"
          :lighting-form="lightingForm"
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
        <section class="grid gap-4 xl:grid-cols-2">
          <PidConfigForm
            :zone-id="Number(zoneId)"
            @saved="onPidSaved"
          />
          <RelayAutotuneTrigger :zone-id="Number(zoneId)" />
        </section>
        <PumpCalibrationsPanel :zone-id="Number(zoneId)" />
      </ZoneAutomationAccordionSection>

      <!-- Аккордеон 3: Настройки Automation Engine -->
      <ZoneAutomationAccordionSection title="Настройки Automation Engine">
        <template #badge>
          <Badge variant="info">
            {{ automationEngineKeySettings.length }} параметров
          </Badge>
        </template>

        <p class="text-xs text-[color:var(--text-dim)]">
          Фактические параметры payload: `attempts`, `retries`, `timeouts`, `intervals`, `thresholds`.
        </p>

        <dl class="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2">
          <template
            v-for="item in automationEngineKeySettings"
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

        <AutomationSchedulerDevCard
          :scheduler-task-id-input="schedulerTaskIdInput"
          :scheduler-task-lookup-loading="schedulerTaskLookupLoading"
          :scheduler-task-list-loading="schedulerTaskListLoading"
          :scheduler-task-error="schedulerTaskError"
          :scheduler-task-status="schedulerTaskStatus"
          :scheduler-task-sla="schedulerTaskSla"
          :scheduler-task-done="schedulerTaskDone"
          :scheduler-task-timeline="schedulerTaskTimeline"
          :format-date-time="formatDateTime"
          :scheduler-task-status-variant="schedulerTaskStatusVariant"
          :scheduler-task-status-label="schedulerTaskStatusLabel"
          :scheduler-task-type-label="schedulerTaskTypeLabel"
          :scheduler-task-decision-label="schedulerTaskDecisionLabel"
          :scheduler-task-reason-label="schedulerTaskReasonLabel"
          :scheduler-task-error-label="schedulerTaskErrorLabel"
          :scheduler-task-process-status-variant="schedulerTaskProcessStatusVariant"
          :scheduler-task-process-status-label="schedulerTaskProcessStatusLabel"
          :scheduler-task-event-label="schedulerTaskEventLabel"
          :scheduler-task-timeline-step-label="schedulerTaskTimelineStepLabel"
          :scheduler-task-timeline-stage-label="schedulerTaskTimelineStageLabel"
          :filtered-recent-scheduler-tasks="filteredRecentSchedulerTasks"
          :scheduler-task-search="schedulerTaskSearch"
          :scheduler-task-preset="schedulerTaskPreset"
          :scheduler-task-preset-options="schedulerTaskPresetOptions"
          :scheduler-tasks-updated-at="schedulerTasksUpdatedAt"
          @lookup-task="lookupSchedulerTask"
          @refresh-list="fetchRecentSchedulerTasks"
          @update:scheduler-task-id-input="onSchedulerTaskIdInputUpdate"
          @update:scheduler-task-search="onSchedulerTaskSearchUpdate"
          @update:scheduler-task-preset="onSchedulerTaskPresetUpdate"
        />

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
        :is-applying="isApplyingProfile"
        :is-system-type-locked="isSystemTypeLocked"
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
import AutomationSchedulerDevCard from '@/Components/AutomationSchedulerDevCard.vue'
import AutomationWorkflowCard from '@/Components/AutomationWorkflowCard.vue'
import ZoneAutomationAccordionSection from '@/Components/ZoneAutomationAccordionSection.vue'
import ZoneAutomationOpsPanel from '@/Components/ZoneAutomationOpsPanel.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import PidConfigForm from '@/Components/PidConfigForm.vue'
import PumpCalibrationsPanel from '@/Components/PumpCalibrationsPanel.vue'
import RelayAutotuneTrigger from '@/Components/RelayAutotuneTrigger.vue'
import ZoneAutomationEditWizard from '@/Pages/Zones/Tabs/ZoneAutomationEditWizard.vue'
import { buildGrowthCycleConfigPayload } from '@/composables/zoneAutomationFormLogic'
import type {
  ClimateFormState,
  LightingFormState,
  SchedulerTaskPreset,
  WaterFormState,
  ZoneAutomationTabProps,
} from '@/composables/zoneAutomationTypes'
import { useZoneAutomationTab } from '@/composables/useZoneAutomationTab'
import type { AutomationState } from '@/types/Automation'
import type { PidConfigWithMeta } from '@/types/PidConfig'

interface ZoneAutomationWizardApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
}

interface AutomationEngineSettingItem {
  key: string
  label: string
  value: unknown
  unit?: string
  description?: string
}

interface AutomationEngineSettingDescriptor {
  key: string
  label: string
  unit?: string
  description: string
}

const automationEngineSettingDescriptors: AutomationEngineSettingDescriptor[] = [
  {
    key: 'subsystems.diagnostics.execution.workflow',
    label: 'diagnostics.workflow',
    description: 'Режим запуска диагностики: startup (2 бака), cycle_start (3 бака) или diagnostics (только диагностика).',
  },
  {
    key: 'subsystems.diagnostics.execution.interval_sec',
    label: 'diagnostics.interval_sec',
    unit: 'sec',
    description: 'Период выполнения диагностического цикла и проверки условий.',
  },
  {
    key: 'subsystems.diagnostics.execution.refill.duration_sec',
    label: 'refill.duration_sec',
    unit: 'sec',
    description: 'Рабочая длительность импульса долива/набора при диагностике.',
  },
  {
    key: 'subsystems.diagnostics.execution.refill.timeout_sec',
    label: 'refill.timeout_sec',
    unit: 'sec',
    description: 'Максимальное время ожидания завершения refill до фиксации timeout.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.clean_fill_timeout_sec',
    label: 'startup.clean_fill_timeout_sec',
    unit: 'sec',
    description: 'Таймаут фазы заполнения бака чистой водой в startup.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.solution_fill_timeout_sec',
    label: 'startup.solution_fill_timeout_sec',
    unit: 'sec',
    description: 'Таймаут фазы заполнения бака раствором в startup.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.prepare_recirculation_timeout_sec',
    label: 'startup.prepare_recirculation_timeout_sec',
    unit: 'sec',
    description: 'Таймаут подготовки рециркуляции перед переходом в рабочий режим.',
  },
  {
    key: 'subsystems.diagnostics.execution.startup.clean_fill_retry_cycles',
    label: 'startup.clean_fill_retry_cycles',
    description: 'Количество разрешённых повторов clean_fill при неуспешном наборе.',
  },
  {
    key: 'subsystems.diagnostics.execution.irrigation_recovery.max_continue_attempts',
    label: 'irrigation_recovery.max_continue_attempts',
    description: 'Максимум попыток продолжить полив в сценарии recovery.',
  },
  {
    key: 'subsystems.diagnostics.execution.irrigation_recovery.timeout_sec',
    label: 'irrigation_recovery.timeout_sec',
    unit: 'sec',
    description: 'Таймаут сценария восстановления irrigation_recovery.',
  },
  {
    key: 'subsystems.diagnostics.execution.prepare_tolerance.ec_pct',
    label: 'prepare_tolerance.ec_pct',
    unit: '%',
    description: 'Допуск по EC для признания фазы подготовки раствора успешной.',
  },
  {
    key: 'subsystems.diagnostics.execution.prepare_tolerance.ph_pct',
    label: 'prepare_tolerance.ph_pct',
    unit: '%',
    description: 'Допуск по pH для признания фазы подготовки раствора успешной.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.max_ec_correction_attempts',
    label: 'correction.max_ec_correction_attempts',
    description: 'Максимум попыток EC-коррекции в одном correction cycle.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.max_ph_correction_attempts',
    label: 'correction.max_ph_correction_attempts',
    description: 'Максимум попыток pH-коррекции в одном correction cycle.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.prepare_recirculation_max_attempts',
    label: 'correction.prepare_recirculation_max_attempts',
    description: 'Сколько окон рециркуляции допускается до terminal fail.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.prepare_recirculation_max_correction_attempts',
    label: 'correction.prepare_recirculation_max_correction_attempts',
    description: 'Верхний общий лимит шагов коррекции внутри окон рециркуляции.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.ec_mix_wait_sec',
    label: 'correction.ec_mix_wait_sec',
    unit: 'sec',
    description: 'Ожидание смешивания после дозирования EC перед следующей проверкой.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.ph_mix_wait_sec',
    label: 'correction.ph_mix_wait_sec',
    unit: 'sec',
    description: 'Ожидание смешивания после дозирования pH перед следующей проверкой.',
  },
  {
    key: 'subsystems.diagnostics.execution.correction.stabilization_sec',
    label: 'correction.stabilization_sec',
    unit: 'sec',
    description: 'Время стабилизации раствора перед чтением датчиков.',
  },
  {
    key: 'subsystems.irrigation.execution.interval_sec',
    label: 'irrigation.interval_sec',
    unit: 'sec',
    description: 'Период запуска полива в рабочем цикле.',
  },
  {
    key: 'subsystems.irrigation.execution.duration_sec',
    label: 'irrigation.duration_sec',
    unit: 'sec',
    description: 'Длительность одного поливочного импульса.',
  },
  {
    key: 'subsystems.climate.execution.interval_sec',
    label: 'climate.interval_sec',
    unit: 'sec',
    description: 'Период пересчёта климатического контура.',
  },
  {
    key: 'subsystems.lighting.execution.interval_sec',
    label: 'lighting.interval_sec',
    unit: 'sec',
    description: 'Период проверки и применения режима досветки.',
  },
  {
    key: 'subsystems.solution_change.execution.interval_sec',
    label: 'solution_change.interval_sec',
    unit: 'sec',
    description: 'Период запуска процедуры полной смены раствора.',
  },
  {
    key: 'subsystems.solution_change.execution.duration_sec',
    label: 'solution_change.duration_sec',
    unit: 'sec',
    description: 'Длительность одного цикла смены раствора.',
  },
]

function readByPath(source: unknown, path: string): unknown {
  if (!source || typeof source !== 'object') {
    return null
  }

  return path.split('.').reduce<unknown>((acc, segment) => {
    if (!acc || typeof acc !== 'object' || Array.isArray(acc)) {
      return null
    }

    return (acc as Record<string, unknown>)[segment]
  }, source)
}

function formatAutomationEngineSettingValue(item: AutomationEngineSettingItem): string {
  const { value, unit } = item

  if (value === null || value === undefined) {
    return '—'
  }

  let rendered: string
  if (typeof value === 'boolean') {
    rendered = value ? 'true' : 'false'
  } else if (Array.isArray(value)) {
    rendered = value.length > 0 ? value.map((entry) => String(entry)).join(', ') : '[]'
  } else if (typeof value === 'object') {
    rendered = JSON.stringify(value)
  } else {
    rendered = String(value)
  }

  if (!unit) {
    return rendered
  }

  return `${rendered} ${unit}`
}

const props = defineProps<ZoneAutomationTabProps>()

const {
  role,
  canConfigureAutomation,
  canOperateAutomation,
  isSystemTypeLocked,
  climateForm,
  waterForm,
  lightingForm,
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
  runManualClimate,
  runManualLighting,
  runManualPh,
  runManualEc,
  schedulerTaskIdInput,
  schedulerTaskLookupLoading,
  schedulerTaskListLoading,
  schedulerTaskError,
  schedulerTaskStatus,
  automationControlMode,
  allowedManualSteps,
  automationControlModeLoading,
  automationControlModeSaving,
  manualStepLoading,
  filteredRecentSchedulerTasks,
  schedulerTaskSearch,
  schedulerTaskPreset,
  schedulerTaskPresetOptions,
  schedulerTasksUpdatedAt,
  fetchRecentSchedulerTasks,
  setAutomationControlMode,
  syncControlModeFromAutomationState,
  lookupSchedulerTask,
  runManualStep,
  schedulerTaskStatusVariant,
  schedulerTaskStatusLabel,
  schedulerTaskTypeLabel,
  schedulerTaskProcessStatusVariant,
  schedulerTaskProcessStatusLabel,
  schedulerTaskTimelineStageLabel,
  schedulerTaskTimelineStepLabel,
  schedulerTaskTimelineItems,
  schedulerTaskEventLabel,
  schedulerTaskDecisionLabel,
  schedulerTaskReasonLabel,
  schedulerTaskErrorLabel,
  schedulerTaskSlaMeta,
  schedulerTaskDoneMeta,
  formatDateTime,
} = useZoneAutomationTab(props)

const zoneId = toRef(props, 'zoneId')
const showEditWizard = ref(false)
const showRuntimePayload = ref(false)
const lastAutomationSnapshot = ref<AutomationState | null>(null)
const pendingControlModeValue = ref<'auto' | 'semi' | 'manual' | null>(null)

const schedulerTaskSla = computed(() => schedulerTaskSlaMeta(schedulerTaskStatus.value))
const schedulerTaskDone = computed(() => schedulerTaskDoneMeta(schedulerTaskStatus.value))
const schedulerTaskTimeline = computed(() => schedulerTaskTimelineItems(schedulerTaskStatus.value))
const automationEngineRuntimePayload = computed(() => {
  return buildGrowthCycleConfigPayload(
    {
      climateForm,
      waterForm,
      lightingForm,
    },
    { includeSystemType: !isSystemTypeLocked.value }
  )
})
const automationEngineRuntimePayloadPretty = computed(() => {
  return JSON.stringify(automationEngineRuntimePayload.value, null, 2)
})
const automationEngineKeySettings = computed<AutomationEngineSettingItem[]>(() => {
  const payload = automationEngineRuntimePayload.value
  return automationEngineSettingDescriptors
    .map((descriptor) => ({
      key: descriptor.key,
      label: descriptor.label,
      unit: descriptor.unit,
      description: descriptor.description,
      value: readByPath(payload, descriptor.key),
    }))
    .filter((item) => item.value !== null && item.value !== undefined)
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

  const success = await applyAutomationProfile()
  if (success) {
    showEditWizard.value = false
  }
}

function onPidSaved(_config: PidConfigWithMeta): void {
  void fetchRecentSchedulerTasks()
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

function onSchedulerTaskIdInputUpdate(value: string): void {
  schedulerTaskIdInput.value = value
}

function onSchedulerTaskSearchUpdate(value: string): void {
  schedulerTaskSearch.value = value
}

function onSchedulerTaskPresetUpdate(value: SchedulerTaskPreset): void {
  schedulerTaskPreset.value = value
}
</script>
