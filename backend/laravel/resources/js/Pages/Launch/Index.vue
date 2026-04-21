<template>
    <AppLayout>
        <Head title="Запуск цикла" />
        <div class="launch-page">
            <header class="launch-page__header">
                <h1 class="launch-page__title">Запуск цикла выращивания</h1>
                <p v-if="resolvedZoneName" class="launch-page__subtitle">
                    Зона: <strong>{{ resolvedZoneName }}</strong>
                </p>
            </header>

            <div v-if="manifestQuery.isLoading.value" class="launch-page__skeleton">
                Загрузка manifest'а…
            </div>

            <div v-else-if="manifestQuery.isError.value" class="launch-page__error">
                Не удалось загрузить manifest: {{ (manifestQuery.error.value as Error)?.message }}
                <button type="button" @click="() => manifestQuery.refetch()">Повторить</button>
            </div>

            <BaseWizard
                v-else-if="manifest"
                :steps="visibleSteps"
                v-model="currentStep"
                :can-proceed="canProceedStep"
                :submitting="launchMutation.isPending.value"
                title=""
                @submit="handleSubmit"
                @cancel="handleCancel"
            >
                <template #step-zone>
                    <ZoneStep
                        :model-value="state.zone_id"
                        @update:model-value="onZoneSelected"
                    />
                </template>

                <template #step-recipe>
                    <RecipeStep
                        :recipe-revision-id="state.recipe_revision_id"
                        :plant-id="state.plant_id"
                        :planting-at="state.planting_at"
                        :batch-label="state.batch_label"
                        :notes="state.notes"
                        :recipes="recipeOptions"
                        :plants="plantOptions"
                        :errors="errors"
                        @update:recipe-revision-id="updateField('recipe_revision_id', $event)"
                        @update:plant-id="updateField('plant_id', $event)"
                        @update:planting-at="updateField('planting_at', $event)"
                        @update:batch-label="updateField('batch_label', $event)"
                        @update:notes="updateField('notes', $event)"
                        @refresh-plants="loadReferenceData"
                        @refresh-recipes="loadReferenceData"
                    />
                </template>

                <template #step-automation>
                    <AutomationStep
                        :zone-id="state.zone_id"
                        :current-recipe-phase="currentRecipePhase"
                        @update:profile="onAutomationProfileUpdate"
                    />
                </template>

                <template #step-calibration>
                    <CalibrationStep
                        :blockers="manifest.readiness.blockers"
                        :warnings="manifest.readiness.warnings"
                        :zone-id="state.zone_id"
                        :phase-targets="phaseTargetsForPid"
                        @navigate="openBlockerAction"
                        @calibration-updated="onCalibrationUpdated"
                    />
                </template>

                <template #step-preview>
                    <PreviewStep
                        :payload-preview="state"
                        :errors="errorList"
                        :recipe-phases="recipePhases"
                    >
                        <template #diff-preview>
                            <DiffPreview
                                :current="currentLogicProfile"
                                :next="mergedLogicProfile"
                            />
                        </template>
                    </PreviewStep>
                </template>
            </BaseWizard>
        </div>
    </AppLayout>
</template>

<script setup lang="ts">
import { Head, router } from '@inertiajs/vue3';
import { computed, onMounted, ref, watch } from 'vue';
import AppLayout from '@/Layouts/AppLayout.vue';
import BaseWizard from '@/Components/Shared/BaseWizard/BaseWizard.vue';
import ZoneStep from '@/Components/Launch/ZoneStep.vue';
import RecipeStep from '@/Components/Launch/RecipeStep.vue';
import AutomationStep from '@/Components/Launch/AutomationStep.vue';
import CalibrationStep from '@/Components/Launch/CalibrationStep.vue';
import PreviewStep from '@/Components/Launch/PreviewStep.vue';
import DiffPreview from '@/Components/Launch/DiffPreview.vue';
import { useFormSchema } from '@/composables/useFormSchema';
import { growCycleLaunchSchema, type GrowCycleLaunchPayload } from '@/schemas/growCycleLaunch';
import {
    automationProfileDefaults,
    type AutomationProfile,
} from '@/schemas/automationProfile';
import {
    assignmentsToApplyPayload,
    profileToZoneLogicProfile,
} from '@/composables/automationProfileConverters';
import { resolveRecipePhasePidTargets } from '@/composables/recipePhasePidTargets';
import { useQueryClient } from '@tanstack/vue-query';
import { launchFlowKeys } from '@/services/queries/launchFlow';
import { useLaunchGrowCycleMutation, useLaunchManifest } from '@/services/queries/launchFlow';
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow';
import { api } from '@/services/api';
import { useToast } from '@/composables/useToast';

