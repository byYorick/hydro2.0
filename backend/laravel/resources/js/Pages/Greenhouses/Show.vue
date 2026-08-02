<template>
  <AppLayout>
    <div class="space-y-5">
      <section class="ui-hero p-5 md:p-6 space-y-5">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-muted)]">
                {{ greenhouse.type || 'Теплица' }}
              </p>
              <span
                v-if="greenhouse.timezone"
                class="rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2 py-0.5 text-[11px] text-[color:var(--text-muted)]"
              >
                {{ greenhouse.timezone }}
              </span>
              <span
                class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px]"
                :class="greenhouseClimateEnabled
                  ? 'border-[color:var(--accent-green)]/35 bg-[color:var(--accent-green)]/10 text-[color:var(--accent-green)]'
                  : 'border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'"
              >
                <span
                  class="ui-state-dot"
                  :class="greenhouseClimateEnabled ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--text-dim)]'"
                />
                Климат {{ greenhouseClimateEnabled ? 'вкл' : 'выкл' }}
              </span>
            </div>
            <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              {{ greenhouse.name }}
            </h1>
            <p class="max-w-2xl text-sm text-[color:var(--text-muted)]">
              {{ greenhouse.description || 'Состояние теплицы, зон и оборудования в одном месте.' }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2 shrink-0">
            <Link href="/zones">
              <Button
                size="sm"
                variant="outline"
              >
                Все зоны
              </Button>
            </Link>
            <Button
              v-if="canConfigureGreenhouse"
              size="sm"
              @click="openZoneWizardGuarded()"
            >
              <svg
                class="mr-1 h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 4v16m8-8H4"
                />
              </svg>
              Новая зона
            </Button>
          </div>
        </div>

        <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-3">
          <div
            class="ui-kpi-card"
            data-testid="greenhouse-kpi-zones"
          >
            <div class="ui-kpi-label">
              Зоны
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
              {{ zones.length }}
            </div>
            <div class="ui-kpi-hint">
              Всего в теплице
            </div>
          </div>
          <div
            class="ui-kpi-card"
            data-testid="greenhouse-kpi-nodes"
          >
            <div class="ui-kpi-label">
              Узлы онлайн
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
              {{ nodeSummary.online }}<span class="text-base font-semibold text-[color:var(--text-muted)]">/{{ nodeSummary.total ?? nodes.length }}</span>
            </div>
            <div class="ui-kpi-hint">
              Offline: {{ nodeSummary.offline }}
            </div>
          </div>
          <div
            class="ui-kpi-card"
            data-testid="greenhouse-kpi-alerts"
            :class="activeAlerts > 0 ? 'border-[color:var(--accent-red)]/45' : ''"
          >
            <div class="ui-kpi-label">
              Оповещения
            </div>
            <div
              class="ui-kpi-value"
              :class="activeAlerts > 0 ? 'text-[color:var(--accent-red)]' : ''"
            >
              {{ activeAlerts }}
            </div>
            <div class="ui-kpi-hint">
              {{ activeAlerts > 0 ? 'Требуют внимания' : 'Активных нет' }}
            </div>
          </div>
        </div>

        <div
          v-if="activeAlerts > 0"
          class="flex flex-col gap-2 rounded-xl border border-[color:var(--accent-red)]/35 bg-[color:var(--accent-red)]/8 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="flex items-start gap-2 text-sm text-[color:var(--text-primary)]">
            <svg
              class="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--accent-red)]"
              fill="currentColor"
              viewBox="0 0 20 20"
            >
              <path
                fill-rule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clip-rule="evenodd"
              />
            </svg>
            <span>
              Активных оповещений: <strong class="tabular-nums">{{ activeAlerts }}</strong>. Проверьте зоны и узлы перед запуском циклов.
            </span>
          </div>
          <Link
            href="/alerts"
            class="text-xs font-medium text-[color:var(--accent-red)] hover:underline shrink-0"
          >
            Открыть оповещения
          </Link>
        </div>
      </section>

      <section class="space-y-4">
        <div class="ui-section-header !mb-0">
          <div>
            <h2 class="ui-section-title">
              Управление теплицей
            </h2>
            <p class="ui-section-subtitle mt-0.5">
              Климат теплицы и обслуживание climate/weather оборудования.
            </p>
          </div>
        </div>

        <div class="grid gap-4 xl:grid-cols-12">
          <aside class="surface-card flex flex-col gap-4 rounded-2xl border border-[color:var(--border-muted)] p-4 xl:col-span-4">
            <div class="space-y-1">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">
                  Обслуживание
                </h3>
                <span
                  class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] tabular-nums"
                  :class="maintenanceExitTargets.length > 0
                    ? 'border-[color:var(--accent-amber)]/40 bg-[color:var(--accent-amber)]/10 text-[color:var(--accent-amber)]'
                    : 'border-[color:var(--border-muted)] text-[color:var(--text-muted)]'"
                >
                  <span
                    class="h-1.5 w-1.5 rounded-full"
                    :class="maintenanceExitTargets.length > 0 ? 'bg-[color:var(--accent-amber)]' : 'bg-[color:var(--accent-green)]'"
                  />
                  {{ maintenanceExitTargets.length > 0 ? 'Есть в maintenance' : 'Нет в maintenance' }}
                </span>
              </div>
              <p class="text-xs text-[color:var(--text-muted)]">
                Lifecycle <code class="text-[color:var(--text-primary)]">MAINTENANCE</code> для узлов теплицы.
              </p>
            </div>

            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/35 px-3 py-2.5 text-xs text-[color:var(--text-muted)] space-y-1.5">
              <div class="font-medium text-[color:var(--text-primary)]">
                Что входит
              </div>
              <ul class="list-disc space-y-1 pl-4">
                <li>Все узлы зон теплицы: pH, EC, irrig, climate, light, relay и др.</li>
                <li>Перевод в <code>MAINTENANCE</code>: статус offline, телеметрия не принимается как рабочая.</li>
                <li>Для калибровки, ремонта, замены датчиков/насосов без списания узла.</li>
                <li>Привязка к зоне и циклы выращивания не снимаются автоматически.</li>
                <li>Выход возвращает узлы в <code>ACTIVE</code>.</li>
              </ul>
            </div>

            <div class="grid grid-cols-2 gap-2">
              <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40 px-3 py-2.5">
                <div class="text-[11px] uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
                  Можно ввести
                </div>
                <div class="mt-1 text-xl font-semibold tabular-nums text-[color:var(--text-primary)]">
                  {{ maintenanceEnterTargets.length }}
                </div>
              </div>
              <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40 px-3 py-2.5">
                <div class="text-[11px] uppercase tracking-[0.12em] text-[color:var(--text-muted)]">
                  В maintenance
                </div>
                <div
                  class="mt-1 text-xl font-semibold tabular-nums"
                  :class="maintenanceExitTargets.length > 0 ? 'text-[color:var(--accent-amber)]' : 'text-[color:var(--text-primary)]'"
                >
                  {{ maintenanceExitTargets.length }}
                </div>
              </div>
            </div>

            <div class="text-xs text-[color:var(--text-muted)]">
              Узлов теплицы:
              <span class="tabular-nums text-[color:var(--text-primary)]">{{ maintenanceCandidateNodes.length }}</span>
              · в обслуживании
              <span class="tabular-nums text-[color:var(--text-primary)]">{{ maintenanceExitTargets.length }}/{{ maintenanceCandidateNodes.length }}</span>
            </div>

            <div
              v-if="maintenanceCandidateNodes.length > 0"
              class="max-h-36 space-y-1 overflow-y-auto rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/25 p-2"
            >
              <div
                v-for="node in maintenanceCandidateNodes"
                :key="node.id"
                class="flex items-center justify-between gap-2 rounded-lg px-2 py-1 text-xs"
              >
                <span class="min-w-0 truncate text-[color:var(--text-primary)]">
                  {{ node.name || node.uid }}
                  <span class="text-[color:var(--text-muted)]">· {{ node.type || '—' }}</span>
                </span>
                <Badge :variant="node.lifecycle_state === 'MAINTENANCE' ? 'warning' : 'neutral'">
                  {{ node.lifecycle_state || '—' }}
                </Badge>
              </div>
            </div>
            <div
              v-else
              class="rounded-xl border border-dashed border-[color:var(--border-muted)] px-3 py-3 text-center text-xs text-[color:var(--text-muted)]"
            >
              Нет узлов теплицы для обслуживания.
            </div>

            <div class="mt-auto flex flex-col gap-2">
              <Button
                size="sm"
                variant="outline"
                class="w-full justify-center"
                :disabled="!canConfigureGreenhouse || maintenanceSubmitting"
                @click="openMaintenanceModal('MAINTENANCE')"
              >
                В обслуживание
              </Button>
              <Button
                size="sm"
                variant="ghost"
                class="w-full justify-center"
                :disabled="!canConfigureGreenhouse || maintenanceSubmitting"
                @click="openMaintenanceModal('ACTIVE')"
              >
                Завершить обслуживание
              </Button>
            </div>

            <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/35 px-3 py-2 text-xs text-[color:var(--text-muted)]">
              <span v-if="lastClimateSavedAt">Профиль климата: {{ formatTime(lastClimateSavedAt) }}</span>
              <span v-else>Профиль климата ещё не сохранён</span>
            </div>
          </aside>

          <div class="xl:col-span-8">
            <GreenhouseClimateConfiguration
              v-model:enabled="greenhouseClimateEnabled"
              :climate-form="climateForm"
              :bindings="greenhouseClimateBindings"
              :available-nodes="availableNodes"
              :can-configure="canOperateGreenhouse"
              :applying="climateSubmitting"
              :show-apply-button="true"
              apply-label="Сохранить климат теплицы"
              @apply="saveGreenhouseClimate"
            />
          </div>
        </div>
      </section>

      <div class="grid gap-5 xl:grid-cols-12">
        <section class="space-y-4 xl:col-span-8">
          <div class="ui-section-header !mb-0">
            <div>
              <h2 class="ui-section-title">
                Зоны теплицы
              </h2>
              <p class="ui-section-subtitle mt-0.5">
                Панель наблюдения и управления. Циклы и фазы — внутри зоны.
              </p>
            </div>
            <span class="rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2.5 py-1 text-xs tabular-nums text-[color:var(--text-muted)]">
              {{ zones.length }} {{ zonesWord }}
            </span>
          </div>

          <div
            v-if="zones.length > 0"
            class="grid gap-3 md:grid-cols-2"
          >
            <ZoneCard
              v-for="zone in zones"
              :key="zone.id"
              :zone="zone"
              :telemetry="zone.telemetry"
              :alerts-count="zone.alerts_count"
              :nodes-online="zone.nodes_online"
              :nodes-total="zone.nodes_total"
            />
          </div>
          <div
            v-else
            class="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[color:var(--border-muted)] px-6 py-12 text-center"
          >
            <p class="text-sm text-[color:var(--text-primary)]">
              В теплице пока нет зон
            </p>
            <p class="mt-1 max-w-sm text-xs text-[color:var(--text-muted)]">
              Создайте зону, чтобы подключить узлы и запустить цикл выращивания.
            </p>
            <Button
              v-if="canConfigureGreenhouse"
              class="mt-4"
              size="sm"
              @click="openZoneWizardGuarded()"
            >
              Новая зона
            </Button>
          </div>
        </section>

        <section class="surface-card space-y-3 rounded-2xl border border-[color:var(--border-muted)] p-4 xl:col-span-4">
          <div class="ui-section-header !mb-0">
            <div>
              <h2 class="ui-section-title">
                Узлы
              </h2>
              <p class="ui-section-subtitle mt-0.5">
                Состояние оборудования.
              </p>
            </div>
            <span class="text-xs tabular-nums text-[color:var(--text-muted)]">
              {{ nodes.length }} устройств
            </span>
          </div>

          <div
            v-if="nodes.length > 0"
            class="space-y-2"
          >
            <div
              v-for="node in nodes"
              :key="node.id"
              class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40 px-3 py-2.5 transition-colors hover:border-[color:var(--border-strong)]"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-[color:var(--text-primary)]">
                    {{ node.name || node.uid }}
                  </div>
                  <div class="mt-0.5 truncate text-xs text-[color:var(--text-muted)]">
                    {{ node.zone?.name || 'Без зоны' }}
                    <span v-if="node.type"> · {{ node.type }}</span>
                  </div>
                </div>
                <Badge :variant="node.status === 'online' ? 'success' : 'danger'">
                  {{ node.status }}
                </Badge>
              </div>
              <div class="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-[color:var(--text-muted)]">
                <span>Ф/В: {{ node.fw_version || '—' }}</span>
                <span>{{ node.lifecycle_state || 'Неизвестно' }}</span>
                <span>Отклик: {{ formatTime(node.last_seen_at) }}</span>
              </div>
            </div>
          </div>
          <div
            v-else
            class="rounded-xl border border-dashed border-[color:var(--border-muted)] px-4 py-8 text-center"
          >
            <p class="text-sm text-[color:var(--text-primary)]">
              Узлы ещё не подключены
            </p>
            <p class="mt-1 text-xs text-[color:var(--text-muted)]">
              После регистрации устройства появятся в этом списке.
            </p>
          </div>
        </section>
      </div>
    </div>

    <ZoneCreateWizard
      :show="showZoneWizard"
      :greenhouse-id="greenhouse.id"
      @close="closeZoneWizard"
      @created="onZoneCreated"
    />

    <ConfirmModal
      :open="maintenanceModal.open"
      :title="maintenanceModalTitle"
      :message="maintenanceModalMessage"
      :confirm-text="maintenanceModalConfirmText"
      :confirm-variant="maintenanceModalConfirmVariant"
      :loading="maintenanceSubmitting"
      :confirm-disabled="maintenanceTargets.length === 0"
      @close="closeMaintenanceModal"
      @confirm="confirmMaintenance"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <p>{{ maintenanceModalMessage }}</p>
        <ul class="max-h-40 space-y-1 overflow-y-auto rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/40 p-3 text-xs">
          <li
            v-for="node in maintenanceTargets"
            :key="node.id"
            class="flex justify-between gap-2"
          >
            <span class="truncate text-[color:var(--text-primary)]">{{ node.name || node.uid }}</span>
            <span>{{ node.type || '—' }} · {{ node.lifecycle_state || '—' }}</span>
          </li>
        </ul>
      </div>
    </ConfirmModal>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import GreenhouseClimateConfiguration from '@/Components/GreenhouseClimateConfiguration.vue'
