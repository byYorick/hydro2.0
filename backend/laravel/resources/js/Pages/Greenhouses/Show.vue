<template>
  <AppLayout>
    <div class="space-y-6">
      <header class="ui-hero p-5 space-y-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p class="text-xs uppercase tracking-[0.4em] text-[color:var(--text-dim)]">
              {{ greenhouse.type || 'Теплица' }}
            </p>
            <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">
              {{ greenhouse.name }}
            </h1>
            <p class="mt-1 max-w-2xl text-sm text-[color:var(--text-muted)]">
              {{ greenhouse.description || 'Информационная панель по текущему состоянию теплицы и прикреплённым зонам.' }}
            </p>
          </div>
          <div class="flex items-center gap-3">
            <Link href="/zones">
              <Button
                size="sm"
                variant="outline"
              >
                Все зоны
              </Button>
            </Link>
          </div>
        </div>
        <div class="grid gap-3 xs:grid-cols-2 md:grid-cols-4">
          <MetricCard
            label="Зоны"
            :value="zones.length"
            color="var(--accent-cyan)"
            status="success"
            subtitle="Общее количество зон"
          />
          <MetricCard
            label="Активные циклы"
            :value="activeCyclesCount"
            color="var(--accent-green)"
            status="info"
            subtitle="С привязанными рецептами"
          />
          <MetricCard
            label="Узлы онлайн"
            :value="nodeSummary.online"
            color="var(--accent-cyan)"
            status="success"
            subtitle="Работает"
          />
          <MetricCard
            label="Оповещения"
            :value="activeAlerts"
            color="var(--accent-red)"
            status="danger"
            subtitle="Активных"
          />
        </div>
      </header>

      <section class="space-y-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 class="text-base font-semibold">
              Управление теплицей
            </h2>
            <p class="text-xs text-[color:var(--text-dim)]">
              Общий климат теплицы и обслуживание оборудования.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              :disabled="!canConfigureGreenhouse || maintenanceEnterTargets.length === 0 || maintenanceSubmitting"
              @click="openMaintenanceModal('MAINTENANCE')"
            >
              В обслуживание
            </Button>
            <Button
              size="sm"
              variant="ghost"
              :disabled="!canConfigureGreenhouse || maintenanceExitTargets.length === 0 || maintenanceSubmitting"
              @click="openMaintenanceModal('ACTIVE')"
            >
              Завершить обслуживание
            </Button>
          </div>
        </div>

        <GreenhouseClimateConfiguration
          :enabled="greenhouseClimateEnabled"
          :climate-form="climateForm"
          :bindings="greenhouseClimateBindings"
          :available-nodes="availableNodes"
          :can-configure="canOperateGreenhouse"
          :applying="climateSubmitting"
          :show-apply-button="true"
          apply-label="Сохранить климат теплицы"
          @update:enabled="greenhouseClimateEnabled = $event"
          @apply="saveGreenhouseClimate"
        />

        <div class="text-xs text-[color:var(--text-dim)]">
          <span v-if="lastClimateSavedAt">Профиль обновлён: {{ formatTime(lastClimateSavedAt) }}</span>
          <span v-else>Профиль климата ещё не сохранён</span>
          <span class="ml-3">Runtime dispatcher климата теплицы пока в разработке, но profile и bindings уже сохраняются.</span>
        </div>

        <div class="text-xs text-[color:var(--text-dim)]">
          В обслуживании сейчас {{ maintenanceExitTargets.length }} / {{ climateNodes.length }} climate/weather нод.
        </div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">
              Зоны теплицы
            </h2>
            <p class="text-xs text-[color:var(--text-dim)]">
              Панель наблюдения и управления.
            </p>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-[color:var(--text-dim)]">{{ zones.length }} зон</span>
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
        <div class="grid gap-3 md:grid-cols-2">
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
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">
              Циклы
            </h2>
            <p class="text-xs text-[color:var(--text-dim)]">
              Отслеживание фаз и прогресса рецептов.
            </p>
          </div>
          <span class="text-xs text-[color:var(--text-dim)]">{{ cycles.length }} активных</span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <Card
            v-for="cycle in cycles"
            :key="cycle.zone_id"
            class="space-y-3"
          >
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold">
                  {{ cycle.zone?.name }}
                </div>
                <div class="text-xs text-[color:var(--text-muted)]">
                  {{ cycle.recipe?.name }}
                </div>
              </div>
              <Badge :variant="cycle.progress >= 85 ? 'success' : cycle.progress >= 45 ? 'warning' : 'info'">
                {{ cycle.statusLabel }}
              </Badge>
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Фаза {{ cycle.phaseIndex }} · Прогресс {{ cycle.progress.toFixed(1) }}%
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-[color:var(--border-muted)]">
              <div
                class="h-full rounded-full bg-[linear-gradient(90deg,var(--accent-green),var(--accent-cyan))] transition-all"
                :style="{ width: `${Math.min(Math.max(cycle.progress, 0), 100)}%` }"
              ></div>
            </div>
          </Card>
        </div>
        <div
          v-if="cycles.length === 0"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Нет активных циклов
        </div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">
              Узлы
            </h2>
            <p class="text-xs text-[color:var(--text-dim)]">
              Состояние оборудования.
            </p>
          </div>
          <span class="text-xs text-[color:var(--text-dim)]">{{ nodes.length }} устройств</span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <Card
            v-for="node in nodes"
            :key="node.id"
            class="space-y-2"
          >
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold">
                  {{ node.name || node.uid }}
                </div>
                <div class="text-xs text-[color:var(--text-muted)]">
                  {{ node.zone?.name }}
                </div>
              </div>
              <Badge :variant="node.status === 'online' ? 'success' : 'danger'">
                {{ node.status }}
              </Badge>
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Ф/В: {{ node.fw_version || '—' }}
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Жизненный цикл: {{ node.lifecycle_state || 'Неизвестно' }}
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">
              Последний отклик: {{ formatTime(node.last_seen_at) }}
            </div>
          </Card>
        </div>
      </section>
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
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import GreenhouseClimateConfiguration from '@/Components/GreenhouseClimateConfiguration.vue'
import MetricCard from '@/Components/MetricCard.vue'
import ZoneCreateWizard from '@/Components/ZoneCreateWizard.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { useApi } from '@/composables/useApi'
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
import { applyAutomationFromRecipe, buildGrowthCycleConfigPayload } from '@/composables/zoneAutomationFormLogic'
import { extractCollection } from '@/composables/setupWizardCollection'
import { formatTime } from '@/utils/formatTime'
import { calculateProgressFromDuration } from '@/utils/growCycleProgress'
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
const { api } = useApi(showToast)
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
  prepareToleranceEcPct: 10,
  prepareTolerancePhPct: 5,
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
  refillRequiredNodeTypes: 'irrig,climate,light',
  refillPreferredChannel: 'fill_valve',
  startupCleanFillTimeoutSeconds: 1800,
  startupSolutionFillTimeoutSeconds: 1800,
  startupPrepareRecirculationTimeoutSeconds: 900,
  startupCleanFillRetryCycles: 2,
  irrigationRecoveryMaxContinueAttempts: 3,
  irrigationRecoveryTimeoutSeconds: 600,
  solutionChangeEnabled: false,
  solutionChangeIntervalMinutes: 180,
  solutionChangeDurationSeconds: 120,
  manualIrrigationSeconds: 90,
  twoTankCleanFillStartSteps: 1,
  twoTankCleanFillStopSteps: 1,
  twoTankSolutionFillStartSteps: 1,
  twoTankSolutionFillStopSteps: 1,
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
  const payload = buildGrowthCycleConfigPayload(
    {
      climateForm,
      waterForm,
      lightingForm,
      zoneClimateForm,
    },
    {
      includeClimateSubsystem: true,
    }
  )
  const subsystems = asRecord(payload.subsystems ?? null)
  const climate = asRecord(subsystems?.climate ?? null)

  return {
    climate: {
      enabled: greenhouseClimateEnabled.value,
      execution: asRecord(climate?.execution ?? null) ?? {},
    },
  }
}