interface Props {
    zoneId: number | null;
    auth: { user: { role: string } };
}

const props = defineProps<Props>();

const { showToast } = useToast();

const form = useFormSchema<GrowCycleLaunchPayload>(growCycleLaunchSchema, {
    zone_id: props.zoneId ?? undefined,
    overrides: {},
    bindings: {},
} as Partial<GrowCycleLaunchPayload>);

const state = form.state;
const errors = form.errors;

const zoneIdRef = computed<number | null>(() => state.zone_id ?? null);
const manifestQuery = useLaunchManifest(zoneIdRef);
const launchMutation = useLaunchGrowCycleMutation();

const manifest = computed(() => manifestQuery.data.value ?? null);

const currentStep = ref<string>('');
const visibleSteps = computed(() => (manifest.value?.steps ?? []).filter((step) => step.visible));

watch(
    () => visibleSteps.value.map((step) => step.id).join('|'),
    (joined) => {
        if (!joined) return;
        const firstVisible = visibleSteps.value[0]?.id ?? '';
        if (!currentStep.value || !visibleSteps.value.some((step) => step.id === currentStep.value)) {
            currentStep.value = firstVisible;
        }
    },
    { immediate: true },
);

interface RecipeOption {
    id: number;
    name: string;
    latest_published_revision_id?: number | null;
    plants?: Array<{ id: number; name: string }>;
}
const recipeOptions = ref<RecipeOption[]>([]);
const plantOptions = ref<Array<{ id: number; name: string }>>([]);
const zoneNameById = ref<Record<number, string>>({});

const automationProfile = ref<AutomationProfile>(
    structuredClone(automationProfileDefaults),
);

function onAutomationProfileUpdate(next: AutomationProfile) {
    automationProfile.value = next;
}

const phaseTargetsForPid = computed(() =>
    resolveRecipePhasePidTargets(currentRecipePhase.value ?? null),
);

const queryClient = useQueryClient();

async function onCalibrationUpdated() {
    const zoneId = state.zone_id ?? null;
    await queryClient.invalidateQueries({ queryKey: launchFlowKeys.manifest(zoneId) });
}

const revisionPhasesCache = ref<Record<number, unknown[]>>({});
const currentRecipePhase = ref<unknown>(null);
const recipePhases = ref<unknown[]>([]);

async function loadRecipeRevisionPhases(revisionId: number) {
    if (revisionPhasesCache.value[revisionId]) {
        const cached = revisionPhasesCache.value[revisionId];
        currentRecipePhase.value = cached[0] ?? null;
        recipePhases.value = cached;
        return;
    }
    try {
        const rev = await api.recipes.getRevision(revisionId);
        const phases = Array.isArray((rev as { phases?: unknown[] })?.phases)
            ? ((rev as { phases: unknown[] }).phases as unknown[])
            : [];
        revisionPhasesCache.value = { ...revisionPhasesCache.value, [revisionId]: phases };
        currentRecipePhase.value = phases[0] ?? null;
        recipePhases.value = phases;
    } catch {
        currentRecipePhase.value = null;
        recipePhases.value = [];
    }
}

watch(
    () => state.recipe_revision_id,
    (revId) => {
        if (!revId) {
            currentRecipePhase.value = null;
            return;
        }
        loadRecipeRevisionPhases(revId);
    },
    { immediate: true },
);

