<template>
  <Head title="Запуск цикла" />
  <AppLayout>
    <LaunchShell>
    <template #topbar>
      <LaunchTopBar
        :user-email="userEmail"
        :quick-jump-steps="stepperSteps"
        @jump="onStepSelect"
      >
        <template
          v-if="breadcrumbZoneName"
          #breadcrumbs
        >
          <Link
            :href="dashboardHref"
            class="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            Dashboard
          </Link>
          <span class="text-[var(--text-dim)]">/</span>
          <Link
            :href="zonesHref"
            class="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            Зоны
          </Link>
          <span class="text-[var(--text-dim)]">/</span>
          <span class="text-[var(--text-primary)] font-mono">{{ breadcrumbZoneName }}</span>
          <span class="text-[var(--text-dim)]">/</span>
          <span class="text-[var(--text-primary)]">Мастер запуска</span>
        </template>
      </LaunchTopBar>
    </template>

    <template #stepper>
      <LaunchStepper
        v-if="stepperSteps.length > 0"
        :steps="stepperSteps"
        :active="activeIndex"
        :completion="completion"
        @select="onStepSelect"
      />
    </template>

    <div
      v-if="manifestQuery.isLoading.value"
      class="px-4 py-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-sm text-[var(--text-muted)]"
    >
      Загрузка manifest'а…
    </div>

    <div
      v-else-if="manifestQuery.isError.value"
      class="px-4 py-3 rounded-md border border-alert bg-alert-soft text-sm text-alert flex items-center gap-2"
    >
      <span>Не удалось загрузить manifest: {{ (manifestQuery.error.value as Error)?.message }}</span>
      <Button
        size="sm"
        variant="secondary"
        @click="() => manifestQuery.refetch()"
      >
        Повторить
      </Button>
    </div>

    <template v-else-if="manifest && stepperSteps.length > 0">
      <StepHeader
        :step="currentStepDef"
        :index="activeIndex"
        :total="stepperSteps.length"
      />

      <ZoneStep
        v-if="currentStep === 'zone'"
        :model-value="state.zone_id"
        @update:model-value="onZoneSelected"
      />

      <RecipeStep
        v-else-if="currentStep === 'recipe'"
        :recipe-revision-id="state.recipe_revision_id"
        :plant-id="state.plant_id"
        :planting-at="state.planting_at"
        :batch-label="state.batch_label"
        :notes="state.notes"
        :recipes="recipeOptions"
        :plants="plantOptions"
        :recipe-phases="(recipePhases as never)"
        :errors="errors"
        @update:recipe-revision-id="updateField('recipe_revision_id', $event)"
        @update:plant-id="updateField('plant_id', $event)"
        @update:planting-at="updateField('planting_at', $event)"
        @update:batch-label="updateField('batch_label', $event)"
        @update:notes="updateField('notes', $event)"
        @refresh-plants="loadReferenceData"
        @refresh-recipes="loadReferenceData"
      />

      <AutomationStep
        v-else-if="currentStep === 'automation'"
        :zone-id="state.zone_id"
        :current-recipe-phase="currentRecipePhase"
        :recipe-summary="recipeSummary"
        @update:profile="onAutomationProfileUpdate"
      />

      <CalibrationStep
        v-else-if="currentStep === 'calibration'"
        :zone-id="state.zone_id"
        :phase-targets="phaseTargetsForPid"
        @calibration-updated="onCalibrationUpdated"
      />

      <PreviewStep
        v-else-if="currentStep === 'preview'"
        :payload-preview="state"
        :errors="errorList"
        :recipe-phases="recipePhases"
        :automation-profile="automationProfile"
        :available-nodes="availableNodesForPreview"
        :current-recipe-phase="currentRecipePhase"
        :recipe-name="recipeSummary?.name ?? null"
        :recipe-revision-label="recipeSummary?.revisionLabel ?? null"
        :zone-name="zoneNameById[state.zone_id ?? 0] ?? null"
        :plant-name="plantNameById[state.plant_id ?? 0] ?? null"
        :readiness-blockers="manifest.readiness.blockers"
        :readiness-warnings="manifest.readiness.warnings"
        :ae3-online="ae3Online"
        @launch="handleSubmit"
      >
        <template #diff-preview>
          <DiffPreview
            :current="currentLogicProfile"
            :next="mergedLogicProfile"
          />
        </template>
      </PreviewStep>
    </template>

    <template #footer>
      <LaunchFooterNav
        v-if="stepperSteps.length > 0"
        :active="activeIndex"
        :total="stepperSteps.length"
        :completion="completion"
        :can-launch="canLaunch"
        :submitting="submitting"
        @back="goBack"
        @next="goNext"
        @launch="handleSubmit"
      />
    </template>
    </LaunchShell>
  </AppLayout>
