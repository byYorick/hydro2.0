<template>
  <AppLayout>
    <div class="space-y-5">
      <section class="ui-hero p-6">
        <div class="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
          <div>
            <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
              центр циклов
            </p>
            <h1 class="text-2xl font-semibold tracking-tight mt-1">
              Циклы выращивания
            </h1>
            <p class="text-sm text-[color:var(--text-muted)] mt-1">
              Операционный контроль выполнения циклов, телеметрии и критических действий.
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button
              v-if="canConfigureCycle"
              size="sm"
              variant="secondary"
              @click="router.visit('/recipes')"
            >
              Фазы и рецепты
            </Button>
            <Button
              v-if="canManageCycle"
              size="sm"
              @click="router.visit('/grow-cycle-wizard')"
            >
              Запустить цикл
            </Button>
          </div>
        </div>
        <div class="ui-kpi-grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 mt-6">
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Активные
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-green)]">
              {{ summary.cycles_running }}
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Пауза
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
              {{ summary.cycles_paused }}
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              План
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-amber)]">
              {{ summary.cycles_planned }}
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Без цикла
            </div>
            <div class="ui-kpi-value">
              {{ summary.cycles_none }}
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Алерты
            </div>
            <div class="ui-kpi-value text-[color:var(--accent-red)]">
              {{ summary.alerts_active }}
            </div>
          </div>
          <div class="ui-kpi-card">
            <div class="ui-kpi-label">
              Устройства
            </div>
            <div class="ui-kpi-value">
              {{ summary.devices_online }}/{{ summary.devices_total }}
            </div>
          </div>
        </div>
      </section>

      <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
        <div class="flex flex-col lg:flex-row lg:items-center gap-3">
          <div class="flex flex-col sm:flex-row sm:items-center gap-2 flex-1">
            <input
              v-model="query"
              class="input-field flex-1"
              placeholder="Поиск зоны, культуры или теплицы"
            />
            <select
              v-model="statusFilter"
              class="input-select w-full sm:w-44"
            >
              <option value="">
                Все статусы
              </option>
              <option value="RUNNING">
                Активные
              </option>
              <option value="PAUSED">
                Пауза
              </option>
              <option value="PLANNED">
                План
              </option>
              <option value="NONE">
                Без цикла
              </option>
            </select>
            <select
              v-model="greenhouseFilter"
              class="input-select w-full sm:w-48"
            >
              <option value="">
                Все теплицы
              </option>
              <option
                v-for="gh in greenhouses"
                :key="gh.id"
                :value="String(gh.id)"
              >
                {{ gh.name }}
              </option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="btn btn-ghost h-9 px-3 text-xs"
              @click="showOnlyAlerts = !showOnlyAlerts"
            >
              {{ showOnlyAlerts ? 'Показать все' : 'Только алерты' }}
            </button>
            <button
              type="button"
              class="btn btn-ghost h-9 px-3 text-xs"
              @click="toggleDense"
            >
              {{ denseView ? 'Стандартный вид' : 'Компактный вид' }}
            </button>
          </div>
        </div>
      </section>

      <div
        v-if="!filteredZones.length"
        class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-6 text-sm text-[color:var(--text-muted)] text-center"
      >
        Нет зон по текущим фильтрам.
      </div>
      <div
        v-else
        class="grid grid-cols-1 xl:grid-cols-2 gap-4"
      >
        <div
          v-for="zone in pagedZones"
          :key="zone.id"
          class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4 flex flex-col gap-4"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-3">
                <Link
                  :href="`/zones/${zone.id}`"
                  class="text-lg font-semibold truncate hover:underline text-[color:var(--text-primary)]"
                >
                  {{ zone.name }}
                </Link>
                <Badge :variant="getZoneStatusVariant(zone.status)">
                  {{ translateStatus(zone.status) }}
                </Badge>
                <Badge
                  v-if="zone.cycle"
                  :variant="getCycleStatusVariant(zone.cycle.status, 'center')"
                >
                  {{ getCycleStatusLabel(zone.cycle.status, 'short') }}
                </Badge>
              </div>
              <div class="text-xs text-[color:var(--text-dim)] mt-1 flex flex-wrap items-center gap-2">
                <span v-if="zone.greenhouse">{{ zone.greenhouse.name }}</span>
                <span v-if="zone.plant">Культура: {{ zone.plant.name }}</span>
                <span v-else-if="zone.recipe">Рецепт: {{ zone.recipe.name }}</span>
                <span v-if="zone.devices.total">Устройства: {{ zone.devices.online }}/{{ zone.devices.total }}</span>
              </div>
            </div>
            <div
              v-if="zone.alerts_count > 0"
              class="status-chip status-chip--alarm"
            >
              Алертов: {{ zone.alerts_count }}
            </div>
            <div
              v-else
              class="status-chip status-chip--running"
            >
              ОК
            </div>
          </div>

          <div
            v-if="zone.cycle"
            class="space-y-3"
          >
            <div>
              <div class="flex items-center justify-between text-xs text-[color:var(--text-muted)]">
                <span>Прогресс цикла</span>
                <span>{{ zone.cycle.progress?.overall_pct ?? 0 }}%</span>
              </div>
              <div class="mt-1 h-2 rounded-full bg-[color:var(--border-muted)] overflow-hidden">
                <div
                  class="h-full bg-[color:var(--accent-green)] transition-all"
                  :style="{ width: `${zone.cycle.progress?.overall_pct ?? 0}%` }"
                ></div>
              </div>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <div class="metric-pill">
                <span class="text-[color:var(--text-dim)]">Стадия</span>
                <span class="text-[color:var(--text-primary)] font-semibold">
                  {{ zone.cycle.current_stage?.name || '—' }}
                </span>
              </div>
              <div
                v-if="zone.cycle.expected_harvest_at"
                class="metric-pill"
              >
                <span class="text-[color:var(--text-dim)]">Сбор</span>
                <span class="text-[color:var(--text-primary)] font-semibold">
                  {{ formatDate(zone.cycle.expected_harvest_at) }}
                </span>
              </div>
              <div
                v-if="zone.cycle.planting_at"
                class="metric-pill"
              >
                <span class="text-[color:var(--text-dim)]">Посев</span>
                <span class="text-[color:var(--text-primary)] font-semibold">
                  {{ formatDate(zone.cycle.planting_at) }}
                </span>
              </div>
            </div>
          </div>

          <div
            v-else
            class="text-sm text-[color:var(--text-muted)]"
          >
            Активный цикл не запущен. Можно создать план или запустить новый цикл.
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div class="surface-strong rounded-lg px-2 py-2 border border-[color:var(--border-muted)]">
              <div class="text-[10px] uppercase text-[color:var(--text-dim)]">
                pH
              </div>
              <div class="text-[color:var(--text-primary)] font-semibold">
                {{ formatMetric(zone.telemetry.ph, 2) }}
              </div>
            </div>
            <div class="surface-strong rounded-lg px-2 py-2 border border-[color:var(--border-muted)]">
              <div class="text-[10px] uppercase text-[color:var(--text-dim)]">
                EC
              </div>
              <div class="text-[color:var(--text-primary)] font-semibold">
                {{ formatMetric(zone.telemetry.ec, 2) }}
              </div>
            </div>
            <div class="surface-strong rounded-lg px-2 py-2 border border-[color:var(--border-muted)]">
              <div class="text-[10px] uppercase text-[color:var(--text-dim)]">
                Темп.
              </div>
              <div class="text-[color:var(--text-primary)] font-semibold">
                {{ formatMetric(zone.telemetry.temperature, 1) }}°C
              </div>
            </div>
            <div class="surface-strong rounded-lg px-2 py-2 border border-[color:var(--border-muted)]">
              <div class="text-[10px] uppercase text-[color:var(--text-dim)]">
                Влажн.
              </div>
              <div class="text-[color:var(--text-primary)] font-semibold">
                {{ formatMetric(zone.telemetry.humidity, 0) }}%
              </div>
            </div>
          </div>

          <div
            v-if="zone.alerts_preview.length"
            class="space-y-1 text-xs text-[color:var(--text-dim)]"
          >
            <div class="font-semibold text-[color:var(--text-primary)]">
              Последние алерты
            </div>
            <div
              v-for="alert in zone.alerts_preview"
              :key="alert.id"
              class="flex items-center justify-between gap-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2 py-1"
            >
              <span class="truncate">{{ alert.type }}</span>
              <span class="text-[10px]">{{ formatTime(alert.created_at) }}</span>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <template v-if="zone.cycle">
              <Button
                v-if="canManageCycle && zone.cycle.status === 'RUNNING'"
                size="sm"
                variant="secondary"
                :disabled="isActionLoading(zone.id, 'pause')"
                @click="pauseCycle(zone)"
              >
                {{ isActionLoading(zone.id, 'pause') ? 'Пауза...' : 'Пауза' }}
              </Button>
              <Button
                v-else-if="canManageCycle && zone.cycle.status === 'PAUSED'"
                size="sm"
                variant="secondary"
                :disabled="isActionLoading(zone.id, 'resume')"
                @click="resumeCycle(zone)"
              >
                {{ isActionLoading(zone.id, 'resume') ? 'Запуск...' : 'Возобновить' }}
              </Button>
              <Button
                v-if="canIssueZoneCommands"
                size="sm"
                variant="outline"
                @click="openActionModal(zone, 'FORCE_IRRIGATION')"
              >
                Промывка
              </Button>
              <Button
                v-if="canManageCycle"
                size="sm"
                variant="secondary"
                :disabled="isActionLoading(zone.id, 'harvest')"
                @click="openHarvestModal(zone)"
              >
                {{ isActionLoading(zone.id, 'harvest') ? 'Фиксация...' : 'Сбор' }}
              </Button>
              <Button
                v-if="canManageCycle"
                size="sm"
                variant="outline"
                :disabled="isActionLoading(zone.id, 'abort')"
                @click="openAbortModal(zone)"
              >
                Стоп
              </Button>
            </template>
            <template v-else-if="canManageCycle && !zone.cycle">
              <Button
                size="sm"
                @click="router.visit('/grow-cycle-wizard')"
              >
                Запустить цикл
              </Button>
            </template>
            <Button
              size="sm"
              variant="ghost"
              @click="router.visit(`/zones/${zone.id}`)"
            >
              Детали зоны
            </Button>
          </div>

          <div
            v-if="zone.telemetry.updated_at"
            class="text-[11px] text-[color:var(--text-dim)]"
          >
            Обновление: {{ formatTime(zone.telemetry.updated_at) }}
          </div>
        </div>
      </div>

      <Pagination
        v-if="filteredZones.length > perPage"
        v-model:current-page="currentPage"
        v-model:per-page="perPage"
        :total="filteredZones.length"
      />
    </div>

    <ZoneActionModal
      v-if="actionModal.zone"
      :show="actionModal.open"
      :zone-id="actionModal.zone.id"
      :action-type="actionModal.actionType"
      @close="closeActionModal"
      @submit="submitAction"
    />

    <ConfirmModal
      :open="harvestModal.open"
      title="Зафиксировать сбор"
      message=" "
      confirm-text="Подтвердить"
      :loading="isActionLoading(harvestModal.zone?.id || 0, 'harvest')"
      @close="closeHarvestModal"
      @confirm="confirmHarvest"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Зафиксировать сбор урожая и завершить цикл?</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">Метка партии (опционально)</label>
          <input
            v-model="harvestModal.batchLabel"
            class="input-field mt-1 w-full"
            placeholder="Например: Batch-042"
          />
        </div>
      </div>
    </ConfirmModal>

    <ConfirmModal
      :open="abortModal.open"
      title="Аварийная остановка"
      message=" "
      confirm-text="Остановить"
      confirm-variant="danger"
      :loading="isActionLoading(abortModal.zone?.id || 0, 'abort')"
      @close="closeAbortModal"
      @confirm="confirmAbort"
    >
      <div class="space-y-3 text-sm text-[color:var(--text-muted)]">
        <div>Остановить цикл? Это действие нельзя отменить.</div>
        <div>
          <label class="text-xs text-[color:var(--text-dim)]">Причина (опционально)</label>
          <textarea
            v-model="abortModal.notes"
            class="input-field mt-1 w-full h-20 resize-none"
            placeholder="Короткое описание причины"
          ></textarea>
        </div>
      </div>
    </ConfirmModal>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import Pagination from '@/Components/Pagination.vue'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import { translateStatus } from '@/utils/i18n'
