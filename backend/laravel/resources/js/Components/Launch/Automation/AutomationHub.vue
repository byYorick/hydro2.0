<template>
    <div class="auto-hub">
        <AutomationReadinessBar
            :contracts="contracts"
            :summary="summary"
            @open-blockers="blockersOpen = true"
            @open-contract="onContractClick"
            @refresh="$emit('refresh')"
        />

        <div class="auto-hub__grid">
            <aside class="auto-hub__sidebar">
                <div class="auto-hub__section">
                    <div class="auto-hub__section-label">Инфраструктура</div>
                    <CalibrationSidebarItem
                        title="Привязки узлов"
                        subtitle="полив · pH · EC"
                        :state="navStates.bindings.state"
                        :count="navStates.bindings.count"
                        :active="currentSub === 'bindings'"
                        :index="1"
                        @click="currentSub = 'bindings'"
                    />
                    <CalibrationSidebarItem
                        title="Водный контур"
                        :subtitle="systemTypeLocked ? `${topologyLabel} · ${tanksCount} бак(ов)` : 'нужна топология из рецепта'"
                        :state="navStates.contour.state"
                        :count="navStates.contour.count"
                        :active="currentSub === 'contour'"
                        :index="2"
                        @click="currentSub = 'contour'"
                    />
                </div>

                <div class="auto-hub__section">
                    <div class="auto-hub__section-label">Подсистемы</div>
                    <CalibrationSidebarItem
                        title="Полив"
                        :subtitle="irrigationSubtitle"
                        :state="navStates.irrigation.state"
                        :count="navStates.irrigation.count"
                        :active="currentSub === 'irrigation'"
                        :index="3"
                        @click="currentSub = 'irrigation'"
                    />
                    <CalibrationSidebarItem
                        title="Коррекция pH/EC"
                        :subtitle="correctionSubtitle"
                        :state="navStates.correction.state"
                        :count="navStates.correction.count"
                        :active="currentSub === 'correction'"
                        :index="4"
                        @click="currentSub = 'correction'"
                    />
                </div>

                <div class="auto-hub__section">
                    <div class="auto-hub__section-label">Опциональные</div>
                    <CalibrationSidebarItem
                        title="Свет"
                        :subtitle="lighting.enabled ? 'включён · расписание' : 'выключен'"
                        :state="navStates.lighting.state"
                        :count="lighting.enabled ? navStates.lighting.count : 'выкл'"
                        :active="currentSub === 'lighting'"
                        :index="5"
                        @click="currentSub = 'lighting'"
                    />
                    <CalibrationSidebarItem
                        title="Климат"
                        :subtitle="climate.enabled ? 'включён · CO₂ / вентиляция' : 'выключен'"
                        :state="navStates.climate.state"
                        :count="climate.enabled ? navStates.climate.count : 'выкл'"
                        :active="currentSub === 'climate'"
                        :index="6"
                        @click="currentSub = 'climate'"
                    />
                </div>
            </aside>

            <main class="auto-hub__main">
                <div class="auto-hub__subpage-head">
                    <div class="auto-hub__subpage-breadcrumb">
                        / зона / автоматика / {{ currentSub }}
                    </div>
                    <h3 class="auto-hub__subpage-title">{{ currentSubMeta.title }}</h3>
                    <p class="auto-hub__subpage-desc">{{ currentSubMeta.desc }}</p>
                </div>

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

                <div v-if="currentSub === 'correction'" class="auto-hub__note">
                    💡 Полный стек калибровки (насосы / процесс / PID / автонастройка) — в следующем шаге
                    <strong>«Калибровки и настройки»</strong>. Здесь только целевые значения и конфигурация коррекции.
                </div>

                <div class="auto-hub__subpage-footer">
                    <a
                        class="auto-hub__link"
                        :href="`/zones/${zoneId}/edit`"
                        target="_blank"
                        rel="noopener"
                    >
                        Открыть полную инфраструктуру зоны ↗
                    </a>
                    <button
                        type="button"
                        class="auto-hub__btn auto-hub__btn--ghost"
                        :disabled="refreshingNodes"
                        @click="$emit('refresh-nodes')"
                    >
                        {{ refreshingNodes ? '↻ Обновление…' : '↻ Обновить список нод' }}
                    </button>
                    <button
                        type="button"
                        class="auto-hub__btn auto-hub__btn--ghost"
                        @click="$emit('refresh')"
                    >
                        ↻ Перечитать всё
                    </button>
                </div>
            </main>
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
import { computed, ref } from 'vue';
import PresetSelector from '@/Components/AutomationForms/PresetSelector.vue';
import ZoneAutomationProfileSections from '@/Components/ZoneAutomationProfileSections.vue';
import AutomationReadinessBar from '@/Components/Launch/Automation/AutomationReadinessBar.vue';
import AutomationBlockersDrawer from '@/Components/Launch/Automation/AutomationBlockersDrawer.vue';
import CalibrationSidebarItem, {
    type NavState,
} from '@/Components/Launch/Calibration/CalibrationSidebarItem.vue';
import {
    useAutomationContracts,
    type AutomationContract,
} from '@/composables/useAutomationContracts';
import type { AutomationProfile } from '@/schemas/automationProfile';
import type {
    LightingFormState,
    WaterFormState,
    ZoneAutomationSectionAssignments,
    ZoneClimateFormState,
} from '@/composables/zoneAutomationTypes';
import type { Node as SetupWizardNode } from '@/types/SetupWizard';

