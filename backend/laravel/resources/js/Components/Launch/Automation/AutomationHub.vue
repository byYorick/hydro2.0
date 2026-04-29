<template>
  <div class="flex flex-col gap-3">
    <AutomationReadinessBar
      :contracts="contracts"
      :summary="summary"
      @open-blockers="blockersOpen = true"
      @open-contract="onContractClick"
      @refresh="$emit('refresh')"
    />

    <RecipeBadge
      v-if="systemTypeLocked && recipeSummary"
      :recipe-name="recipeSummary.name"
      :revision-label="recipeSummary.revisionLabel"
      :system-type="recipeSummary.systemType"
      :target-ph="recipeSummary.targetPh"
      :target-ec="recipeSummary.targetEc"
    />

    <div
      v-if="setupPendingLabel"
      class="inline-flex items-center gap-2 self-start rounded-full border border-warn-soft bg-warn-soft px-3 py-1 text-xs font-medium text-warn"
      data-testid="launch-setup-pending-badge"
    >
      <span class="h-1.5 w-1.5 rounded-full bg-warn"></span>
      {{ setupPendingLabel }}
    </div>

    <div class="grid gap-3 lg:[grid-template-columns:240px_1fr] items-start">
      <AutomationSidebar
        :current="currentSub"
        :nav="navMap"
        @select="(id) => (currentSub = id)"
      />

      <section
        class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] p-3.5 flex flex-col gap-3 min-h-[260px]"
      >
        <AutomationBreadcrumb
          :sub="currentSub"
          :title="currentSubMeta.title"
          :description="currentSubMeta.desc"
        />

        <BindingsSubview
          v-if="currentSub === 'bindings'"
          :zone-id="zoneId"
          :assignments="profile.assignments"
          :available-nodes="availableNodes"
          :binding-node-ids="bindingNodeIds"
          :binding-failed-node-ids="bindingFailedNodeIds"
          @update:assignments="onAssignmentsUpdate"
          @bind-node="(id: number) => $emit('bind-node', id)"
        />

        <ContourSubview
          v-else-if="currentSub === 'contour'"
          :water-form="profile.waterForm"
          @update:water-form="onWaterFormUpdate"
          @preset-applied="$emit('preset-applied', $event)"
          @preset-cleared="$emit('preset-cleared')"
        />

        <IrrigationSubview
          v-else-if="currentSub === 'irrigation'"
          :water-form="profile.waterForm"
          @update:water-form="onWaterFormUpdate"
        />

        <CorrectionTargetsSubview
          v-else-if="currentSub === 'correction'"
          :water-form="profile.waterForm"
          @update:water-form="onWaterFormUpdate"
        />

        <LightingSubview
          v-else-if="currentSub === 'lighting'"
          :lighting-form="profile.lightingForm"
          @update:lighting-form="onLightingFormUpdate"
        />

        <ClimateSubview
          v-else-if="currentSub === 'climate'"
          :zone-climate-form="profile.zoneClimateForm"
          :assignments="profile.assignments"
          @update:zone-climate-form="onZoneClimateFormUpdate"
        />

        <div
          class="flex items-center justify-between gap-2 flex-wrap rounded-md border border-dashed border-[var(--border-muted)] bg-[var(--bg-elevated)] px-3 py-2"
        >
          <a
            class="inline-flex items-center gap-1 px-2.5 py-1 rounded-md border border-brand-soft bg-brand-soft text-brand-ink text-xs hover:border-brand"
            :href="`/zones/${zoneId}/edit`"
            target="_blank"
            rel="noopener"
          >
            Открыть полную инфраструктуру зоны ↗
          </a>
          <div class="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              :disabled="refreshingNodes"
              @click="$emit('refresh-nodes')"
            >
              {{ refreshingNodes ? '↻ Обновление…' : '↻ Обновить ноды' }}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              @click="$emit('refresh')"
            >
              ↻ Перечитать всё
            </Button>
          </div>
        </div>
      </section>
    </div>

    <BlockersDrawer
      :open="blockersOpen"
      :blockers="blockers"
      title="Automation blockers"
      @close="blockersOpen = false"
      @navigate="(b) => onBlockerNavigate(b as AutomationContract)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AutomationReadinessBar from './AutomationReadinessBar.vue'