import ZoneCreateWizard from '@/Components/ZoneCreateWizard.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { api } from '@/services/api'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import { useSimpleModal } from '@/composables/useModal'
import { useToast } from '@/composables/useToast'
import {
  asRecord,
  GREENHOUSE_LOGIC_PROFILE_NAMESPACE,
  payloadFromGreenhouseLogicDocument,
  resolveGreenhouseProfileEntry,
  toNodeIdArray,
  type GreenhouseClimateBindingsState,
} from '@/composables/greenhouseLogicProfileAuthority'
import { applyAutomationFromRecipe } from '@/composables/zoneAutomationFormLogic'
import {
  buildGreenhouseClimateSubsystemPayload,
  validateGreenhouseClimateForm,
} from '@/composables/zoneAutomationProfilePayload'
import { formatTime } from '@/utils/formatTime'
import type { ClimateFormState, LightingFormState, WaterFormState, ZoneClimateFormState } from '@/composables/zoneAutomationTypes'
import type { Zone } from '@/types'
import type { Device } from '@/types'
import type { ZoneTelemetry } from '@/types'

interface Props {
  greenhouse: {
    id: number
    name: string
    description?: string | null
    type?: string | null
    timezone?: string | null
  }
  zones: Array<Zone & {
    telemetry?: ZoneTelemetry | null
    alerts_count?: number
    nodes_online?: number
    nodes_offline?: number
    nodes_total?: number
  }>
  nodes: Array<Device & {
    last_seen_at?: string
  }>
  nodeSummary: {
    online: number
    offline: number
    total?: number
  }
  activeAlerts: number
}