const resolvedZoneName = computed(() => {
    const id = state.zone_id;
    if (!id) return null;
    return zoneNameById.value[id] ?? null;
});

const errorList = computed(() =>
    Object.entries(errors.value).map(([path, message]) => ({ path, message })),
);

const currentLogicProfile = ref<Record<string, unknown>>({});

async function loadLogicProfile(zoneId: number) {
    try {
        const profile = await api.automationConfigs.get('zone', zoneId, 'zone.logic_profile');
        const payload = (profile as unknown as { payload?: Record<string, unknown> }).payload ?? {};
        currentLogicProfile.value = payload;
    } catch {
        currentLogicProfile.value = {};
    }
}

watch(
    () => state.zone_id,
    (id) => {
        if (typeof id === 'number') loadLogicProfile(id);
    },
    { immediate: true },
);

const mergedLogicProfile = computed<Record<string, unknown>>(() =>
    profileToZoneLogicProfile(automationProfile.value) as Record<string, unknown>,
);

function toArray<T>(value: unknown): T[] {
    if (Array.isArray(value)) return value as T[];
    if (value && typeof value === 'object') {
        const obj = value as { data?: unknown };
        if (Array.isArray(obj.data)) return obj.data as T[];
    }
    return [];
}

async function loadReferenceData() {
    try {
        const [zonesRaw, plantsRaw] = await Promise.all([api.zones.list(), api.plants.list()]);
        const zones = toArray<{ id: number; name: string }>(zonesRaw);
        const plants = toArray<{ id: number; name: string }>(plantsRaw);
        const map: Record<number, string> = {};
        for (const zone of zones) {
            map[zone.id] = zone.name;
        }
        zoneNameById.value = map;
        plantOptions.value = plants.map((plant) => ({ id: plant.id, name: plant.name }));
    } catch (error) {
        showToast((error as Error).message || 'Ошибка загрузки справочников', 'error');
    }

    try {
        const recipesRaw = await api.recipes.list();
        const recipes = toArray<RecipeOption>(recipesRaw);
        recipeOptions.value = recipes.map((recipe) => ({
            id: recipe.id,
            name: recipe.name,
            latest_published_revision_id: recipe.latest_published_revision_id ?? null,
            plants: Array.isArray(recipe.plants) ? recipe.plants : [],
        }));
    } catch (error) {
        showToast((error as Error).message || 'Ошибка загрузки рецептов', 'error');
    }
}

onMounted(loadReferenceData);

function canProceedStep(stepId: string): boolean | { ok: false; reason: string } {
    if (stepId === 'zone') {
        return state.zone_id != null ? true : { ok: false, reason: 'Выберите зону' };
    }
    if (stepId === 'recipe') {
        if (!state.recipe_revision_id) return { ok: false, reason: 'Выберите ревизию рецепта' };
        if (!state.plant_id) return { ok: false, reason: 'Выберите растение' };
        if (!state.planting_at) return { ok: false, reason: 'Укажите дату посадки' };
        return true;
    }
    if (stepId === 'automation') {
        const a = automationProfile.value.assignments;
        if (!a.irrigation) return { ok: false, reason: 'Не привязан irrigation канал' };
        if (!a.ph_correction) return { ok: false, reason: 'Не привязан pH-корректор' };
        if (!a.ec_correction) return { ok: false, reason: 'Не привязан EC-корректор' };
        if (automationProfile.value.lightingForm.enabled && !a.light) {
            return { ok: false, reason: 'Свет включён — нужна привязка светового канала' };
        }
        if (automationProfile.value.zoneClimateForm.enabled) {
            const hasClimateBinding =
                a.co2_sensor || a.co2_actuator || a.root_vent_actuator;
            if (!hasClimateBinding) {
                return { ok: false, reason: 'Climate включён — нужна привязка CO₂/вентиляции' };
            }
        }
        return true;
    }
    if (stepId === 'calibration') {
        const blockers = manifest.value?.readiness.blockers ?? [];
        return blockers.length === 0
            ? true
            : { ok: false, reason: `Осталось ${blockers.length} blocker(ов)` };
    }
    if (stepId === 'preview') {
        if (!form.isValid.value) return { ok: false, reason: 'Payload не валиден' };
        const blockers = manifest.value?.readiness.blockers ?? [];
        if (blockers.length > 0) {
            return { ok: false, reason: `Readiness blockers: ${blockers.length} — запуск заблокирован` };
        }
        return true;
    }
    return true;
}