</template>

<script setup lang="ts">
import { Head, Link, router } from '@inertiajs/vue3'
import { computed, onMounted, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import LaunchShell from '@/Components/Launch/Shell/LaunchShell.vue'
import LaunchTopBar from '@/Components/Launch/Shell/LaunchTopBar.vue'
import LaunchStepper from '@/Components/Launch/Shell/LaunchStepper.vue'
import LaunchFooterNav from '@/Components/Launch/Shell/LaunchFooterNav.vue'
import StepHeader from '@/Components/Launch/Shell/StepHeader.vue'
import type {
  LaunchStep,
  StepCompletion,
} from '@/Components/Launch/Shell/types'
import ZoneStep from '@/Components/Launch/ZoneStep.vue'
import RecipeStep from '@/Components/Launch/RecipeStep.vue'
import AutomationStep from '@/Components/Launch/AutomationStep.vue'
import CalibrationStep from '@/Components/Launch/CalibrationStep.vue'
import PreviewStep from '@/Components/Launch/PreviewStep.vue'
import DiffPreview from '@/Components/Launch/DiffPreview.vue'
import Button from '@/Components/Button.vue'
import { useFormSchema } from '@/composables/useFormSchema'
import { growCycleLaunchSchema, type GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch'
import {
  automationProfileDefaults,
  type AutomationProfile,
} from '@/schemas/automationProfile'
import {
  assignmentsToApplyPayload,
  profileToZoneLogicProfile,
} from '@/composables/automationProfileConverters'
import { resolveRecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import { useQueryClient } from '@tanstack/vue-query'
import { launchFlowKeys } from '@/services/queries/launchFlow'
import { useLaunchGrowCycleMutation, useLaunchManifest } from '@/services/queries/launchFlow'
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useLaunchSteps } from '@/composables/useLaunchSteps'
import { useLaunchPreviewContext } from '@/composables/useLaunchPreviewContext'
import { useLaunchTopBarContext } from '@/composables/useLaunchTopBarContext'
import { route } from '@/utils/route'

const props = defineProps<{
  zoneId: number | null
  auth: { user: { role: string; email?: string | null; name?: string | null } }
}>()

const { showToast } = useToast()

const form = useFormSchema<GrowCycleLaunchPayload>(growCycleLaunchSchema, {
  zone_id: props.zoneId ?? undefined,
  overrides: {},
  bindings: {},
} as Partial<GrowCycleLaunchPayload>)

const state = form.state
const errors = form.errors

const zoneIdRef = computed<number | null>(() => state.zone_id ?? null)
const manifestQuery = useLaunchManifest(zoneIdRef)
const launchMutation = useLaunchGrowCycleMutation()

const manifest = computed(() => manifestQuery.data.value ?? null)

const currentStep = ref<string>('')

const automationProfile = ref<AutomationProfile>(
  structuredClone(automationProfileDefaults),
)

const {
  stepperSteps,
  activeIndex,
  completion,
  currentStepDef,
  canLaunch,
  canProceedStep,
} = useLaunchSteps({
  state,
  manifest,
  automationProfile,
  isFormValid: form.isValid,
  currentStep,
})

watch(
  () => stepperSteps.value.map((s) => s.id).join('|'),
  (joined) => {
    if (!joined) return
    const first = stepperSteps.value[0]?.id ?? ''
    if (
      !currentStep.value ||
      !stepperSteps.value.some((s) => s.id === currentStep.value)
    ) {
      currentStep.value = first
    }
  },
  { immediate: true },
)

interface RecipeOption {
  id: number
  name: string
  latest_published_revision_id?: number | null
  plants?: Array<{ id: number; name: string }>
}
const recipeOptions = ref<RecipeOption[]>([])
const plantOptions = ref<Array<{ id: number; name: string }>>([])
const zoneNameById = ref<Record<number, string>>({})

const plantNameById = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {}
  for (const p of plantOptions.value) map[p.id] = p.name
  return map
})

