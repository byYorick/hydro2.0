<template>
  <div class="space-y-4">
    <!-- ══════════════════════════════════════════════════════════════
         CRITICAL ALERT BAR — shown only when zones have issues
    ══════════════════════════════════════════════════════════════ -->
    <div
      v-if="criticalZones.length > 0"
      class="rounded-xl border px-4 py-3 flex items-center justify-between gap-3"
      :class="hasAlarm
        ? 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]'
        : 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]'"
    >
      <div class="flex items-center gap-2 min-w-0">
        <span class="shrink-0 text-base">{{ hasAlarm ? '🔴' : '⚠️' }}</span>
        <div class="text-sm font-medium truncate">
          <span :class="hasAlarm ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--accent-amber)]'">
            {{ criticalZones[0].name }}:
          </span>
          <span class="ml-1 text-[color:var(--text-primary)]">
            {{ criticalZoneHint(criticalZones[0]) }}
          </span>
          <span
            v-if="criticalZones.length > 1"
            class="ml-2 text-[color:var(--text-muted)]"
          >
            и ещё {{ criticalZones.length - 1 }} {{ criticalZones.length - 1 === 1 ? 'зона' : 'зон' }}
          </span>
        </div>
      </div>
      <Link :href="`/zones/${criticalZones[0].id}`">
        <Button
          size="sm"
          :variant="hasAlarm ? 'danger' : 'warning'"
          class="shrink-0"
        >
          Перейти
        </Button>
      </Link>
    </div>

    <!-- ══════════════════════════════════════════════════════════════
         KPI ROW — compact counters
    ══════════════════════════════════════════════════════════════ -->
    <div class="grid grid-cols-4 gap-2">
      <div class="glass-panel rounded-xl p-3 text-center border border-[color:var(--border-muted)]">
        <div class="text-2xl font-bold text-[color:var(--accent-green)]">
          {{ runningCount }}
        </div>
        <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)] mt-0.5">
          В работе
        </div>
      </div>
      <div
        class="glass-panel rounded-xl p-3 text-center border"
        :class="warningCount > 0 ? 'border-[color:var(--badge-warning-border)]' : 'border-[color:var(--border-muted)]'"
      >
        <div
          class="text-2xl font-bold"
          :class="warningCount > 0 ? 'text-[color:var(--accent-amber)]' : 'text-[color:var(--text-dim)]'"
        >
          {{ warningCount }}
        </div>
        <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)] mt-0.5">
          Warning
        </div>
      </div>
      <div
        class="glass-panel rounded-xl p-3 text-center border"
        :class="alarmCount > 0 ? 'border-[color:var(--badge-danger-border)]' : 'border-[color:var(--border-muted)]'"
      >
        <div
          class="text-2xl font-bold"
          :class="alarmCount > 0 ? 'text-[color:var(--accent-red)]' : 'text-[color:var(--text-dim)]'"
        >
          {{ alarmCount }}
        </div>
        <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)] mt-0.5">
          Alarm
        </div>
      </div>
      <div class="glass-panel rounded-xl p-3 text-center border border-[color:var(--border-muted)]">
        <div class="text-2xl font-bold text-[color:var(--accent-cyan)]">
          {{ activeCyclesCount }}
        </div>
        <div class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)] mt-0.5">
          Циклов
        </div>
      </div>
    </div>

    <!-- ══════════════════════════════════════════════════════════════
         ZONE HEALTH GRID — main view
    ══════════════════════════════════════════════════════════════ -->
    <div
      v-if="zones.length > 0"
      class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
    >
      <div
        v-for="zone in sortedZones"
        :key="zone.id"
        class="surface-card surface-card--elevated rounded-2xl border transition-all duration-200 overflow-hidden"
        :class="zoneCardBorder(zone)"
      >
        <!-- Zone header -->
        <div
          class="flex items-start justify-between px-4 pt-4 pb-3 border-b"
          :class="zoneHeaderBorder(zone)"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <div
                class="w-2 h-2 rounded-full shrink-0 transition-all duration-500"
                :class="zoneDotClass(zone)"
              ></div>
              <Link
                :href="`/zones/${zone.id}`"
                class="text-sm font-semibold truncate hover:text-[color:var(--accent-cyan)] transition-colors"
              >
                {{ zone.name }}
              </Link>
            </div>
            <div
              v-if="zoneCropInfo(zone)"
              class="text-xs text-[color:var(--text-muted)] mt-0.5 truncate"
            >
              {{ zoneCropInfo(zone) }}
            </div>
          </div>
          <div class="flex items-center gap-1.5 shrink-0 ml-2">
            <Badge
              :variant="zoneStatusVariant(zone)"
              size="sm"
            >
              {{ translateStatus(zone.status) }}
            </Badge>
          </div>
        </div>

        <!-- Phase progress strip -->
        <div
          v-if="zonePhaseInfo(zone)"
          class="px-4 py-2 border-b border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
        >
          <div class="flex items-center justify-between text-[10px] text-[color:var(--text-muted)] mb-1">
            <span>{{ zonePhaseInfo(zone)!.phaseName }}</span>
            <span class="tabular-nums">
              День {{ zonePhaseInfo(zone)!.dayElapsed }}/{{ zonePhaseInfo(zone)!.dayTotal }}
            </span>
          </div>
          <div class="w-full h-1 bg-[color:var(--border-muted)] rounded-full overflow-hidden">
            <div
              class="h-full bg-[color:var(--accent-cyan)] rounded-full transition-all duration-500"
              :style="{ width: `${zonePhaseInfo(zone)!.progress}%` }"
            ></div>
          </div>
        </div>

        <!-- Gauges + sparkline area -->
        <div class="px-4 py-4">
          <!-- pH / EC / Temp gauges in a row -->
          <div class="flex items-start justify-around gap-1">
            <ZoneHealthGauge
              :value="zone.telemetry?.ph"
              :target-min="resolveTarget(zone, 'ph', 'min')"
              :target-max="resolveTarget(zone, 'ph', 'max')"
              :global-min="4.0"
              :global-max="9.0"
              label="pH"
              :decimals="2"
            />
            <div class="w-px self-stretch bg-[color:var(--border-muted)]"></div>
            <ZoneHealthGauge
              :value="zone.telemetry?.ec"
              :target-min="resolveTarget(zone, 'ec', 'min')"
              :target-max="resolveTarget(zone, 'ec', 'max')"
              :global-min="0"
              :global-max="5.0"
              label="EC"
              unit=" мСм"
              :decimals="2"
            />
            <template v-if="zone.telemetry?.temperature != null">
              <div class="w-px self-stretch bg-[color:var(--border-muted)]"></div>
              <ZoneHealthGauge
                :value="zone.telemetry.temperature"
                :target-min="resolveTarget(zone, 'temperature', 'min')"
                :target-max="resolveTarget(zone, 'temperature', 'max')"
                :global-min="10"
                :global-max="40"
                label="T°C"
                :decimals="1"
              />
            </template>
          </div>

          <!-- pH sparkline (24h) -->
          <div
            v-if="sparklineData(zone.id)"
            class="mt-3"
          >
            <div class="text-[9px] text-[color:var(--text-dim)] mb-1 uppercase tracking-wider">
              pH · 24 часа
            </div>
            <Sparkline
              :data="sparklineData(zone.id)!"
              :width="240"
              :height="28"
              :color="sparklineColor(zone)"
              :show-area="true"
              :stroke-width="1.5"
            />
          </div>

          <!-- AI prediction hint -->
          <div class="mt-2">
            <ZoneAIPredictionHint
              :zone-id="zone.id"
              metric-type="PH"
              :target-min="resolveTarget(zone, 'ph', 'min')"
              :target-max="resolveTarget(zone, 'ph', 'max')"
              :horizon-minutes="90"
            />
          </div>
        </div>

        <!-- Footer actions -->
        <div class="px-4 pb-3 flex items-center gap-2 border-t border-[color:var(--border-muted)] pt-3">
          <Button
            size="sm"
            variant="outline"
            class="flex-1 text-xs"
            @click="handleForceIrrigation(zone.id)"
          >
            💧 Полить
          </Button>
          <Link
            :href="`/zones/${zone.id}`"
            class="flex-1"
          >
            <Button
              size="sm"
              variant="secondary"
              class="w-full text-xs"
            >
              ↗ Зона
            </Button>
          </Link>
        </div>
      </div>
    </div>

    <!-- Empty zones state -->
    <div
      v-else
      class="glass-panel border border-[color:var(--border-muted)] rounded-2xl text-center py-12 text-[color:var(--text-dim)]"
    >
      <div class="text-4xl mb-3">
        🌿
      </div>
      <div class="text-sm font-medium">
        Нет зон для мониторинга
      </div>
      <div class="text-xs mt-1 text-[color:var(--text-muted)]">
        Создайте зоны и запустите циклы выращивания
      </div>
      <Link
        href="/zones"
        class="mt-4 inline-block"
      >
        <Button
          size="sm"
          variant="primary"
        >
          Управление зонами
        </Button>
      </Link>
    </div>

    <!-- ══════════════════════════════════════════════════════════════
         ACTIVE RECIPES — compact list
    ══════════════════════════════════════════════════════════════ -->
    <div
      v-if="activeRecipesSummary.length > 0"
      class="space-y-2"
    >
      <div class="flex items-center justify-between">
        <h2 class="text-xs font-semibold uppercase tracking-widest text-[color:var(--text-dim)]">
          Активные рецепты
        </h2>
        <Link
          href="/recipes"
          class="text-xs text-[color:var(--accent-cyan)] hover:underline transition-colors"
        >
          Все рецепты →
        </Link>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div
          v-for="recipe in activeRecipesSummary"
          :key="recipe.id"
          class="glass-panel border border-[color:var(--border-muted)] rounded-xl px-3 py-2.5 flex items-center justify-between gap-3 hover:border-[color:var(--border-strong)] transition-colors"
        >
          <div class="min-w-0">
            <div class="text-sm font-medium truncate">
              {{ recipe.name }}
            </div>
            <div class="text-xs text-[color:var(--text-muted)] mt-0.5">
              {{ recipe.zonesCount }} {{ recipe.zonesCount === 1 ? 'зона' : 'зон' }}
              <span
                v-if="recipe.phaseName"
                class="ml-1"
              >· {{ recipe.phaseName }}</span>
            </div>
          </div>
          <Link :href="`/recipes/${recipe.id}`">
            <Button
              size="sm"
              variant="outline"
              class="shrink-0 text-xs"
            >
              Открыть
            </Button>
          </Link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { Link } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import Sparkline from '@/Components/Sparkline.vue'