function updateField<K extends keyof GrowCycleLaunchPayload>(
    key: K,
    value: GrowCycleLaunchPayload[K] | undefined,
) {
    if (value === undefined) {
        delete (state as Record<string, unknown>)[key as string];
    } else {
        (state as Record<string, unknown>)[key as string] = value;
    }
}

function onZoneSelected(zoneId: number) {
    if (zoneId > 0) {
        updateField('zone_id', zoneId);
    } else {
        updateField('zone_id', undefined);
    }
}

function openBlockerAction(blocker: LaunchFlowReadinessBlocker) {
    if (!blocker.action?.route?.name) return;
    try {
        const url = route(blocker.action.route.name, blocker.action.route.params ?? {});
        router.visit(url);
    } catch {
        showToast(`Маршрут ${blocker.action.route.name} не найден`, 'warning');
    }
}

async function handleSubmit() {
    const payload = form.toPayload();
    if (!payload) {
        showToast('Форма содержит ошибки — исправьте и повторите', 'error');
        return;
    }

    const blockers = manifest.value?.readiness.blockers ?? [];
    if (blockers.length > 0) {
        showToast(`Запуск заблокирован: blockers = ${blockers.length}`, 'error');
        return;
    }

    try {
        await api.automationConfigs.update('zone', payload.zone_id, 'zone.logic_profile', {
            payload: profileToZoneLogicProfile(automationProfile.value),
        });
    } catch (error) {
        showToast((error as Error).message || 'Ошибка сохранения zone.logic_profile', 'error');
        return;
    }

    try {
        const bindings = assignmentsToApplyPayload(payload.zone_id, automationProfile.value.assignments);
        await api.setupWizard.applyDeviceBindings(bindings);
    } catch (error) {
        showToast((error as Error).message || 'Ошибка применения привязок узлов', 'error');
        return;
    }

    try {
        await launchMutation.mutateAsync(payload);
        showToast('Цикл запущен', 'success');
        router.visit(route('zones.show', { zone: payload.zone_id }));
    } catch (error) {
        showToast((error as Error).message || 'Ошибка запуска цикла', 'error');
    }
}

function handleCancel() {
    if (state.zone_id) {
        router.visit(route('zones.show', { zone: state.zone_id }));
    } else {
        router.visit('/');
    }
}

declare function route(name: string, params?: Record<string, unknown>): string;
</script>

<style scoped>
.launch-page {
    max-width: 960px;
    margin: 0 auto;
    padding: 1.5rem;
}

.launch-page__header {
    margin-bottom: 1.5rem;
}

.launch-page__title {
    font-size: 1.5rem;
    font-weight: 600;
    margin: 0 0 0.25rem;
}

.launch-page__subtitle {
    margin: 0;
    opacity: 0.75;
    font-size: 0.875rem;
}

.launch-page__skeleton,
.launch-page__error {
    padding: 1rem;
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 0.5rem;
    background: rgba(148, 163, 184, 0.06);
    font-size: 0.875rem;
}

.launch-page__error {
    background: rgba(239, 68, 68, 0.08);
    border-color: rgba(239, 68, 68, 0.35);
}

.launch-page__error button {
    margin-left: 0.5rem;
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    border: 1px solid rgba(239, 68, 68, 0.5);
    background: rgba(239, 68, 68, 0.12);
    color: inherit;
    cursor: pointer;
}
</style>
