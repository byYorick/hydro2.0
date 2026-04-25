<template>
  <div class="flex flex-col gap-3">
    <CalibrationReadinessBar
      :contracts="contracts"
      :summary="summary"
      @open-blockers="blockersOpen = true"
      @open-pump-wizard="openPumpWizardFromReadiness"
      @open-contract="onContractClick"
    />

    <div class="grid gap-3 lg:[grid-template-columns:240px_1fr] items-start">
      <CalibrationSidebar
        :current="currentSub"
        :nav="navMap"
        @select="(id) => (currentSub = id)"
      />

      <section
        class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] p-3.5 flex flex-col gap-3 min-h-[260px]"
      >
        <CalibrationBreadcrumb
          :sub="currentSub"
          :title="currentSubMeta.title"
          :description="currentSubMeta.desc"
        />

        <PumpsSubview
          v-if="currentSub === 'pumps'"
          :zone-id="zoneId"
          :pumps="pumps"
          @calibrate="onPumpCalibrateFromRow"
          @open-pump-wizard="openPumpWizardGeneric"
          @export-csv="onExportCsv"
        />

        <SensorsSubview
          v-else-if="currentSub === 'sensors'"
          :zone-id="zoneId"
          :settings="sensorCalibrationSettings"
        />

        <ProcessSubview
          v-else-if="currentSub === 'process'"
          :zone-id="zoneId"
          @saved="$emit('updated')"
        />

        <CorrectionSubview
          v-else-if="currentSub === 'correction'"
          :zone-id="zoneId"
          @saved="$emit('updated')"
        />

        <PidSubview
          v-else-if="currentSub === 'pid'"
          :zone-id="zoneId"
          :phase-targets="phaseTargets"
          :pid-chart-params="pidChartParams"
          @saved="$emit('updated')"
        />
      </section>
    </div>

    <CalibrationBlockersDrawer
      :open="blockersOpen"
      :blockers="blockers"
      @close="blockersOpen = false"
      @navigate="onBlockerNavigate"
    />

    <PumpCalibrationDrawer
      :show="pumpDrawerOpen"
      :zone-id="zoneId"
      :devices="zoneDevices"
      :pumps="pumps"
      :loading-run="pumpActions.loadingRun.value"
      :loading-save="pumpActions.loadingSave.value"
      :run-success-seq="pumpActions.runSeq.value"
      :save-success-seq="pumpActions.saveSeq.value"
      :last-run-token="pumpActions.lastRunToken.value"
      :initial-component="forcedComponent"
      :initial-node-channel-id="forcedNodeChannelId"
      @close="pumpDrawerOpen = false"
      @start="onPumpStart"
      @save="onPumpSave"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import CalibrationReadinessBar from './CalibrationReadinessBar.vue'
import CalibrationSidebar, {
  type CalibrationSubKey,
  type CalibrationNavMap,
  type CalibrationNavInfo,
} from './CalibrationSidebar.vue'
import CalibrationBreadcrumb from './CalibrationBreadcrumb.vue'
import { type PumpRow } from './CalibrationPumpsSubpage.vue'
import CalibrationBlockersDrawer from './CalibrationBlockersDrawer.vue'
import PumpCalibrationDrawer from './PumpCalibrationDrawer.vue'
import SensorsSubview from './Subviews/SensorsSubview.vue'
import PumpsSubview from './Subviews/PumpsSubview.vue'
import ProcessSubview from './Subviews/ProcessSubview.vue'
import CorrectionSubview from './Subviews/CorrectionSubview.vue'
import PidSubview from './Subviews/PidSubview.vue'
import {
  useCalibrationContracts,
  type CalibrationContract,
} from '@/composables/useCalibrationContracts'
import { useSensorCalibrationSettings } from '@/composables/useSensorCalibrationSettings'
import { usePumpCalibrationActions } from '@/composables/usePumpCalibrationActions'
import { useToast } from '@/composables/useToast'
import { api } from '@/services/api'
import type { Device } from '@/types'
import type { PumpCalibration } from '@/types/PidConfig'
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import type {
  PumpCalibrationComponent,
  PumpCalibrationRunPayload,
  PumpCalibrationSavePayload,
} from '@/types/Calibration'

const props = withDefaults(
  defineProps<{
    zoneId: number
    phaseTargets?: RecipePhasePidTargets | null
  }>(),
  { phaseTargets: null },
)
const emit = defineEmits<{ (e: 'updated'): void }>()

const { showToast } = useToast()
const sensorCalibrationSettings = useSensorCalibrationSettings()

const currentSub = ref<CalibrationSubKey>('pumps')
const blockersOpen = ref(false)
const pumpDrawerOpen = ref(false)
const forcedComponent = ref<PumpCalibrationComponent | null>(null)
const forcedNodeChannelId = ref<number | null>(null)

