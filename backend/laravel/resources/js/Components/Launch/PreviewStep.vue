<template>
  <section class="grid gap-4 items-start lg:[grid-template-columns:1.3fr_1fr]">
    <div class="flex flex-col gap-3">
      <ShellCard title="Сводка запуска">
        <template #actions>
          <Chip :tone="errors.length === 0 ? 'growth' : 'warn'">
            <template #icon>
              <span class="font-mono text-[11px]">{{ errors.length === 0 ? '✓' : '!' }}</span>
            </template>
            {{ errors.length === 0 ? 'готова' : `${errors.length} ошибок` }}
          </Chip>
        </template>

        <div class="grid gap-3 lg:grid-cols-2">
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <Stat
              label="Зона"
              :value="zoneLabel"
              mono
            />
            <Stat
              label="Растение"
              :value="plantLabel"
              mono
            />
            <Stat
              label="Рецепт"
              :value="recipeLabel"
              mono
              tone="brand"
            />
            <Stat
              label="Система"
              :value="systemLabel"
              mono
            />
            <Stat
              label="pH target"
              :value="phLabel"
              mono
              tone="brand"
            />
            <Stat
              label="EC target"
              :value="ecLabel"
              mono
              tone="brand"
            />
            <Stat
              label="Полив"
              :value="irrigLabel"
              mono
            />
            <Stat
              label="Дата посадки"
              :value="formatPlanting(payloadPreview.planting_at)"
              mono
            />
            <Stat
              label="Метка партии"
              :value="payloadPreview.batch_label || '—'"
              mono
            />
          </div>

          <div class="flex flex-col gap-1.5 min-w-0">
            <div
              class="text-[11px] uppercase tracking-wider text-[var(--text-dim)] font-medium pb-0.5"
            >
              Контуры
            </div>
            <ContourRow
              label="Полив"
              :node="contourNodeLabel('irrigation')"
              :bound="!!automationProfile?.assignments?.irrigation"
            >
              <template #icon>
                <Ic name="drop" />
              </template>
            </ContourRow>
            <ContourRow
              label="pH"
              :node="contourNodeLabel('ph_correction')"
              :bound="!!automationProfile?.assignments?.ph_correction"
            >
              <template #icon>
                <Ic name="beaker" />
              </template>
            </ContourRow>
            <ContourRow
              label="EC"
              :node="contourNodeLabel('ec_correction')"
              :bound="!!automationProfile?.assignments?.ec_correction"
            >
              <template #icon>
                <Ic name="zap" />
              </template>
            </ContourRow>
          </div>
        </div>
      </ShellCard>

      <ShellCard
        v-if="recipePhases.length"
        title="Фазы рецепта"
        :pad="false"
      >
        <RecipePhasesSummary :phases="recipePhases as never" />
      </ShellCard>

      <ShellCard title="Diff · zone.logic_profile">
        <template #actions>
          <Chip tone="brand">
            <span class="font-mono">overrides</span>
          </Chip>
        </template>
        <slot name="diff-preview"></slot>
      </ShellCard>
    </div>

    <aside class="flex flex-col gap-3 lg:sticky lg:top-[108px] lg:self-start">
      <ShellCard title="Readiness check">
        <div class="flex flex-col">
          <ReadinessRow
            v-for="row in readinessRows"
            :key="row.key"
            :label="row.label"
            :status="row.status"
            :note="row.note"
          />
        </div>
      </ShellCard>

      <div
        class="rounded-md border border-brand bg-gradient-to-b from-[var(--bg-surface)] to-brand-soft p-4 flex flex-col gap-3"
      >
        <div class="text-[11px] font-bold uppercase tracking-widest text-brand-ink">
          Запуск цикла
        </div>
        <div class="text-lg font-semibold leading-tight text-[var(--text-primary)]">
          <template v-if="ready">
            Готово.<br />
            <span class="font-normal text-sm text-[var(--text-muted)]">
              Посадка сейчас, первый полив через
              <span class="font-mono">{{ firstIrrigationLabel }}</span>.
            </span>
          </template>
          <template v-else>
            <span class="text-warn">{{ readinessRows.filter(r => r.status !== 'ok').length }}</span>
            проверок не пройдено
          </template>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <Button
            variant="success"
            size="md"
            :disabled="!ready"
            @click="$emit('launch')"
          >
            ▶ Запустить цикл
          </Button>
          <Button
            v-if="canSimulate"
            size="md"
            variant="secondary"
            @click="$emit('simulate')"
          >
            Симуляция
          </Button>
        </div>
      </div>

      <Hint :show="showHints">
        После «Запустить цикл» вызывается <span class="font-mono">POST /api/zones/{id}/grow-cycles</span>
        с overrides. AE3 создаёт grow cycle, инициализирует стартовую фазу
        и планирует первый полив через scheduler-dispatch.
      </Hint>
    </aside>
  </section>