import BlockersDrawer from '@/Components/Launch/Shell/BlockersDrawer.vue'
import AutomationSidebar, {
  type AutomationSubKey,
  type AutomationNavMap,
  type AutomationNavInfo,
} from './AutomationSidebar.vue'
import AutomationBreadcrumb from './AutomationBreadcrumb.vue'
import RecipeBadge from './RecipeBadge.vue'
import BindingsSubview from './Subviews/BindingsSubview.vue'
import ContourSubview from './Subviews/ContourSubview.vue'
import IrrigationSubview from './Subviews/IrrigationSubview.vue'
import CorrectionTargetsSubview from './Subviews/CorrectionTargetsSubview.vue'
import LightingSubview from './Subviews/LightingSubview.vue'
import ClimateSubview from './Subviews/ClimateSubview.vue'
import Button from '@/Components/Button.vue'
import {
  useAutomationContracts,
  type AutomationContract,
} from '@/composables/useAutomationContracts'
import type { AutomationProfile } from '@/schemas/automationProfile'
import type {
  LightingFormState,
  WaterFormState,
  ZoneAutomationSectionAssignments,
  ZoneClimateFormState,
} from '@/composables/zoneAutomationTypes'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'

interface RecipeSummary {
  name?: string | null
  revisionLabel?: string | null
  systemType?: string | null
  targetPh?: number | null
  targetEc?: number | null
}

const props = withDefaults(
  defineProps<{
    zoneId: number
    profile: AutomationProfile
    currentRecipePhase?: unknown
    systemTypeLocked: boolean
    availableNodes: SetupWizardNode[]
    refreshingNodes?: boolean
    bindingInProgress?: boolean
    bindingNodeIds?: ReadonlySet<number>
    bindingFailedNodeIds?: ReadonlySet<number>
    recipeSummary?: RecipeSummary | null
    workflowPhase?: string | null
  }>(),
  {
    currentRecipePhase: null,
    refreshingNodes: false,
    bindingInProgress: false,
    bindingNodeIds: () => new Set<number>(),
    bindingFailedNodeIds: () => new Set<number>(),
    recipeSummary: null,
    workflowPhase: null,
  },
)

const emit = defineEmits<{
  (e: 'update:water-form', v: WaterFormState): void
  (e: 'update:lighting-form', v: LightingFormState): void
  (e: 'update:zone-climate-form', v: ZoneClimateFormState): void
  (e: 'update:assignments', v: ZoneAutomationSectionAssignments): void
  (e: 'bind-devices', roles: string[]): void
  (e: 'bind-node', nodeId: number): void
  (e: 'refresh-nodes'): void
  (e: 'refresh'): void
  (e: 'preset-applied', preset: unknown): void
  (e: 'preset-cleared'): void
}>()

const currentSub = ref<AutomationSubKey>('bindings')
const blockersOpen = ref(false)

const profileRef = computed(() => props.profile)
const systemTypeLockedRef = computed(() => props.systemTypeLocked)

const { contracts, summary, blockers } = useAutomationContracts({
  profile: profileRef,
  systemTypeLocked: systemTypeLockedRef,
})