import ZoneHealthGauge from '@/Components/ZoneHealthGauge.vue'
import ZoneAIPredictionHint from '@/Components/ZoneAIPredictionHint.vue'
import { translateStatus } from '@/utils/i18n'
import { useTelemetry } from '@/composables/useTelemetry'
import type { Zone, Recipe } from '@/types'
import type { BadgeVariant } from '@/Components/Badge.vue'

// ─── Props ────────────────────────────────────────────────────────────────────
interface Props {
  dashboard: {
    zones?: Zone[]
    recipes?: Recipe[]
    zonesByStatus?: Record<string, number>
    problematicZones?: Zone[]
  }
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'force-irrigation', zoneId: number): void
}>()

// ─── Data ──────────────────────────────────────────────────────────────────────
const zones = computed<Zone[]>(() => props.dashboard.zones ?? [])
const recipes = computed<Recipe[]>(() => props.dashboard.recipes ?? [])

// ─── KPI counts ───────────────────────────────────────────────────────────────
const runningCount = computed(() => props.dashboard.zonesByStatus?.RUNNING ?? 0)
const warningCount = computed(() => props.dashboard.zonesByStatus?.WARNING ?? 0)
const alarmCount   = computed(() => props.dashboard.zonesByStatus?.ALARM ?? 0)
const activeCyclesCount = computed(() =>
  zones.value.filter(z => z.activeGrowCycle != null).length
)