interface PageProps {
  auth?: {
    user?: {
      role?: string
    }
  }
  [key: string]: unknown
}

type MaintenanceTargetState = 'MAINTENANCE' | 'ACTIVE'
type GreenhouseNodeOption = Device & { channels?: Array<{ channel?: string; type?: string }> }

const props = withDefaults(defineProps<Props>(), {
  zones: () => [],
  nodes: () => [],
  nodeSummary: () => ({
    online: 0,
    offline: 0,
    total: 0,
  }),
  activeAlerts: 0,
})

const page = usePage<PageProps>()
const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
const canConfigureGreenhouse = computed(() => role.value === 'agronomist' || role.value === 'admin')
const canOperateGreenhouse = computed(() => role.value === 'agronomist' || role.value === 'admin' || role.value === 'operator')

const { showToast } = useToast()
const automationConfig = useAutomationConfig(showToast)
const { isOpen: showZoneWizard, open: openZoneWizard, close: closeZoneWizard } = useSimpleModal()

const climateSubmitting = ref(false)
const lastClimateSavedAt = ref<string | null>(null)
const greenhouseClimateEnabled = ref(false)
const availableNodes = ref<GreenhouseNodeOption[]>([])
const managedGreenhouseNodes = ref<GreenhouseNodeOption[]>([])
const greenhouseClimateBindings = reactive<GreenhouseClimateBindingsState>({
  climate_sensors: [],
  weather_station_sensors: [],
  vent_actuators: [],
  fan_actuators: [],
})