async function loadAvailableNodes(): Promise<void> {
  try {
    const response = await api.get('/nodes', {
      params: {
        greenhouse_id: props.greenhouse.id,
        include_unassigned: true,
      },
    })
    availableNodes.value = extractCollection<GreenhouseNodeOption>(response.data)
  } catch {
    showToast('Не удалось загрузить список нод теплицы.', 'warning', TOAST_TIMEOUT.NORMAL)
  }
}

async function loadManagedGreenhouseNodes(): Promise<void> {
  try {
    const response = await api.get('/nodes', {
      params: {
        greenhouse_id: props.greenhouse.id,
      },
    })
    managedGreenhouseNodes.value = extractCollection<GreenhouseNodeOption>(response.data)
  } catch {
    showToast('Не удалось загрузить управляемые greenhouse climate ноды.', 'warning', TOAST_TIMEOUT.NORMAL)
  }
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
    const bindingsPayload = {
      greenhouse_id: props.greenhouse.id,
      enabled: greenhouseClimateEnabled.value,
      climate_sensors: [...greenhouseClimateBindings.climate_sensors],
      weather_station_sensors: [...greenhouseClimateBindings.weather_station_sensors],
      vent_actuators: [...greenhouseClimateBindings.vent_actuators],
      fan_actuators: [...greenhouseClimateBindings.fan_actuators],
    }

    if (greenhouseClimateEnabled.value) {
      await api.post('/setup-wizard/validate-greenhouse-climate-devices', bindingsPayload)
    }

    await api.post('/setup-wizard/apply-greenhouse-climate-bindings', bindingsPayload)
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

const cycles = computed(() => {
  if (!props.zones || !Array.isArray(props.zones)) {
    return []
  }

  return props.zones
    .filter((zone) => zone.activeGrowCycle || (zone.cycles && zone.cycles.length > 0))
    .map((zone) => {
      const activeGrowCycle = (zone as any).activeGrowCycle
      const legacyCycle = zone.cycles?.find(cycle => cycle.status === 'RUNNING')
      const cycle = activeGrowCycle || legacyCycle

      if (cycle) {
        const currentPhase = activeGrowCycle?.currentPhase
        const phaseIndex = activeGrowCycle
          ? (currentPhase?.phase_index ?? 0) + 1
          : (legacyCycle?.current_phase_index ?? 0) + 1

        let progress = 0
        const phaseDurationHours = activeGrowCycle
          ? (currentPhase?.duration_hours ?? ((currentPhase?.duration_days || 0) * 24))
          : (legacyCycle?.recipe?.phases?.[legacyCycle?.current_phase_index ?? 0]?.duration_hours ?? 0)

        const phaseStartCandidate = activeGrowCycle?.phase_started_at || activeGrowCycle?.started_at || legacyCycle?.started_at

        if (phaseDurationHours && phaseStartCandidate) {
          progress = calculateProgressFromDuration(phaseStartCandidate, phaseDurationHours, null) ?? 0
        }

        return {
          zone_id: zone.id,
          zone,
          recipe: activeGrowCycle?.recipeRevision?.recipe ?? legacyCycle?.recipe ?? null,
          phaseIndex,
          statusLabel: progress >= 85 ? 'Старт' : progress >= 45 ? 'В процессе' : 'Начало',
          progress,
        }
      }

      return {
        zone_id: zone.id,
        zone,
        recipe: null,
        phaseIndex: 0,
        statusLabel: 'Нет данных',
        progress: 0,
      }
    })
})

const activeCyclesCount = computed(() => cycles.value.length)
const nodes = computed(() => props.nodes || [])
const zones = computed(() => props.zones || [])
const nodeSummary = computed(() => props.nodeSummary || { online: 0, offline: 0, total: 0 })
const activeAlerts = computed(() => props.activeAlerts ?? 0)

const climateNodes = computed(() => {
  return managedGreenhouseNodes.value.filter((node) => {
    const type = String(node.type ?? '').toLowerCase()
    return type === 'climate' || type === 'weather'
  })
})

const maintenanceEnterTargets = computed(() => {
  const allowedStates = new Set(['ASSIGNED_TO_ZONE', 'ACTIVE', 'DEGRADED', 'REGISTERED_BACKEND'])
  return climateNodes.value.filter((node) => {
    if (!node.lifecycle_state || node.lifecycle_state === 'MAINTENANCE') {
      return false
    }
    return allowedStates.has(node.lifecycle_state)
  })
})

const maintenanceExitTargets = computed(() => climateNodes.value.filter((node) => node.lifecycle_state === 'MAINTENANCE'))

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
    return `Перевести в обслуживание ${total} climate/weather нод теплицы?`
  }

  return `Завершить обслуживание для ${total} climate/weather нод и вернуть их в активный режим?`
})

const maintenanceModalConfirmText = computed(() => maintenanceModal.targetState === 'MAINTENANCE' ? 'В обслуживание' : 'Завершить')
const maintenanceModalConfirmVariant = computed(() => maintenanceModal.targetState === 'MAINTENANCE' ? 'warning' : 'primary')

function openMaintenanceModal(targetState: MaintenanceTargetState): void {
  if (!canConfigureGreenhouse.value) {
    showToast('Режим обслуживания доступен только агроному.', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  maintenanceModal.targetState = targetState

  if (maintenanceTargets.value.length === 0) {
    showToast('Нет узлов, доступных для выбранного действия.', 'warning', TOAST_TIMEOUT.NORMAL)
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
      targets.map((node) => api.post(`/nodes/${node.id}/lifecycle/transition`, {
        target_state: targetState,
        reason: `Greenhouse ${props.greenhouse.name}: ${targetState === 'MAINTENANCE' ? 'maintenance' : 'resume'}`,
      }))
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