// ─── Critical zones (ALARM first, then WARNING) ───────────────────────────────
const criticalZones = computed(() =>
  zones.value
    .filter(z => z.status === 'ALARM' || z.status === 'WARNING')
    .sort((a, b) => (a.status === 'ALARM' ? 0 : 1) - (b.status === 'ALARM' ? 0 : 1))
)
const hasAlarm = computed(() => criticalZones.value.some(z => z.status === 'ALARM'))

function criticalZoneHint(zone: Zone): string {
  const issues = (zone.issues ?? []).slice(0, 1)
  if (issues.length) return issues[0]
  if (zone.alerts_count && zone.alerts_count > 0) return `${zone.alerts_count} активных алертов`
  return zone.status === 'ALARM' ? 'критическое отклонение' : 'требует внимания'
}

// ─── Zone sort: ALARM → WARNING → RUNNING → others ───────────────────────────
const sortedZones = computed(() => {
  const priority: Record<string, number> = { ALARM: 0, WARNING: 1, RUNNING: 2, PAUSED: 3, IDLE: 4, NEW: 5 }
  return [...zones.value].sort((a, b) => (priority[a.status] ?? 9) - (priority[b.status] ?? 9))
})

// ─── Zone card styles ─────────────────────────────────────────────────────────
function zoneCardBorder(zone: Zone): string {
  if (zone.status === 'ALARM') return 'border-[color:var(--badge-danger-border)]'
  if (zone.status === 'WARNING') return 'border-[color:var(--badge-warning-border)]'
  return 'border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)]'
}