function onAutomationProfileUpdate(next: AutomationProfile) {
  automationProfile.value = next
}

const { availableNodes: availableNodesForPreview, ae3Online } =
  useLaunchPreviewContext(zoneIdRef)

const { userEmail, breadcrumbZoneName, dashboardHref, zonesHref } =
  useLaunchTopBarContext({
    auth: props.auth,
    zoneId: zoneIdRef,
    zoneNameById: computed(() => zoneNameById.value),
  })

const phaseTargetsForPid = computed(() =>
  resolveRecipePhasePidTargets(currentRecipePhase.value ?? null),
)

const queryClient = useQueryClient()

async function onCalibrationUpdated() {
  const zoneId = state.zone_id ?? null
  await queryClient.invalidateQueries({ queryKey: launchFlowKeys.manifest(zoneId) })
}

const revisionPhasesCache = ref<Record<number, unknown[]>>({})
const currentRecipePhase = ref<unknown>(null)
const recipePhases = ref<unknown[]>([])

async function loadRecipeRevisionPhases(revisionId: number) {
  if (revisionPhasesCache.value[revisionId]) {
    const cached = revisionPhasesCache.value[revisionId]
    currentRecipePhase.value = cached[0] ?? null
    recipePhases.value = cached
    return
  }
  try {
    const rev = await api.recipes.getRevision(revisionId)
    const phases = Array.isArray((rev as { phases?: unknown[] })?.phases)
      ? ((rev as { phases: unknown[] }).phases as unknown[])
      : []
    revisionPhasesCache.value = { ...revisionPhasesCache.value, [revisionId]: phases }
    currentRecipePhase.value = phases[0] ?? null
    recipePhases.value = phases
  } catch {
    currentRecipePhase.value = null
    recipePhases.value = []
  }
}

watch(
  () => state.recipe_revision_id,
  (revId) => {
    if (!revId) {
      currentRecipePhase.value = null
      recipePhases.value = []
      return
    }
    loadRecipeRevisionPhases(revId)
  },
  { immediate: true },
)

const selectedRecipe = computed(
  () => recipeOptions.value.find((r) => r.latest_published_revision_id === state.recipe_revision_id) ?? null,
)

const recipeSummary = computed(() => {
  const phase = currentRecipePhase.value as
    | {
        irrigation_mode?: string | null
        ph_target?: number | null
        ec_target?: number | null
      }
    | null
  if (!selectedRecipe.value && !phase) return null
  return {
    name: selectedRecipe.value?.name ?? null,
    revisionLabel: state.recipe_revision_id ? `r${state.recipe_revision_id}` : null,
    systemType: phase?.irrigation_mode ?? null,
    targetPh: phase?.ph_target ?? null,
    targetEc: phase?.ec_target ?? null,
  }
})

const errorList = computed(() =>
  Object.entries(errors.value).map(([path, message]) => ({ path, message })),
)

const currentLogicProfile = ref<Record<string, unknown>>({})

async function loadLogicProfile(zoneId: number) {
  try {
    const profile = await api.automationConfigs.get('zone', zoneId, 'zone.logic_profile')
    const payload = (profile as unknown as { payload?: Record<string, unknown> }).payload ?? {}
    currentLogicProfile.value = payload
  } catch {
    currentLogicProfile.value = {}
  }
}

watch(
  () => state.zone_id,
  (id) => {
    if (typeof id === 'number') loadLogicProfile(id)
  },
  { immediate: true },
)

const mergedLogicProfile = computed<Record<string, unknown>>(
  () => profileToZoneLogicProfile(automationProfile.value) as Record<string, unknown>,
)

function toArray<T>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[]
  if (value && typeof value === 'object') {
    const obj = value as { data?: unknown }
    if (Array.isArray(obj.data)) return obj.data as T[]
  }
  return []
}

async function loadReferenceData() {
  try {
    const [zonesRaw, plantsRaw] = await Promise.all([api.zones.list(), api.plants.list()])
    const zones = toArray<{ id: number; name: string }>(zonesRaw)
    const plants = toArray<{ id: number; name: string }>(plantsRaw)
    const map: Record<number, string> = {}
    for (const zone of zones) map[zone.id] = zone.name
    zoneNameById.value = map
    plantOptions.value = plants.map((p) => ({ id: p.id, name: p.name }))
  } catch (error) {
    showToast((error as Error).message || 'Ошибка загрузки справочников', 'error')
  }

  try {
    const recipesRaw = await api.recipes.list()
    const recipes = toArray<RecipeOption>(recipesRaw)
    recipeOptions.value = recipes.map((recipe) => ({
      id: recipe.id,
      name: recipe.name,
      latest_published_revision_id: recipe.latest_published_revision_id ?? null,
      plants: Array.isArray(recipe.plants) ? recipe.plants : [],
    }))
  } catch (error) {
    showToast((error as Error).message || 'Ошибка загрузки рецептов', 'error')
  }
}