</template>

<script setup lang="ts">
import { computed, h } from 'vue'
import type { GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch'
import RecipePhasesSummary from '@/Components/Launch/RecipePhasesSummary.vue'
import { Chip, Stat, Hint } from '@/Components/Shared/Primitives'
import ShellCard from '@/Components/Launch/Shell/ShellCard.vue'
import ContourRow from '@/Components/Launch/Preview/ContourRow.vue'
import ReadinessRow, { type ReadinessStatus } from '@/Components/Launch/Preview/ReadinessRow.vue'
import Button from '@/Components/Button.vue'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type { AutomationProfile } from '@/schemas/automationProfile'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow'

interface Props {
  payloadPreview: Partial<GrowCycleLaunchPayload>
  errors: Array<{ path: string; message: string }>
  recipePhases?: unknown[]
  /** Профиль автоматизации (assignments + waterForm) для ContourRow и Stat'ов pH/EC. */
  automationProfile?: AutomationProfile | null
  /** Узлы зоны для маппинга id → uid в ContourRow. */
  availableNodes?: readonly SetupWizardNode[]
  /** Активная фаза рецепта (ph_target/ec_target/irrigation_*). */
  currentRecipePhase?: unknown
  /** Имя/ревизия рецепта для Stat. */
  recipeName?: string | null
  recipeRevisionLabel?: string | null
  /** Manifest readiness — для показа blocker'ов из backend. */
  readinessBlockers?: readonly LaunchFlowReadinessBlocker[]
  readinessWarnings?: readonly string[]
  /** Сервис health (AE3 online?) — пробрасывается из useServiceHealth родителя. */
  ae3Online?: boolean
  canSimulate?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  recipePhases: () => [],
  automationProfile: null,
  availableNodes: () => [],
  currentRecipePhase: null,
  recipeName: null,
  recipeRevisionLabel: null,
  readinessBlockers: () => [],
  readinessWarnings: () => [],
  ae3Online: false,
  canSimulate: false,
})

defineEmits<{
  (e: 'launch'): void
  (e: 'simulate'): void
}>()

const { showHints } = useLaunchPreferences()

const zoneLabel = computed(
  () => (props.payloadPreview.zone_id ? `id ${props.payloadPreview.zone_id}` : '—'),
)
const plantLabel = computed(
  () => (props.payloadPreview.plant_id ? `id ${props.payloadPreview.plant_id}` : '—'),
)
const recipeLabel = computed(() => {
  const name = props.recipeName
  const rev = props.recipeRevisionLabel
  if (name && rev) return `${name} · ${rev}`
  if (name) return name
  if (props.payloadPreview.recipe_revision_id) {
    return `r${props.payloadPreview.recipe_revision_id}`
  }
  return '—'
})

const phase = computed(
  () =>
    props.currentRecipePhase as
      | {
          ph_target?: number | null
          ec_target?: number | null
          irrigation_mode?: string | null
          irrigation_interval_sec?: number | null
          irrigation_duration_sec?: number | null
        }
      | null,
)

const systemLabel = computed(
  () => phase.value?.irrigation_mode ?? props.automationProfile?.waterForm.systemType ?? '—',
)

const phLabel = computed(() => {
  const p = phase.value?.ph_target ?? props.automationProfile?.waterForm.targetPh
  return p != null ? String(p) : '—'
})

const ecLabel = computed(() => {
  const e = phase.value?.ec_target ?? props.automationProfile?.waterForm.targetEc
  return e != null ? `${e} mS/cm` : '—'
})

const irrigLabel = computed(() => {
  const interval =
    phase.value?.irrigation_interval_sec != null
      ? Math.round(phase.value.irrigation_interval_sec / 60)
      : props.automationProfile?.waterForm.intervalMinutes
  const duration =
    phase.value?.irrigation_duration_sec ??
    props.automationProfile?.waterForm.durationSeconds
  if (interval == null || duration == null) return '—'
  return `${interval}м / ${duration}с`
})

const firstIrrigationLabel = computed(() => {
  const interval =
    phase.value?.irrigation_interval_sec != null
      ? Math.round(phase.value.irrigation_interval_sec / 60)
      : props.automationProfile?.waterForm.intervalMinutes
  if (interval == null) return '—'
  return `${interval} мин`
})