const climateForm = reactive<ClimateFormState>({
  enabled: true,
  dayTemp: 23,
  nightTemp: 20,
  dayHumidity: 62,
  nightHumidity: 70,
  intervalMinutes: 5,
  dayStart: '07:00',
  nightStart: '19:00',
  ventMinPercent: 15,
  ventMaxPercent: 85,
  useExternalTelemetry: true,
  outsideTempMin: 4,
  outsideTempMax: 34,
  outsideHumidityMax: 90,
  manualOverrideEnabled: true,
  overrideMinutes: 30,
  maxVentStepPct: 25,
})

const maintenanceSubmitting = ref(false)
const maintenanceModal = reactive({
  open: false,
  targetState: 'MAINTENANCE' as MaintenanceTargetState,
})

const waterForm = reactive<WaterFormState>({
  systemType: 'drip',
  tanksCount: 2,
  cleanTankFillL: 300,
  nutrientTankTargetL: 280,
  irrigationBatchL: 20,
  intervalMinutes: 30,
  durationSeconds: 120,
  fillTemperatureC: 20,
  fillWindowStart: '05:00',
  fillWindowEnd: '07:00',
  targetPh: 5.8,
  targetEc: 1.6,
  phPct: 5,
  ecPct: 10,
  valveSwitching: true,
  correctionDuringIrrigation: true,
  correctionMaxEcCorrectionAttempts: 8,
  correctionMaxPhCorrectionAttempts: 8,
  correctionPrepareRecirculationMaxAttempts: 6,
  correctionPrepareRecirculationMaxCorrectionAttempts: 24,
  correctionStabilizationSec: 30,
  enableDrainControl: false,
  drainTargetPercent: 20,
  diagnosticsEnabled: true,
  diagnosticsIntervalMinutes: 15,
  diagnosticsWorkflow: 'startup',
  cleanTankFullThreshold: 0.95,
  refillDurationSeconds: 30,
  refillTimeoutSeconds: 600,
  mainPumpFlowLpm: 10,
  cleanWaterFlowLpm: 15,
  workingTankL: 50,
  refillRequiredNodeTypes: 'irrig,climate,light',
  refillPreferredChannel: 'fill_valve',
  startupCleanFillTimeoutSeconds: 1800,
  startupSolutionFillTimeoutSeconds: 1800,
  startupPrepareRecirculationTimeoutSeconds: 900,
  startupCleanFillRetryCycles: 2,
  solutionChangeEnabled: false,
  solutionChangeIntervalMinutes: 180,
  solutionChangeDurationSeconds: 120,
  manualIrrigationSeconds: 90,
})