const pumps = ref<PumpCalibration[]>([])
const zoneDevices = ref<Device[]>([])
const processDocs = ref<Record<string, unknown>>({})
const correctionDoc = ref<Record<string, unknown> | null>(null)
const pidDoc = ref<Record<string, unknown> | null>(null)

const { contracts, summary, blockers } = useCalibrationContracts({
  pumps: computed(() => pumps.value),
  devices: computed(() => zoneDevices.value),
  processDocs: computed(() => processDocs.value),
  correctionDoc: computed(() => correctionDoc.value),
  pidDoc: computed(() => pidDoc.value),
})

const pumpActions = usePumpCalibrationActions({
  getZoneId: () => props.zoneId,
  showToast,
  onSaveSuccess: async () => {
    await loadPumpCalibrations()
    emit('updated')
  },
  onRunSuccess: async () => {
    await loadPumpCalibrations()
  },
})

// ── Sidebar nav ───────────────────────────────────────────────────
const navMap = computed<CalibrationNavMap>(() => {
  const pumpContracts = contracts.value.filter((c) => c.subsystem === 'pump')
  const pumpDone = pumpContracts.filter((c) => c.status === 'passed').length
  const sensorContract = contracts.value.find((c) => c.subsystem === 'sensor')
  const processContract = contracts.value.find((c) => c.subsystem === 'process')
  const correctionContract = contracts.value.find((c) => c.subsystem === 'correction')
  const pidContract = contracts.value.find((c) => c.subsystem === 'pid')
  const pumpsBlocked = pumpContracts.some((c) => c.status === 'blocker')

  const fromContract = (contract?: CalibrationContract): CalibrationNavInfo['state'] => {
    if (!contract) return 'optional'
    if (contract.status === 'passed') return 'passed'
    if (contract.status === 'blocker') return 'blocker'
    if (contract.status === 'optional') return 'optional'
    return 'active'
  }

  return {
    sensors: {
      state: fromContract(sensorContract),
      count: sensorContract?.status === 'passed' ? '2/2' : '0/2',
    },
    pumps: {
      state: pumpsBlocked
        ? 'blocker'
        : pumpDone === pumpContracts.length && pumpContracts.length > 0
          ? 'passed'
          : 'active',
      count: `${pumpDone}/${pumpContracts.length}`,
    },
    process: {
      state: pumpsBlocked ? 'waiting' : fromContract(processContract),
      count: processContract?.status === 'passed' ? '4/4' : '0/4',
      waitingLabel: pumpsBlocked ? 'ждёт насосы' : undefined,
    },
    correction: { state: fromContract(correctionContract), count: 'опц.' },
    pid: { state: fromContract(pidContract), count: 'опц.' },
  }
})

const SUB_META: Record<CalibrationSubKey, { title: string; desc: string }> = {
  sensors: {
    title: 'Калибровка сенсоров',
    desc: 'Двухточечная калибровка pH/EC. AE3 хранит offset/slope и применяет их к raw-значению из mqtt-bridge.',
  },
  pumps: {
    title: 'Дозирующие насосы',
    desc: 'Калибровка ml/sec для всех ролей дозации. Запуск через PumpCalibrationDrawer + ручное измерение мензуркой.',
  },
  process: {
    title: 'Калибровка процесса',
    desc: 'Окно наблюдения и коэффициенты отклика для 4 фаз: solution_fill / tank_recirc / irrigation / generic.',
  },
  correction: {
    title: 'Конфигурация коррекции',
    desc: 'Authority-редактор: recipe / zone / manual. Допуски, шаги, кулдауны, dry_run.',
  },
  pid: {
    title: 'PID и autotune',
    desc: 'Доводка контура коррекции — открывайте только после базовой калибровки.',
  },
}

const currentSubMeta = computed(() => SUB_META[currentSub.value])

// ── PID chart params from pidDoc ──────────────────────────────────
const pidChartParams = computed(() => {
  const d = pidDoc.value as Record<string, unknown> | null
  if (!d) return null
  const target = Number(d.target ?? NaN)
  const dead = Number(d.dead_zone ?? NaN)
  const close = Number(d.close_zone ?? NaN)
  const far = Number(d.far_zone ?? NaN)
  if ([target, dead, close, far].some((v) => Number.isNaN(v))) return null
  return { target, dead, close, far }
})

// ── Data loaders ─────────────────────────────────────────────────
async function loadPumpCalibrations(): Promise<void> {
  try {
    const resp = await api.zones.getPumpCalibrations<{
      pumps?: PumpCalibration[]
    } | PumpCalibration[]>(props.zoneId)
    let list: PumpCalibration[] = []
    if (Array.isArray(resp)) list = resp as PumpCalibration[]
    else if (Array.isArray((resp as { pumps?: PumpCalibration[] })?.pumps))
      list = (resp as { pumps: PumpCalibration[] }).pumps
    pumps.value = list
  } catch {
    pumps.value = []
  }
}