import { getCycleStatusLabel, getCycleStatusVariant } from '@/utils/growCycleStatus'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { useCommands } from '@/composables/useCommands'
import { TOAST_TIMEOUT } from '@/constants/timeouts'

interface Greenhouse {
  id: number
  name: string
}

interface CycleStage {
  name?: string
  code?: string
  started_at?: string | null
}

interface CycleProgress {
  overall_pct?: number
  stage_pct?: number
}

interface GrowCycle {
  id: number
  status: string
  planting_at?: string | null
  expected_harvest_at?: string | null
  current_stage?: CycleStage | null
  progress?: CycleProgress
}

interface ZoneTelemetry {
  ph: number | null
  ec: number | null
  temperature: number | null
  humidity: number | null
  co2: number | null
  updated_at: string | null
}

interface ZoneSummary {
  id: number
  name: string
  status: string
  greenhouse: Greenhouse | null
  telemetry: ZoneTelemetry
  alerts_count: number
  alerts_preview: Array<{ id: number; type: string; details: string; created_at: string }>
  devices: { total: number; online: number }
  recipe: { id: number; name: string } | null
  plant: { id: number; name: string } | null
  cycle: GrowCycle | null
}

interface Summary {
  zones_total: number
  cycles_running: number
  cycles_paused: number
  cycles_planned: number
  cycles_none: number
  alerts_active: number
  devices_online: number
  devices_total: number
}