function zoneHeaderBorder(zone: Zone): string {
  if (zone.status === 'ALARM') return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]'
  if (zone.status === 'WARNING') return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)]'
  return 'border-[color:var(--border-muted)]'
}

function zoneDotClass(zone: Zone): string {
  const map: Record<string, string> = {
    RUNNING: 'bg-[color:var(--accent-green)] shadow-[0_0_6px_var(--accent-green)]',
    WARNING: 'bg-[color:var(--accent-amber)]',
    ALARM: 'bg-[color:var(--accent-red)] animate-pulse',
    PAUSED: 'bg-[color:var(--text-dim)]',
    IDLE: 'bg-[color:var(--text-dim)]',
    NEW: 'bg-[color:var(--text-dim)]',
  }
  return map[zone.status] ?? 'bg-[color:var(--text-dim)]'
}

function zoneStatusVariant(zone: Zone): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
    RUNNING: 'success', WARNING: 'warning', ALARM: 'danger',
    PAUSED: 'neutral', IDLE: 'neutral', NEW: 'neutral',
  }
  return map[zone.status] ?? 'neutral'
}

// ─── Zone info ────────────────────────────────────────────────────────────────
function zoneCropInfo(zone: Zone): string | null {
  return zone.activeGrowCycle?.recipeRevision?.recipe?.name
    ?? zone.recipe_instance?.recipe?.name
    ?? zone.crop
    ?? null
}

interface PhaseInfo {
  phaseName: string
  dayElapsed: number
  dayTotal: number
  progress: number
}