type SubKey =
    | 'bindings'
    | 'contour'
    | 'irrigation'
    | 'correction'
    | 'lighting'
    | 'climate';

interface Props {
    zoneId: number;
    profile: AutomationProfile;
    currentRecipePhase?: unknown;
    systemTypeLocked: boolean;
    availableNodes: SetupWizardNode[];
    refreshingNodes?: boolean;
    bindingInProgress?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
    currentRecipePhase: null,
    refreshingNodes: false,
    bindingInProgress: false,
});

const emit = defineEmits<{
    (e: 'update:water-form', v: WaterFormState): void;
    (e: 'update:lighting-form', v: LightingFormState): void;
    (e: 'update:zone-climate-form', v: ZoneClimateFormState): void;
    (e: 'update:assignments', v: ZoneAutomationSectionAssignments): void;
    (e: 'bind-devices', roles: string[]): void;
    (e: 'refresh-nodes'): void;
    (e: 'refresh'): void;
    (e: 'preset-applied', preset: unknown): void;
    (e: 'preset-cleared'): void;
}>();

const currentSub = ref<SubKey>('bindings');
const blockersOpen = ref(false);

const profileRef = computed(() => props.profile);
const systemTypeLockedRef = computed(() => props.systemTypeLocked);

const { contracts, summary, blockers } = useAutomationContracts({
    profile: profileRef,
    systemTypeLocked: systemTypeLockedRef,
});

// ── Derived labels for sidebar ────────────────────────────────
const topologyLabel = computed(() => {
    const t = props.profile.waterForm.systemType;
    return t === 'drip' ? 'Капельный' : t === 'nft' ? 'NFT' : 'Субстрат';
});
const tanksCount = computed(() => props.profile.waterForm.tanksCount);

const irrigationSubtitle = computed(() => {
    const w = props.profile.waterForm;
    const mode = w.irrigationDecisionStrategy === 'smart_soil_v1' ? 'SMART' : 'По времени';
    return `${mode} · ${w.intervalMinutes} мин / ${w.durationSeconds} с`;
});

const correctionSubtitle = computed(() => {
    const w = props.profile.waterForm;
    return `pH ${w.targetPh} · EC ${w.targetEc}`;
});

const lighting = computed(() => props.profile.lightingForm);
const climate = computed(() => props.profile.zoneClimateForm);

// ── Nav states from contracts ─────────────────────────────────
const navStates = computed(() => {
    const bySubsystem = (sub: string) =>
        contracts.value.filter((c) => c.subsystem === sub);

    const aggregate = (sub: string): { state: NavState; count: string } => {
        const items = bySubsystem(sub);
        if (items.length === 0) return { state: 'optional', count: '—' };
        const optional = items.every((c) => c.status === 'optional');
        if (optional) return { state: 'optional', count: 'опц.' };
        const blocked = items.some((c) => c.status === 'blocker');
        const passed = items.filter((c) => c.status === 'passed').length;
        const required = items.filter((c) => c.required).length;
        const state: NavState = blocked ? 'blocker' : passed === required && required > 0 ? 'passed' : 'active';
        return { state, count: `${passed}/${required}` };
    };

    return {
        bindings: aggregate('bindings'),
        contour: aggregate('contour'),
        irrigation: aggregate('irrigation'),
        correction: aggregate('correction'),
        lighting: aggregate('lighting'),
        climate: aggregate('climate'),
    };
});