const lightingForm = reactive<LightingFormState>({
  enabled: false,
  luxDay: 18000,
  luxNight: 0,
  hoursOn: 16,
  intervalMinutes: 30,
  scheduleStart: '06:00',
  scheduleEnd: '22:00',
  manualIntensity: 75,
  manualDurationHours: 4,
})

const zoneClimateForm = reactive<ZoneClimateFormState>({ enabled: false })

function buildGreenhouseClimateSubsystem(): Record<string, unknown> {
  return buildGreenhouseClimateSubsystemPayload(climateForm, greenhouseClimateEnabled.value)
}

async function loadAvailableNodes(): Promise<void> {
  try {
    const response = await api.nodes.list({
      greenhouse_id: props.greenhouse.id,
      include_unassigned: true,
    })
    availableNodes.value = unwrapNodesList(response)
  } catch {
    showToast('Не удалось загрузить список нод теплицы.', 'warning', TOAST_TIMEOUT.NORMAL)
  }
}

async function loadManagedGreenhouseNodes(): Promise<void> {
  try {
    const response = await api.nodes.list({
      greenhouse_id: props.greenhouse.id,
    })
    managedGreenhouseNodes.value = unwrapNodesList(response)
  } catch {
    showToast('Не удалось загрузить управляемые greenhouse climate ноды.', 'warning', TOAST_TIMEOUT.NORMAL)
  }
}

