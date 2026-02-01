<template>
  <AppLayout>
    <div class="space-y-6">
      <header class="space-y-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p class="text-xs uppercase tracking-[0.4em] text-[color:var(--text-dim)]">
              {{ greenhouse.type || 'Теплица' }}
            </p>
            <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">
              {{ greenhouse.name }}
            </h1>
            <p class="text-sm text-[color:var(--text-muted)] max-w-2xl mt-1">
              {{ greenhouse.description || 'Информационная панель по текущему состоянию теплицы и прикрепленным зонам.' }}
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
              Климат и обслуживание оборудования.
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              :disabled="!canManageGreenhouse || climateSubmitting"
              @click="openClimateModal"
            >
              Управление климатом
            </Button>
            <Button
              size="sm"
              variant="outline"
              :disabled="!canManageGreenhouse || maintenanceEnterTargets.length === 0 || maintenanceSubmitting"
              @click="openMaintenanceModal('MAINTENANCE')"
            >
              В обслуживание
            </Button>
            <Button
              size="sm"
              variant="ghost"
              :disabled="!canManageGreenhouse || maintenanceExitTargets.length === 0 || maintenanceSubmitting"
              @click="openMaintenanceModal('ACTIVE')"
            >
              Завершить обслуживание
            </Button>
          </div>
        </div>
        <div class="text-xs text-[color:var(--text-dim)]">
          Климат применится ко всем {{ climateZoneIds.length }} зонам теплицы.
          В обслуживании сейчас {{ maintenanceExitTargets.length }} / {{ climateNodes.length }} климат-узлов.
          <span v-if="!canManageGreenhouse">
            Доступно только для ролей «оператор», «агроном», «инженер», «админ».
          </span>
        </div>
        <div
          v-if="climateFailures.length > 0"
          data-testid="climate-failures"
          class="rounded-xl border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] p-3 text-xs text-[color:var(--badge-danger-text)]"
        >
          <div class="font-semibold">
            Ошибки применения климата
          </div>
          <div class="mt-1 text-[color:var(--text-muted)]">
            Не удалось отправить команды для {{ climateFailures.length }} зон.
          </div>
          <div class="mt-2 space-y-1">
            <div
              v-for="failure in climateFailures"
              :key="failure.zoneId"
              data-testid="climate-failure-item"
              class="flex items-start gap-2"
            >
              <span class="font-semibold">{{ failure.zoneName }}</span>
              <span>— {{ failure.reason }}</span>
            </div>
          </div>
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
              size="sm"
              @click="openZoneWizard()"
            >
              <svg
                class="w-4 h-4 mr-1"
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
            <div class="h-2 rounded-full bg-[color:var(--border-muted)] overflow-hidden">
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

    <!-- Мастер создания зоны -->
    <ZoneCreateWizard
      :show="showZoneWizard"
      :greenhouse-id="greenhouse.id"
      @close="closeZoneWizard"
      @created="onZoneCreated"
    />

    <ZoneActionModal
      v-if="climateModalOpen"
      :show="climateModalOpen"
      action-type="FORCE_CLIMATE"
      :zone-id="climateZoneIds[0] || 0"
      @close="climateModalOpen = false"
      @submit="onClimateSubmit"
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
import { computed, ref, reactive } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import MetricCard from '@/Components/MetricCard.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import ZoneCreateWizard from '@/Components/ZoneCreateWizard.vue'
import ZoneActionModal from '@/Components/ZoneActionModal.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import { formatTime } from '@/utils/formatTime'
import { logger } from '@/utils/logger'
import { calculateProgressFromDuration } from '@/utils/growCycleProgress'
import { useSimpleModal } from '@/composables/useModal'
import { useCommands } from '@/composables/useCommands'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { Zone } from '@/types'
import type { Device } from '@/types'
import type { ZoneTelemetry } from '@/types'
import type { CommandParams } from '@/types'

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
}

type MaintenanceTargetState = 'MAINTENANCE' | 'ACTIVE'

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
const canManageGreenhouse = computed(() => (
  role.value === 'agronomist'
  || role.value === 'admin'
  || role.value === 'operator'
  || role.value === 'engineer'
))

const { showToast } = useToast()
const { api } = useApi()
const { sendZoneCommand } = useCommands()

const { isOpen: showZoneWizard, open: openZoneWizard, close: closeZoneWizard } = useSimpleModal()