interface Props {
  summary: Summary
  zones: ZoneSummary[]
  greenhouses: Greenhouse[]
}

const props = defineProps<Props>()
const page = usePage()
const role = computed(() => (page.props.auth as any)?.user?.role || 'viewer')
const canConfigureCycle = computed(() => ['admin', 'agronomist'].includes(role.value))
const canManageCycle = computed(() => ['admin', 'agronomist', 'operator'].includes(role.value))
const canIssueZoneCommands = computed(() => ['admin', 'operator', 'agronomist', 'engineer'].includes(role.value))

const query = ref('')
const statusFilter = ref('')
const greenhouseFilter = ref('')
const showOnlyAlerts = ref(false)
const denseView = ref(false)
const currentPage = ref(1)
const perPage = ref(8)

const { api } = useApi()
const { showToast } = useToast()
const { sendZoneCommand } = useCommands(showToast)

const actionLoading = reactive<Record<string, boolean>>({})

const filteredZones = computed(() => {
  const search = query.value.trim().toLowerCase()
  return props.zones.filter((zone) => {
    const matchesSearch = !search || [
      zone.name,
      zone.greenhouse?.name,
      zone.recipe?.name,
      zone.plant?.name,
    ]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(search))

    const cycleStatus = zone.cycle?.status || 'NONE'
    const matchesStatus = !statusFilter.value || statusFilter.value === cycleStatus

    const matchesGreenhouse = !greenhouseFilter.value || String(zone.greenhouse?.id || '') === greenhouseFilter.value

    const matchesAlerts = !showOnlyAlerts.value || zone.alerts_count > 0

    return matchesSearch && matchesStatus && matchesGreenhouse && matchesAlerts
  })
})

