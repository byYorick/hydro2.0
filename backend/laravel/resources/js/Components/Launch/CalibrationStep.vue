<template>
    <section class="launch-step">
        <header class="launch-step__header">
            <h3 class="launch-step__title">Калибровки и настройки</h3>
            <p class="launch-step__desc">
                Sensor / pump / process calibration, correction config, PID. Слева — подшаги, справа — подробности.
            </p>
        </header>

        <CalibrationHub
            v-if="zoneId"
            :zone-id="zoneId"
            :phase-targets="phaseTargets"
            @updated="onAuthorityUpdated"
        />
        <div v-else class="launch-step__empty">
            Калибровки доступны после выбора зоны.
        </div>
    </section>
</template>

<script setup lang="ts">
import CalibrationHub from '@/Components/Launch/Calibration/CalibrationHub.vue';
import type { LaunchFlowReadinessBlocker } from '@/services/api/launchFlow';
import type { RecipePhasePidTargets } from '@/composables/recipePhasePidTargets';

interface Props {
    blockers?: LaunchFlowReadinessBlocker[];
    warnings?: string[];
    zoneId?: number;
    phaseTargets?: RecipePhasePidTargets | null;
}

withDefaults(defineProps<Props>(), {
    blockers: () => [],
    warnings: () => [],
    zoneId: undefined,
    phaseTargets: null,
});

const emit = defineEmits<{
    (event: 'navigate', blocker: LaunchFlowReadinessBlocker): void;
    (event: 'calibration-updated'): void;
}>();

function onAuthorityUpdated() {
    emit('calibration-updated');
}
</script>

<style scoped>
.launch-step { display: flex; flex-direction: column; gap: 1rem; }
.launch-step__title { font-size: 1rem; font-weight: 600; margin: 0 0 0.25rem; }
.launch-step__desc { margin: 0; opacity: 0.75; font-size: 0.875rem; }
.launch-step__empty {
    padding: 0.75rem;
    background: rgba(251, 191, 36, 0.08);
    border: 1px solid rgba(251, 191, 36, 0.3);
    border-radius: 0.4rem;
    font-size: 0.85rem;
}
</style>