async function loadZoneDevices(): Promise<void> {
  try {
    const resp = await api.nodes.list({
      zone_id: props.zoneId,
      include_unassigned: true,
      per_page: 100,
    })
    const list = Array.isArray(resp)
      ? resp
      : Array.isArray((resp as { data?: unknown[] })?.data)
        ? ((resp as { data: unknown[] }).data as unknown[])
        : []
    zoneDevices.value = list as Device[]
  } catch {
    zoneDevices.value = []
  }
}

async function loadProcessDocs(): Promise<void> {
  const modes = ['generic', 'solution_fill', 'tank_recirc', 'irrigation']
  const out: Record<string, unknown> = {}
  for (const mode of modes) {
    try {
      const doc = await api.automationConfigs.get(
        'zone',
        props.zoneId,
        `zone.process_calibration.${mode}`,
      )
      out[mode] = (doc as { payload?: unknown })?.payload ?? null
    } catch {
      out[mode] = null
    }
  }
  processDocs.value = out
}

async function loadCorrectionDoc(): Promise<void> {
  try {
    const doc = await api.automationConfigs.get('zone', props.zoneId, 'zone.correction')
    correctionDoc.value =
      (doc as { payload?: Record<string, unknown> })?.payload ?? null
  } catch {
    correctionDoc.value = null
  }
}

async function loadPidDoc(): Promise<void> {
  try {
    const doc = await api.automationConfigs.get('zone', props.zoneId, 'zone.pid.ph')
    pidDoc.value = (doc as { payload?: Record<string, unknown> })?.payload ?? null
  } catch {
    pidDoc.value = null
  }
}

async function reloadAll(): Promise<void> {
  await Promise.all([
    loadPumpCalibrations(),
    loadZoneDevices(),
    loadProcessDocs(),
    loadCorrectionDoc(),
    loadPidDoc(),
  ])
}

onMounted(reloadAll)
watch(() => props.zoneId, reloadAll)

// ── Pump-drawer actions ───────────────────────────────────────────
function onPumpCalibrateFromRow(pump: PumpRow): void {
  if (!pump.canCalibrate) {
    showToast('Канал не привязан — привяжите на шаге «Автоматика»', 'warning')
    return
  }
  forcedComponent.value = pump.component as PumpCalibrationComponent
  forcedNodeChannelId.value = pump.nodeChannelId
  pumpDrawerOpen.value = true
}

function openPumpWizardGeneric(): void {
  currentSub.value = 'pumps'
  forcedComponent.value = null
  forcedNodeChannelId.value = null
  pumpDrawerOpen.value = true
}

function openPumpWizardFromReadiness(): void {
  currentSub.value = 'pumps'
  const firstPending = contracts.value.find(
    (c) => c.subsystem === 'pump' && c.status === 'blocker',
  )
  if (firstPending) {
    const componentMap: Record<string, PumpCalibrationComponent> = {
      npk: 'npk',
      ph_down: 'ph_down',
      ph_up: 'ph_up',
    }
    forcedComponent.value = componentMap[firstPending.component] ?? null
  } else {
    forcedComponent.value = null
  }
  forcedNodeChannelId.value = null
  pumpDrawerOpen.value = true
}

function onContractClick(contract: CalibrationContract): void {
  const target = contract.action?.target
  if (
    target === 'pumps' ||
    target === 'sensors' ||
    target === 'process' ||
    target === 'correction' ||
    target === 'pid'
  ) {
    currentSub.value = target as CalibrationSubKey
  }
}

function onBlockerNavigate(contract: CalibrationContract): void {
  onContractClick(contract)
  blockersOpen.value = false
}

async function onPumpStart(payload: PumpCalibrationRunPayload): Promise<void> {
  await pumpActions.startPumpCalibration(payload)
}

async function onPumpSave(payload: PumpCalibrationSavePayload): Promise<void> {
  const ok = await pumpActions.savePumpCalibration(payload)
  if (ok) {
    showToast('Калибровка сохранена', 'success')
  }
}

function onExportCsv(): void {
  const rows = pumps.value.map((p) => ({
    role: p.role,
    component: p.component,
    channel: `${p.node_uid}/${p.channel}`,
    ml_per_sec: p.ml_per_sec ?? '',
    k_ms_per_ml_l: p.k_ms_per_ml_l ?? '',
    valid_from: p.valid_from ?? '',
    source: p.source ?? '',
  }))
  if (rows.length === 0) {
    showToast('Нет калибровок для экспорта', 'info')
    return
  }
  const header = Object.keys(rows[0]).join(',')
  const body = rows
    .map((r) => Object.values(r).map((v) => JSON.stringify(v ?? '')).join(','))
    .join('\n')
  const blob = new Blob([`${header}\n${body}`], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `pump-calibrations-zone-${props.zoneId}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
</script>