onMounted(loadReferenceData)

function updateField<K extends keyof GrowCycleLaunchPayload>(
  key: K,
  value: GrowCycleLaunchPayload[K] | undefined,
): void {
  if (value === undefined) {
    delete (state as Record<string, unknown>)[key as string]
  } else {
    (state as Record<string, unknown>)[key as string] = value
  }
}

function onZoneSelected(zoneId: number): void {
  if (zoneId > 0) {
    updateField('zone_id', zoneId)
  } else {
    updateField('zone_id', undefined)
  }
}

function onStepSelect(index: number): void {
  const step = stepperSteps.value[index]
  if (!step) return
  // Allow free navigation backward and to next-only-if-current-is-passable.
  if (index <= activeIndex.value) {
    currentStep.value = step.id
    return
  }
  // Forward jump: every step before must be passable.
  for (let i = 0; i < index; i++) {
    if (canProceedStep(stepperSteps.value[i].id) !== true) {
      const reason = canProceedStep(stepperSteps.value[i].id) as { reason?: string }
      showToast(reason?.reason || 'Заполните предыдущие шаги', 'warning')
      return
    }
  }
  currentStep.value = step.id
}

function goNext(): void {
  const i = activeIndex.value
  const next = stepperSteps.value[i + 1]
  if (!next) return
  const verdict = canProceedStep(currentStep.value)
  if (verdict !== true) {
    showToast((verdict as { reason: string }).reason, 'warning')
    return
  }
  currentStep.value = next.id
}

function goBack(): void {
  const i = activeIndex.value
  const prev = stepperSteps.value[i - 1]
  if (prev) currentStep.value = prev.id
}

function openBlockerAction(blocker: LaunchFlowReadinessBlocker): void {
  const name = blocker.action?.route?.name
  if (!name) return
  try {
    const url = route(name, blocker.action?.route?.params ?? {})
    router.visit(url)
  } catch {
    showToast(`Маршрут ${name} не найден`, 'warning')
  }
}

const submitting = ref(false)

async function handleSubmit(): Promise<void> {
  if (submitting.value) return
  const payload = form.toPayload()
  if (!payload) {
    showToast('Форма содержит ошибки — исправьте и повторите', 'error')
    return
  }

  const blockers = manifest.value?.readiness.blockers ?? []
  if (blockers.length > 0) {
    showToast(`Запуск заблокирован: blockers = ${blockers.length}`, 'error')
    return
  }

  submitting.value = true
  try {
    try {
      await api.automationConfigs.update('zone', payload.zone_id, 'zone.logic_profile', {
        payload: profileToZoneLogicProfile(automationProfile.value),
      })
    } catch (error) {
      showToast(
        `Ошибка сохранения zone.logic_profile: ${(error as Error).message || 'неизвестная'}`,
        'error',
      )
      return
    }

    try {
      const bindings = assignmentsToApplyPayload(payload.zone_id, automationProfile.value.assignments)
      await api.setupWizard.applyDeviceBindings(bindings)
    } catch (error) {
      showToast(
        `Ошибка применения привязок узлов: ${(error as Error).message || 'неизвестная'}. ` +
          'logic_profile сохранён — попробуйте «Запустить» ещё раз.',
        'error',
      )
      return
    }

    try {
      await launchMutation.mutateAsync(payload)
      showToast('Цикл запущен', 'success')
      try {
        router.visit(route('zones.show', { zone: payload.zone_id }))
      } catch {
        router.visit(`/zones/${payload.zone_id}`)
      }
    } catch (error) {
      showToast(
        `Ошибка запуска цикла: ${(error as Error).message || 'неизвестная'}. ` +
          'Конфиг и привязки уже сохранены — повторите «Запустить» после устранения причины.',
        'error',
      )
    }
  } finally {
    submitting.value = false
  }
}
</script>