function onZoneCreated(_zone: Zone): void {
  // Обновляем страницу для отображения новой зоны
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
        
        // Вычисляем прогресс фазы
        let progress = 0
        const phaseDurationHours = activeGrowCycle
          ? (currentPhase?.duration_hours ?? ((currentPhase?.duration_days || 0) * 24))
          : (legacyCycle?.recipe?.phases?.[legacyCycle?.current_phase_index ?? 0]?.duration_hours ?? 0)

        const phaseStartCandidate = activeGrowCycle?.phase_started_at || activeGrowCycle?.started_at || legacyCycle?.started_at

        if (phaseDurationHours && phaseStartCandidate) {
          progress = calculateProgressFromDuration(
            phaseStartCandidate,
            phaseDurationHours,
            null
          ) ?? 0
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
const nodeSummary = computed(() => props.nodeSummary || {
  online: 0,
  offline: 0,
  total: 0,
})

const activeAlerts = computed(() => props.activeAlerts ?? 0)

const climateModalOpen = ref(false)
const climateSubmitting = ref(false)
const climateFailures = ref<Array<{ zoneId: number; zoneName: string; reason: string }>>([])
const climateZoneIds = computed(() => zones.value.map(zone => zone.id))

const climateNodes = computed(() => nodes.value.filter(node => node.type === 'climate'))

const maintenanceSubmitting = ref(false)
const maintenanceModal = reactive({
  open: false,
  targetState: 'MAINTENANCE' as MaintenanceTargetState,
})

const maintenanceEnterTargets = computed(() => {
  const allowedStates = new Set(['ASSIGNED_TO_ZONE', 'ACTIVE', 'DEGRADED'])
  return climateNodes.value.filter((node) => {
    if (!node.lifecycle_state || node.lifecycle_state === 'MAINTENANCE') {
      return false
    }
    return allowedStates.has(node.lifecycle_state)
  })
})

const maintenanceExitTargets = computed(() => {
  return climateNodes.value.filter(node => node.lifecycle_state === 'MAINTENANCE')
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
    return `Перевести в обслуживание ${total} климат-узлов теплицы? Узлы перейдут в offline.`
  }
  return `Завершить обслуживание для ${total} климат-узлов и вернуть их в активный режим?`
})

const maintenanceModalConfirmText = computed(() => {
  return maintenanceModal.targetState === 'MAINTENANCE' ? 'В обслуживание' : 'Завершить'
})

const maintenanceModalConfirmVariant = computed(() => {
  return maintenanceModal.targetState === 'MAINTENANCE' ? 'warning' : 'primary'
})

function openClimateModal(): void {
  if (!canManageGreenhouse.value) {
    showToast('Доступно только для роли «агроном».', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  if (climateZoneIds.value.length === 0) {
    showToast('Нет зон в этой теплице.', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  climateFailures.value = []
  climateModalOpen.value = true
}

function resolveClimateError(error: unknown): string {
  const payload = error as { response?: { data?: { message?: string } }; message?: string }
  return payload?.response?.data?.message || payload?.message || 'Неизвестная ошибка'
}

async function onClimateSubmit({ params }: { params: CommandParams }): Promise<void> {
  if (climateSubmitting.value) return

  const zoneIds = climateZoneIds.value
  if (zoneIds.length === 0) {
    showToast('Нет зон для управления климатом.', 'warning', TOAST_TIMEOUT.NORMAL)
    return
  }

  climateSubmitting.value = true
  climateFailures.value = []

  try {
    const results = await Promise.allSettled(
      zoneIds.map(zoneId => sendZoneCommand(zoneId, 'FORCE_CLIMATE', params))
    )
    const successCount = results.filter(result => result.status === 'fulfilled').length
    const failedCount = results.length - successCount
    const failures: Array<{ zoneId: number; zoneName: string; reason: string }> = []

    results.forEach((result) => {
      if (result.status === 'rejected') {
        logger.warn('[Greenhouses/Show] Climate command failed', result.reason)
      }
    })
    results.forEach((result, index) => {
      if (result.status === 'rejected') {
        const zoneId = zoneIds[index]
        const zoneName = zones.value.find(zone => zone.id === zoneId)?.name || `Зона ${zoneId}`
        failures.push({
          zoneId,
          zoneName,
          reason: resolveClimateError(result.reason),
        })
      }
    })
    climateFailures.value = failures

    if (successCount && failedCount === 0) {
      showToast(`Климат применён для ${successCount} зон.`, 'success', TOAST_TIMEOUT.NORMAL)
    } else if (successCount && failedCount > 0) {
      showToast(`Климат применён для ${successCount} зон, ошибок: ${failedCount}.`, 'warning', TOAST_TIMEOUT.LONG)
    } else {
      showToast('Не удалось применить климат для выбранных зон.', 'error', TOAST_TIMEOUT.LONG)
    }
  } finally {
    climateSubmitting.value = false
  }
}

function openMaintenanceModal(targetState: MaintenanceTargetState): void {
  if (!canManageGreenhouse.value) {
    showToast('Доступно только для роли «агроном».', 'warning', TOAST_TIMEOUT.NORMAL)
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
  if (maintenanceSubmitting.value) return

  const targetState = maintenanceModal.targetState
  const targets = maintenanceTargets.value

  if (targets.length === 0) {
    showToast('Нет узлов для выполнения операции.', 'warning', TOAST_TIMEOUT.NORMAL)
    maintenanceModal.open = false
    return
  }

  maintenanceSubmitting.value = true

  try {
    const results = await Promise.allSettled(
      targets.map(node => api.post(`/api/nodes/${node.id}/lifecycle/transition`, {
        target_state: targetState,
        reason: `Greenhouse ${props.greenhouse.name}: ${targetState === 'MAINTENANCE' ? 'maintenance' : 'resume'}`,
      }))
    )
    const successCount = results.filter(result => result.status === 'fulfilled').length
    const failedCount = results.length - successCount
    const actionLabel = targetState === 'MAINTENANCE' ? 'в обслуживание' : 'в активный режим'

    results.forEach((result) => {
      if (result.status === 'rejected') {
        logger.warn('[Greenhouses/Show] Maintenance transition failed', result.reason)
      }
    })

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
  }
}
</script>
