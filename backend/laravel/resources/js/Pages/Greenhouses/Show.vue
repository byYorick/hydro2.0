<template>
  <AppLayout>
    <div class="space-y-6">
      <header class="space-y-4">
        <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <p class="text-xs uppercase tracking-[0.4em] text-[color:var(--text-dim)]">
              {{ greenhouse.type || 'Теплица' }}
            </p>
            <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">{{ greenhouse.name }}</h1>
            <p class="text-sm text-[color:var(--text-muted)] max-w-2xl mt-1">
              {{ greenhouse.description || 'Информационная панель по текущему состоянию теплицы и прикрепленным зонам.' }}
            </p>
          </div>
          <div class="flex items-center gap-3">
            <Link href="/zones">
              <Button size="sm" variant="outline">Все зоны</Button>
            </Link>
            <Button size="sm" variant="ghost" disabled>
              Синхронизация {{ greenhouse.timezone || 'UTC' }}
            </Button>
          </div>
        </div>
        <div class="grid gap-3 xs:grid-cols-2 md:grid-cols-4">
          <MetricCard label="Зоны" :value="zones.length" color="var(--accent-cyan)" status="success" subtitle="Общее количество зон" />
          <MetricCard label="Активные циклы" :value="activeCyclesCount" color="var(--accent-green)" status="info" subtitle="С привязанными рецептами" />
          <MetricCard label="Узлы онлайн" :value="nodeSummary.online" color="var(--accent-cyan)" status="success" subtitle="Работает" />
          <MetricCard label="Оповещения" :value="activeAlerts" color="var(--accent-red)" status="danger" subtitle="Активных" />
        </div>
      </header>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">Зоны теплицы</h2>
            <p class="text-xs text-[color:var(--text-dim)]">Панель наблюдения и управления.</p>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-[color:var(--text-dim)]">{{ zones.length }} зон</span>
            <Button size="sm" @click="openZoneWizard()">
              <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
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
            <h2 class="text-base font-semibold">Циклы</h2>
            <p class="text-xs text-[color:var(--text-dim)]">Отслеживание фаз и прогресса рецептов.</p>
          </div>
          <span class="text-xs text-[color:var(--text-dim)]">{{ cycles.length }} активных</span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <Card v-for="cycle in cycles" :key="cycle.zone_id" class="space-y-3">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold">{{ cycle.zone?.name }}</div>
                <div class="text-xs text-[color:var(--text-muted)]">{{ cycle.recipe?.name }}</div>
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
              />
            </div>
          </Card>
        </div>
        <div v-if="cycles.length === 0" class="text-xs text-[color:var(--text-dim)]">Нет активных циклов</div>
      </section>

      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold">Узлы</h2>
            <p class="text-xs text-[color:var(--text-dim)]">Состояние оборудования.</p>
          </div>
          <span class="text-xs text-[color:var(--text-dim)]">{{ nodes.length }} устройств</span>
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <Card v-for="node in nodes" :key="node.id" class="space-y-2">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-sm font-semibold">{{ node.name || node.uid }}</div>
                <div class="text-xs text-[color:var(--text-muted)]">{{ node.zone?.name }}</div>
              </div>
              <Badge :variant="node.status === 'online' ? 'success' : 'danger'">
                {{ node.status }}
              </Badge>
            </div>
            <div class="text-xs text-[color:var(--text-muted)]">Ф/В: {{ node.fw_version || '—' }}</div>
            <div class="text-xs text-[color:var(--text-muted)]">Жизненный цикл: {{ node.lifecycle_state || 'Неизвестно' }}</div>
            <div class="text-xs text-[color:var(--text-muted)]">Последний отклик: {{ formatTime(node.last_seen_at) }}</div>
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
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import MetricCard from '@/Components/MetricCard.vue'
import ZoneCard from '@/Pages/Zones/ZoneCard.vue'
import ZoneCreateWizard from '@/Components/ZoneCreateWizard.vue'
import { formatTime } from '@/utils/formatTime'
import { useSimpleModal } from '@/composables/useModal'
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

const { isOpen: showZoneWizard, open: openZoneWizard, close: closeZoneWizard } = useSimpleModal()

function onZoneCreated(zone: Zone): void {
  // Обновляем страницу для отображения новой зоны
  router.reload({ only: ['zones'] })
}

const cycles = computed(() => {
  if (!props.zones || !Array.isArray(props.zones)) {
    return []
  }
  return props.zones
    .filter((zone) => zone.activeGrowCycle || (zone.recipe_instance && zone.recipe_instance.recipe))
    .map((zone) => {
      // Используем новую модель: activeGrowCycle
      if (zone.activeGrowCycle) {
        const cycle = zone.activeGrowCycle
        const currentPhase = cycle.currentPhase
        const phaseIndex = (currentPhase?.phase_index ?? 0) + 1
        
        // Вычисляем прогресс фазы
        let progress = 0
        if (cycle.phase_started_at && currentPhase) {
          const startedAt = new Date(cycle.phase_started_at)
          const now = new Date()
          const durationHours = currentPhase.duration_hours || (currentPhase.duration_days ? currentPhase.duration_days * 24 : 0)
          const phaseEndAt = new Date(startedAt.getTime() + durationHours * 60 * 60 * 1000)
          const totalMs = phaseEndAt.getTime() - startedAt.getTime()
          const elapsedMs = now.getTime() - startedAt.getTime()
          progress = totalMs > 0 ? Math.min(100, Math.max(0, (elapsedMs / totalMs) * 100)) : 0
        }
        
        return {
          zone_id: zone.id,
          zone,
          recipe: cycle.recipeRevision?.recipe,
          phaseIndex,
          statusLabel: progress >= 85 ? 'Старт' : progress >= 45 ? 'В процессе' : 'Начало',
          progress,
        }
      }
      
      // Fallback на legacy recipeInstance
      return {
        zone_id: zone.id,
        zone,
        recipe: zone.recipe_instance?.recipe,
        phaseIndex: (zone.recipe_instance?.current_phase_index ?? 0) + 1,
        statusLabel: zone.recipe_instance?.phase_progress && zone.recipe_instance.phase_progress >= 85
          ? 'Старт' : zone.recipe_instance?.phase_progress && zone.recipe_instance.phase_progress >= 45
          ? 'В процессе' : 'Начало',
        progress: zone.recipe_instance?.phase_progress ?? 0,
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
</script>