const pagedZones = computed(() => {
  const start = (currentPage.value - 1) * perPage.value
  return filteredZones.value.slice(start, start + perPage.value)
})

watch([query, statusFilter, greenhouseFilter, showOnlyAlerts], () => {
  currentPage.value = 1
})

function toggleDense() {
  denseView.value = !denseView.value
  perPage.value = denseView.value ? 12 : 8
}

function formatMetric(value: number | null, digits: number) {
  if (value === null || value === undefined) {
    return '—'
  }
  return Number(value).toFixed(digits)
}

function formatDate(value: string) {
  const date = new Date(value)
  return new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: 'short' }).format(date)
}

function formatTime(value: string) {
  const date = new Date(value)
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function getZoneStatusVariant(status: string) {
  switch (status) {
    case 'RUNNING':
      return 'success'
    case 'PAUSED':
      return 'info'
    case 'WARNING':
      return 'warning'
    case 'ALARM':
      return 'danger'
    default:
      return 'neutral'
  }
}

function setActionLoading(zoneId: number, action: string, value: boolean) {
  actionLoading[`${zoneId}-${action}`] = value
}

function isActionLoading(zoneId: number, action: string) {
  return Boolean(actionLoading[`${zoneId}-${action}`])
}

async function reloadCenter() {
  await router.reload({ only: ['zones', 'summary'] })
}

async function pauseCycle(zone: ZoneSummary) {
  if (!zone.cycle?.id) return
  setActionLoading(zone.id, 'pause', true)
  try {
    const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/pause`)
    if (response.data?.status === 'ok') {
      showToast('Цикл приостановлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
    }
  } finally {
    setActionLoading(zone.id, 'pause', false)
  }
}

async function resumeCycle(zone: ZoneSummary) {
  if (!zone.cycle?.id) return
  setActionLoading(zone.id, 'resume', true)
  try {
    const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/resume`)
    if (response.data?.status === 'ok') {
      showToast('Цикл возобновлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
    }
  } finally {
    setActionLoading(zone.id, 'resume', false)
  }
}

const harvestModal = reactive<{ open: boolean; zone: ZoneSummary | null; batchLabel: string }>({
  open: false,
  zone: null,
  batchLabel: '',
})

const abortModal = reactive<{ open: boolean; zone: ZoneSummary | null; notes: string }>({
  open: false,
  zone: null,
  notes: '',
})

function openHarvestModal(zone: ZoneSummary) {
  harvestModal.zone = zone
  harvestModal.batchLabel = ''
  harvestModal.open = true
}

function closeHarvestModal() {
  harvestModal.open = false
  harvestModal.zone = null
}

async function confirmHarvest() {
  const zone = harvestModal.zone
  if (!zone?.cycle?.id) return
  setActionLoading(zone.id, 'harvest', true)
  try {
    const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/harvest`, {
      batch_label: harvestModal.batchLabel || undefined,
    })
    if (response.data?.status === 'ok') {
      showToast('Урожай зафиксирован', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
      closeHarvestModal()
    }
  } finally {
    setActionLoading(zone.id, 'harvest', false)
  }
}

function openAbortModal(zone: ZoneSummary) {
  abortModal.zone = zone
  abortModal.notes = ''
  abortModal.open = true
}

function closeAbortModal() {
  abortModal.open = false
  abortModal.zone = null
}

async function confirmAbort() {
  const zone = abortModal.zone
  if (!zone?.cycle?.id) return
  setActionLoading(zone.id, 'abort', true)
  try {
    const response = await api.post(`/api/grow-cycles/${zone.cycle.id}/abort`, {
      notes: abortModal.notes || undefined,
    })
    if (response.data?.status === 'ok') {
      showToast('Цикл остановлен', 'success', TOAST_TIMEOUT.NORMAL)
      await reloadCenter()
      closeAbortModal()
    }
  } finally {
    setActionLoading(zone.id, 'abort', false)
  }
}

const actionModal = reactive<{ open: boolean; zone: ZoneSummary | null; actionType: 'FORCE_IRRIGATION' }>({
  open: false,
  zone: null,
  actionType: 'FORCE_IRRIGATION',
})

function openActionModal(zone: ZoneSummary, actionType: 'FORCE_IRRIGATION') {
  actionModal.open = true
  actionModal.zone = zone
  actionModal.actionType = actionType
}

function closeActionModal() {
  actionModal.open = false
  actionModal.zone = null
}

async function submitAction(payload: { actionType: 'FORCE_IRRIGATION'; params: Record<string, number> }) {
  if (!actionModal.zone) return
  await sendZoneCommand(actionModal.zone.id, payload.actionType, payload.params)
  closeActionModal()
}
</script>