function unwrapNodesList(response: unknown): GreenhouseNodeOption[] {
  if (Array.isArray(response)) return response as GreenhouseNodeOption[]
  const inner = (response as { data?: unknown })?.data
  return Array.isArray(inner) ? (inner as GreenhouseNodeOption[]) : []
}

async function loadGreenhouseClimate(): Promise<void> {
  try {
    const document = await automationConfig.getDocument('greenhouse', props.greenhouse.id, GREENHOUSE_LOGIC_PROFILE_NAMESPACE)
    const payload = payloadFromGreenhouseLogicDocument(document)
    const entry = resolveGreenhouseProfileEntry(payload ?? null)
    const bindings = asRecord(payload?.bindings ?? null)

    greenhouseClimateBindings.climate_sensors = toNodeIdArray(bindings?.climate_sensors)
    greenhouseClimateBindings.weather_station_sensors = toNodeIdArray(bindings?.weather_station_sensors)
    greenhouseClimateBindings.vent_actuators = toNodeIdArray(bindings?.vent_actuators)
    greenhouseClimateBindings.fan_actuators = toNodeIdArray(bindings?.fan_actuators)

    if (!entry?.subsystems) {
      return
    }

    const climateSubsystem = asRecord(entry.subsystems.climate ?? null)
    greenhouseClimateEnabled.value = Boolean(climateSubsystem?.enabled ?? false)
    lastClimateSavedAt.value = typeof entry.updated_at === 'string' ? entry.updated_at : null

    applyAutomationFromRecipe(
      {
        extensions: {
          subsystems: {
            climate: climateSubsystem ?? {},
          },
        },
      },
      {
        climateForm,
        waterForm,
        lightingForm,
        zoneClimateForm,
      }
    )
  } catch {
    showToast('Не удалось загрузить климат теплицы.', 'warning', TOAST_TIMEOUT.NORMAL)
  }
}