function zonePhaseInfo(zone: Zone): PhaseInfo | null {
  const cycle = zone.activeGrowCycle
  if (!cycle) return null

  const currentPhaseIndex = cycle.current_phase_index
    ?? cycle.currentPhase?.phase_index
    ?? 0
  const phaseName = cycle.current_phase_name
    ?? (cycle.currentPhase?.phase_index != null
      ? `Фаза ${currentPhaseIndex + 1}`
      : null)
  if (!phaseName) return null

  const startedAt = cycle.phase_started_at
    ? new Date(cycle.phase_started_at)
    : cycle.started_at
      ? new Date(cycle.started_at)
      : null
  if (!startedAt) return null

  const daysElapsed = Math.max(0, Math.floor((Date.now() - startedAt.getTime()) / (1000 * 60 * 60 * 24)))

  const recipePhase = cycle.recipe?.phases?.find((p: any) => (p.phase_index ?? 0) === currentPhaseIndex)
  const durationHours = recipePhase?.duration_hours
  const daysTotal = durationHours ? Math.ceil(durationHours / 24) : daysElapsed || 1
  const progress = Math.min(100, Math.round((daysElapsed / daysTotal) * 100))

  return { phaseName: phaseName as string, dayElapsed: daysElapsed, dayTotal: daysTotal, progress }
}

// ─── Target resolution ────────────────────────────────────────────────────────
type TargetKey = 'ph' | 'ec' | 'temperature' | 'humidity'
type TargetSide = 'min' | 'max'

function resolveTarget(zone: Zone, key: TargetKey, side: TargetSide): number | null {
  const t = zone.targets as any
  if (!t) return null
  // Nested: { ph: { min, max } }
  if (t[key] && typeof t[key] === 'object') return t[key][side] ?? null
  // Flat: ph_min, ph_max, temp_min, temp_max
  const flatKeyMap: Record<TargetKey, string> = { ph: 'ph', ec: 'ec', temperature: 'temp', humidity: 'humidity' }
  return t[`${flatKeyMap[key]}_${side}`] ?? null
}

// ─── Sparklines ───────────────────────────────────────────────────────────────
const { fetchHistory } = useTelemetry()
const sparklines = ref<Record<number, number[]>>({})

async function loadSparkline(zone: Zone): Promise<void> {
  try {
    const now = new Date()
    const from = new Date(now.getTime() - 24 * 60 * 60 * 1000)
    const history = await fetchHistory(zone.id, 'PH', {
      from: from.toISOString(),
      to: now.toISOString(),
    })
    if (history.length > 0) {
      sparklines.value = { ...sparklines.value, [zone.id]: history.map(p => p.value) }
    }
  } catch {
    // Non-critical
  }
}

onMounted(() => {
  zones.value.forEach((zone, i) => {
    setTimeout(() => loadSparkline(zone), i * 250)
  })
})

function sparklineData(zoneId: number): number[] | null {
  return sparklines.value[zoneId] ?? null
}

function sparklineColor(zone: Zone): string {
  if (zone.status === 'ALARM') return 'var(--accent-red)'
  if (zone.status === 'WARNING') return 'var(--accent-amber)'
  return 'var(--accent-cyan)'
}

// ─── Quick actions ────────────────────────────────────────────────────────────
function handleForceIrrigation(zoneId: number): void {
  emit('force-irrigation', zoneId)
}

// ─── Active recipes summary ───────────────────────────────────────────────────
const activeRecipesSummary = computed(() =>
  recipes.value
    .map(recipe => {
      const zonesWithRecipe = zones.value.filter(z =>
        z.activeGrowCycle?.recipeRevision?.recipe_id === recipe.id
        || (z.recipe_instance as any)?.recipe_id === recipe.id
      )
      if (zonesWithRecipe.length === 0) return null
      const phaseInfo = zonePhaseInfo(zonesWithRecipe[0])
      return {
        id: recipe.id,
        name: recipe.name,
        zonesCount: zonesWithRecipe.length,
        phaseName: phaseInfo?.phaseName ?? zonesWithRecipe[0].activeGrowCycle?.current_phase_name ?? null,
      }
    })
    .filter(Boolean)
    .slice(0, 6) as Array<{ id: number; name: string; zonesCount: number; phaseName: string | null }>
)
</script>