const SUB_META: Record<SubKey, { title: string; desc: string }> = {
    bindings: {
        title: 'Привязки узлов',
        desc: 'Обязательные роли (полив / pH / EC) и опциональные (свет, влажность почвы, CO₂, вентиляция).',
    },
    contour: {
        title: 'Водный контур',
        desc: 'Топология из рецепта, баки, насосы, таймауты.',
    },
    irrigation: {
        title: 'Полив',
        desc: 'Интервал, длительность, стратегия (по времени или SMART).',
    },
    correction: {
        title: 'Коррекция pH/EC',
        desc: 'Целевые значения, допуски, стек калибровок контура коррекции.',
    },
    lighting: {
        title: 'Свет',
        desc: 'Вкл/выкл, освещённость день/ночь, начало и конец расписания.',
    },
    climate: {
        title: 'Климат зоны',
        desc: 'Сенсор/исполнитель CO₂, корневая вентиляция — если включено.',
    },
};

const currentSubMeta = computed(() => SUB_META[currentSub.value]);

function onContractClick(contract: AutomationContract) {
    const target = contract.action?.target;
    if (!target) return;
    if (
        target === 'bindings' ||
        target === 'contour' ||
        target === 'irrigation' ||
        target === 'correction' ||
        target === 'lighting' ||
        target === 'climate'
    ) {
        currentSub.value = target as SubKey;
    }
}

function onBlockerNavigate(contract: AutomationContract) {
    onContractClick(contract);
    blockersOpen.value = false;
}

function onWaterFormUpdate(v: WaterFormState) {
    emit('update:water-form', v);
}
function onLightingFormUpdate(v: LightingFormState) {
    emit('update:lighting-form', v);
}
function onZoneClimateFormUpdate(v: ZoneClimateFormState) {
    emit('update:zone-climate-form', v);
}
function onAssignmentsUpdate(v: ZoneAutomationSectionAssignments) {
    emit('update:assignments', v);
}
</script>

<style scoped>
.auto-hub {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.auto-hub__grid {
    display: grid;
    grid-template-columns: minmax(220px, 260px) 1fr;
    gap: 0.85rem;
    align-items: start;
}

.auto-hub__sidebar {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
    padding: 0.65rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.5rem;
}

.auto-hub__section {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
}

.auto-hub__section-label {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 700;
    opacity: 0.55;
    padding: 0 0.4rem 0.25rem;
}

.auto-hub__main {
    padding: 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 0.5rem;
    min-height: 260px;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.auto-hub__subpage-head {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
}

.auto-hub__subpage-breadcrumb {
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
    opacity: 0.55;
}

.auto-hub__subpage-title {
    font-size: 1rem;
    font-weight: 700;
    margin: 0;
}

.auto-hub__subpage-desc {
    font-size: 0.78rem;
    opacity: 0.7;
    margin: 0;
}

.auto-hub__subpage-footer {
    display: flex;
    gap: 0.4rem;
    flex-wrap: wrap;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(148, 163, 184, 0.12);
}

.auto-hub__link {
    padding: 0.3rem 0.7rem;
    border-radius: 0.3rem;
    border: 1px dashed rgba(56, 189, 248, 0.4);
    color: rgb(125, 211, 252);
    font-size: 0.75rem;
    text-decoration: none;
}
.auto-hub__link:hover {
    background: rgba(56, 189, 248, 0.06);
}

.auto-hub__btn {
    padding: 0.3rem 0.7rem;
    border-radius: 0.3rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.75rem;
}

.auto-hub__btn:disabled { cursor: not-allowed; opacity: 0.55; }
.auto-hub__btn--ghost:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.08);
}

.auto-hub__note {
    padding: 0.55rem 0.85rem;
    border-radius: 0.35rem;
    background: rgba(56, 189, 248, 0.06);
    border: 1px solid rgba(56, 189, 248, 0.25);
    color: rgb(125, 211, 252);
    font-size: 0.78rem;
    line-height: 1.4;
}
.auto-hub__note strong {
    color: rgb(186, 230, 253);
}

@media (max-width: 820px) {
    .auto-hub__grid {
        grid-template-columns: 1fr;
    }
}
</style>