async function saveGreenhouseClimate(): Promise<void> {
  if (!canOperateGreenhouse.value || climateSubmitting.value) {
    return
  }

  climateSubmitting.value = true
  try {
    const climateErr = validateGreenhouseClimateForm(climateForm)
    if (climateErr) {
      showToast(climateErr, 'warning', TOAST_TIMEOUT.NORMAL)
      return
    }

    const bindingsPayload = {
      greenhouse_id: props.greenhouse.id,
      enabled: greenhouseClimateEnabled.value,
      climate_sensors: [...greenhouseClimateBindings.climate_sensors],
      weather_station_sensors: [...greenhouseClimateBindings.weather_station_sensors],
      vent_actuators: [...greenhouseClimateBindings.vent_actuators],
      fan_actuators: [...greenhouseClimateBindings.fan_actuators],
    }

    if (greenhouseClimateEnabled.value) {
      await api.setupWizard.validateGreenhouseClimateDevices(bindingsPayload)
    }

    await api.setupWizard.applyGreenhouseClimateBindings(bindingsPayload)
    const currentDocument = await automationConfig.getDocument('greenhouse', props.greenhouse.id, GREENHOUSE_LOGIC_PROFILE_NAMESPACE)
    const currentPayload = payloadFromGreenhouseLogicDocument(currentDocument)
    const response = await automationConfig.updateDocument('greenhouse', props.greenhouse.id, GREENHOUSE_LOGIC_PROFILE_NAMESPACE, {
      active_mode: 'setup',
      profiles: {
        ...(currentPayload?.profiles ?? {}),
        setup: {
          mode: 'setup',
          is_active: true,
          subsystems: buildGreenhouseClimateSubsystem(),
          updated_at: new Date().toISOString(),
        },
      },
    })

    const payload = payloadFromGreenhouseLogicDocument(response)
    const entry = resolveGreenhouseProfileEntry(payload ?? null)
    lastClimateSavedAt.value = typeof entry?.updated_at === 'string' ? entry.updated_at : new Date().toISOString()
    showToast('Климат теплицы сохранён.', 'success', TOAST_TIMEOUT.NORMAL)
    await loadGreenhouseClimate()
  } catch {
    showToast('Не удалось сохранить климат теплицы.', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    climateSubmitting.value = false
  }
}

function openZoneWizardGuarded(): void {
  if (!canConfigureGreenhouse.value) {
    showToast('Создание зон доступно только агроному.', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  openZoneWizard()
}

function onZoneCreated(_zone: Zone): void {
  router.reload({ only: ['zones'] })
}

const nodes = computed(() => props.nodes || [])
const zones = computed(() => props.zones || [])
const nodeSummary = computed(() => props.nodeSummary || { online: 0, offline: 0, total: 0 })
const activeAlerts = computed(() => props.activeAlerts ?? 0)

const zonesWord = computed(() => {
  const count = zones.value.length % 100
  const last = count % 10
  if (count > 10 && count < 20) return 'зон'
  if (last === 1) return 'зона'
  if (last >= 2 && last <= 4) return 'зоны'
  return 'зон'
})

const maintenanceCandidateNodes = computed(() => {
  const byId = new Map<number, GreenhouseNodeOption>()
  for (const node of nodes.value) {
    byId.set(node.id, node as GreenhouseNodeOption)
  }
  for (const node of managedGreenhouseNodes.value) {
    byId.set(node.id, node)
  }
  return Array.from(byId.values())
})

/** FSM: ASSIGNED_TO_ZONE | ACTIVE | DEGRADED → MAINTENANCE */
const maintenanceEnterTargets = computed(() => {
  const allowedStates = new Set(['ASSIGNED_TO_ZONE', 'ACTIVE', 'DEGRADED'])
  return maintenanceCandidateNodes.value.filter((node) => {
    return Boolean(node.lifecycle_state && allowedStates.has(node.lifecycle_state))
  })
})

const maintenanceExitTargets = computed(() => {
  return maintenanceCandidateNodes.value.filter((node) => node.lifecycle_state === 'MAINTENANCE')
})

const maintenanceTargets = computed(() => {
  return maintenanceModal.targetState === 'MAINTENANCE'
    ? maintenanceEnterTargets.value
    : maintenanceExitTargets.value
})

const maintenanceModalTitle = computed(() => {
  return maintenanceModal.targetState === 'MAINTENANCE'
    ? 'Перевести узлы в обслуживание'
    : 'Завершить обслуживание'
})

const maintenanceModalMessage = computed(() => {
  const total = maintenanceTargets.value.length
  if (maintenanceModal.targetState === 'MAINTENANCE') {
    return `Перевести в MAINTENANCE ${total} узлов теплицы? Узлы станут offline, рабочая телеметрия не принимается; привязка к зоне сохранится.`
  }

  return `Завершить обслуживание для ${total} узлов и вернуть их в ACTIVE?`
})

const maintenanceModalConfirmText = computed(() => maintenanceModal.targetState === 'MAINTENANCE' ? 'В обслуживание' : 'Завершить')
const maintenanceModalConfirmVariant = computed(() => maintenanceModal.targetState === 'MAINTENANCE' ? 'warning' : 'primary')

function openMaintenanceModal(targetState: MaintenanceTargetState): void {
  if (!canConfigureGreenhouse.value) {
    showToast('Режим обслуживания доступен агроному и админу.', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  maintenanceModal.targetState = targetState

  if (maintenanceTargets.value.length === 0) {
    const hint = targetState === 'MAINTENANCE'
      ? 'Нет узлов в состояниях ASSIGNED_TO_ZONE / ACTIVE / DEGRADED.'
      : 'Нет узлов в состоянии MAINTENANCE.'
    showToast(hint, 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  maintenanceModal.open = true
}

function closeMaintenanceModal(): void {
  maintenanceModal.open = false
}

async function confirmMaintenance(): Promise<void> {
  if (maintenanceSubmitting.value) {
    return
  }

  const targetState = maintenanceModal.targetState
  const targets = maintenanceTargets.value

  if (targets.length === 0) {
    maintenanceModal.open = false
    return
  }

  maintenanceSubmitting.value = true
  try {
    const results = await Promise.allSettled(
      targets.map((node) => api.nodes.lifecycleTransition(node.id, {
        target_state: targetState,
        reason: `Greenhouse ${props.greenhouse.name}: ${targetState === 'MAINTENANCE' ? 'maintenance' : 'resume'}`,
      })),
    )
    const successCount = results.filter((result) => result.status === 'fulfilled').length
    const failedCount = results.length - successCount
    const actionLabel = targetState === 'MAINTENANCE' ? 'в обслуживание' : 'в активный режим'

    if (successCount && failedCount === 0) {
      showToast(`Узлы переведены ${actionLabel}: ${successCount}.`, 'success', TOAST_TIMEOUT.NORMAL)
    } else if (successCount && failedCount > 0) {
      showToast(`Часть узлов переведена ${actionLabel}: ${successCount}, ошибок: ${failedCount}.`, 'warning', TOAST_TIMEOUT.LONG)
    } else {
      showToast(`Не удалось перевести узлы ${actionLabel}.`, 'error', TOAST_TIMEOUT.LONG)
    }
  } finally {
    maintenanceSubmitting.value = false
    maintenanceModal.open = false
    router.reload({ only: ['nodes', 'nodeSummary'] })
    await Promise.all([
      loadAvailableNodes(),
      loadManagedGreenhouseNodes(),
    ])
  }
}

onMounted(async () => {
  await Promise.all([
    loadAvailableNodes(),
    loadManagedGreenhouseNodes(),
    loadGreenhouseClimate(),
  ])
})
</script>