const navMap = computed<AutomationNavMap>(() => {
  const aggregate = (sub: AutomationSubKey): AutomationNavInfo => {
    const items = contracts.value.filter((c) => c.subsystem === sub)
    if (items.length === 0) return { state: 'optional', count: '—' }
    const optional = items.every((c) => c.status === 'optional')
    if (optional) return { state: 'optional', count: 'опц.' }
    const blocked = items.some((c) => c.status === 'blocker')
    const passed = items.filter((c) => c.status === 'passed').length
    const required = items.filter((c) => c.required).length
    if (blocked) return { state: 'blocker', count: `${passed}/${required}` }
    if (passed === required && required > 0) return { state: 'passed', count: `${passed}/${required}` }
    return { state: 'active', count: `${passed}/${required}` }
  }

  return {
    bindings: {
      ...aggregate('bindings'),
      subtitle: 'полив · pH · EC',
    },
    contour: {
      ...aggregate('contour'),
      subtitle: props.systemTypeLocked
        ? `${topologyLabel.value} · ${tanksCount.value} бак(ов)`
        : 'нет топологии из рецепта',
    },
    irrigation: {
      ...aggregate('irrigation'),
      subtitle: irrigationSubtitle.value,
    },
    correction: {
      ...aggregate('correction'),
      subtitle: correctionSubtitle.value,
    },
    lighting: {
      ...aggregate('lighting'),
      subtitle: props.profile.lightingForm.enabled
        ? 'включён · расписание'
        : 'выключен',
    },
    climate: {
      ...aggregate('climate'),
      subtitle: props.profile.zoneClimateForm.enabled
        ? 'включён · CO₂ / вентиляция'
        : 'выключен',
    },
  }
})

const topologyLabel = computed(() => {
  const t = props.profile.waterForm.systemType
  return t === 'drip' ? 'Капельный' : t === 'nft' ? 'NFT' : 'Субстрат'
})

const tanksCount = computed(() => props.profile.waterForm.tanksCount)

const irrigationSubtitle = computed(() => {
  const w = props.profile.waterForm
  const mode = w.irrigationDecisionStrategy === 'smart_soil_v1' ? 'SMART' : 'По времени'
  return `${mode} · ${w.intervalMinutes}м / ${w.durationSeconds}с`
})

const correctionSubtitle = computed(() => {
  const w = props.profile.waterForm
  return `pH ${w.targetPh} · EC ${w.targetEc}`
})

const setupPendingLabel = computed<string | null>(() => {
  const normalized = String(props.workflowPhase ?? '').trim().toLowerCase()
  if (normalized === '' || normalized === 'ready') {
    return null
  }
  return `Setup pending: ${normalized.toUpperCase()}`
})

const SUB_META: Record<AutomationSubKey, { title: string; desc: string }> = {
  bindings: {
    title: 'Привязки узлов',
    desc: 'Обязательные роли (полив / pH / EC) и опциональные (свет, влажность почвы, CO₂, вентиляция).',
  },
  contour: {
    title: 'Водный контур',
    desc: 'Топология из рецепта, баки, насосы, таймауты диагностики и recovery.',
  },
  irrigation: {
    title: 'Полив',
    desc: 'Интервал, длительность, стратегия (по времени или SMART soil v1).',
  },
  correction: {
    title: 'Коррекция pH/EC',
    desc: 'Целевые значения и допуски. Полный стек калибровок — на шаге «Калибровка».',
  },
  lighting: {
    title: 'Свет',
    desc: 'Расписание, lux день/ночь, manual override.',
  },
  climate: {
    title: 'Климат зоны',
    desc: 'CO₂, корневая вентиляция — если включено.',
  },
}

const currentSubMeta = computed(() => SUB_META[currentSub.value])

function onContractClick(contract: AutomationContract) {
  const target = contract.action?.target
  if (!target) return
  if (
    target === 'bindings' ||
    target === 'contour' ||
    target === 'irrigation' ||
    target === 'correction' ||
    target === 'lighting' ||
    target === 'climate'
  ) {
    currentSub.value = target as AutomationSubKey
  }
}

function onBlockerNavigate(contract: AutomationContract) {
  onContractClick(contract)
  blockersOpen.value = false
}

function onWaterFormUpdate(v: WaterFormState) {
  emit('update:water-form', v)
}
function onLightingFormUpdate(v: LightingFormState) {
  emit('update:lighting-form', v)
}
function onZoneClimateFormUpdate(v: ZoneClimateFormState) {
  emit('update:zone-climate-form', v)
}
function onAssignmentsUpdate(v: ZoneAutomationSectionAssignments) {
  emit('update:assignments', v)
}
</script>