function nodeLabelById(id: number | null | undefined): string | null {
  if (!id) return null
  const node = props.availableNodes.find((n) => n.id === id)
  if (!node) return `Node #${id}`
  return node.uid ?? node.name ?? `Node #${id}`
}

function contourNodeLabel(role: 'irrigation' | 'ph_correction' | 'ec_correction'): string | null {
  const id = props.automationProfile?.assignments?.[role]
  return nodeLabelById(typeof id === 'number' ? id : null)
}

function blockersBySubsystem(prefix: string): LaunchFlowReadinessBlocker[] {
  return props.readinessBlockers.filter((b) =>
    b.code?.toLowerCase().includes(prefix),
  )
}

interface ReadinessRowDef {
  key: string
  label: string
  status: ReadinessStatus
  note: string | null
}

const readinessRows = computed<ReadinessRowDef[]>(() => {
  const a = props.automationProfile?.assignments
  const requiredAssigned = a
    ? [a.irrigation, a.ph_correction, a.ec_correction].filter((v) => typeof v === 'number' && v > 0).length
    : 0

  const sensorBlockers = blockersBySubsystem('sensor')
  const pumpBlockers = blockersBySubsystem('pump')
  const pidBlockers = blockersBySubsystem('pid')
  const procBlockers = blockersBySubsystem('process')

  return [
    {
      key: 'gh',
      label: 'Теплица выбрана',
      status: props.payloadPreview.zone_id ? 'ok' : 'warn',
      note: null,
    },
    {
      key: 'zn',
      label: 'Зона создана и привязана',
      status: props.payloadPreview.zone_id ? 'ok' : 'err',
      note: props.payloadPreview.zone_id ? `id ${props.payloadPreview.zone_id}` : null,
    },
    {
      key: 'pl',
      label: 'Рецепт активен',
      status: props.payloadPreview.recipe_revision_id ? 'ok' : 'err',
      note: props.recipeRevisionLabel,
    },
    {
      key: 'aut',
      label: 'Контуры привязаны',
      status: requiredAssigned === 3 ? 'ok' : requiredAssigned > 0 ? 'warn' : 'err',
      note: `${requiredAssigned}/3`,
    },
    {
      key: 'sens',
      label: 'Сенсоры откалиброваны',
      status: sensorBlockers.length === 0 ? 'ok' : 'warn',
      note: sensorBlockers.length > 0 ? `${sensorBlockers.length} blocker` : null,
    },
    {
      key: 'pumps',
      label: 'Насосы откалиброваны',
      status: pumpBlockers.length === 0 ? 'ok' : 'warn',
      note: pumpBlockers.length > 0 ? `${pumpBlockers.length} blocker` : null,
    },
    {
      key: 'pid',
      label: 'PID pH и EC сохранены',
      status: pidBlockers.length === 0 ? 'ok' : 'warn',
      note: pidBlockers.length > 0 ? `${pidBlockers.length} blocker` : null,
    },
    {
      key: 'proc',
      label: 'Процессы настроены',
      status: procBlockers.length === 0 ? 'ok' : 'warn',
      note: procBlockers.length > 0 ? `${procBlockers.length} blocker` : null,
    },
    {
      key: 'ae',
      label: 'automation-engine online',
      status: props.ae3Online ? 'ok' : 'warn',
      note: props.ae3Online ? '9405' : 'нет связи',
    },
  ]
})

const ready = computed(
  () => props.errors.length === 0 && readinessRows.value.every((r) => r.status === 'ok'),
)

function formatPlanting(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Маленькие inline-иконки для ContourRow.
const ICONS: Record<string, string> = {
  drop: 'M8 2c2 3 5 5.5 5 8a5 5 0 01-10 0c0-2.5 3-5 5-8z',
  beaker: 'M6 2v5L3 13a1.5 1.5 0 001.3 2h7.4A1.5 1.5 0 0013 13L10 7V2',
  zap: 'M9 2l-5 8h4l-1 4 5-8H8z',
}
const Ic = (props: { name: keyof typeof ICONS }) =>
  h('svg', { width: 14, height: 14, viewBox: '0 0 16 16', fill: 'none' }, [
    h('path', {
      d: ICONS[props.name],
      stroke: 'currentColor',
      'stroke-width': '1.4',
      'stroke-linejoin': 'round',
      'stroke-linecap': props.name === 'wave' ? 'round' : undefined,
    }),
  ])
</script>
