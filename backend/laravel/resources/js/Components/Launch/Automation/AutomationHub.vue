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

        <PresetSelector
          v-if="currentSub === 'contour'"
          :water-form="profile.waterForm"
          :can-configure="true"
          :tanks-count="profile.waterForm.tanksCount"
          @update:water-form="onWaterFormUpdate"
          @preset-applied="$emit('preset-applied', $event)"
          @preset-cleared="$emit('preset-cleared')"
        />

        <ZoneAutomationProfileSections
          :water-form="profile.waterForm"
          :lighting-form="profile.lightingForm"
          :zone-climate-form="profile.zoneClimateForm"
          :assignments="profile.assignments"
          :current-recipe-phase="currentRecipePhase"
          :zone-id="zoneId"
          :available-nodes="availableNodes"
          layout-mode="legacy"
          :is-system-type-locked="systemTypeLocked"
          :show-required-devices-section="currentSub === 'bindings'"
          :show-water-contour-section="currentSub === 'contour'"
          :show-irrigation-section="currentSub === 'irrigation'"
          :show-solution-correction-section="currentSub === 'correction'"
          :show-lighting-section="currentSub === 'lighting'"
          :show-zone-climate-section="currentSub === 'climate'"
          :show-lighting-enable-toggle="true"
          :show-lighting-config-fields="true"
          :show-zone-climate-enable-toggle="true"
          :show-zone-climate-config-fields="true"
          :show-node-bindings="true"
          :show-bind-buttons="true"
          :show-refresh-buttons="true"
          :show-correction-calibration-stack="false"
          :bind-disabled="bindingInProgress"
          :binding-in-progress="bindingInProgress"
          :refresh-disabled="refreshingNodes"
          :refreshing-nodes="refreshingNodes"
          :can-configure="true"
          @update:water-form="onWaterFormUpdate"
          @update:lighting-form="onLightingFormUpdate"
          @update:zone-climate-form="onZoneClimateFormUpdate"
          @update:assignments="onAssignmentsUpdate"
          @bind-devices="(r) => $emit('bind-devices', r)"
          @refresh-nodes="$emit('refresh-nodes')"
        />

        <Hint
          v-if="currentSub === 'correction' && showHints"
        >
          Полный стек калибровки (насосы / процесс / PID / автонастройка) — на следующем шаге
          «Калибровка». Здесь только целевые значения и конфигурация коррекции.
        </Hint>

        <div
          class="flex gap-1.5 flex-wrap pt-2.5 border-t border-[var(--border-muted)]"
        >
          <a
            class="px-2.5 py-1 rounded-md border border-dashed border-brand text-brand text-xs hover:bg-brand-soft"
            :href="`/zones/${zoneId}/edit`"
            target="_blank"
            rel="noopener"
          >
            Открыть полную инфраструктуру зоны ↗
          </a>
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
      </section>
    </div>

    <AutomationBlockersDrawer
      :open="blockersOpen"
      :blockers="blockers"
      @close="blockersOpen = false"
      @navigate="onBlockerNavigate"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import PresetSelector from '@/Components/AutomationForms/PresetSelector.vue'
import ZoneAutomationProfileSections from '@/Components/ZoneAutomationProfileSections.vue'
import AutomationReadinessBar from './AutomationReadinessBar.vue'
import AutomationBlockersDrawer from './AutomationBlockersDrawer.vue'
import AutomationSidebar, {
  type AutomationSubKey,
  type AutomationNavMap,
  type AutomationNavInfo,
} from './AutomationSidebar.vue'
import AutomationBreadcrumb from './AutomationBreadcrumb.vue'
import RecipeBadge from './RecipeBadge.vue'
import Button from '@/Components/Button.vue'
import Hint from '@/Components/Shared/Primitives/Hint.vue'
import {
  useAutomationContracts,
  type AutomationContract,
} from '@/composables/useAutomationContracts'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
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
    recipeSummary?: RecipeSummary | null
  }>(),
  {
    currentRecipePhase: null,
    refreshingNodes: false,
    bindingInProgress: false,
    recipeSummary: null,
  },
)

const emit = defineEmits<{
  (e: 'update:water-form', v: WaterFormState): void
  (e: 'update:lighting-form', v: LightingFormState): void
  (e: 'update:zone-climate-form', v: ZoneClimateFormState): void
  (e: 'update:assignments', v: ZoneAutomationSectionAssignments): void
  (e: 'bind-devices', roles: string[]): void
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

const { showHints } = useLaunchPreferences()

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
