<template>
    <section class="cal-readiness">
        <div class="cal-readiness__header">
            <div class="cal-readiness__title">
                <span class="cal-readiness__label">готовность калибровки</span>
                <span class="cal-readiness__count">
                    <strong>{{ summary.passed }} из {{ summary.total }}</strong> контрактов закрыто
                </span>
            </div>
            <div class="cal-readiness__tags">
                <button
                    v-for="contract in blockerContracts"
                    :key="contract.id"
                    type="button"
                    class="cal-readiness__tag cal-readiness__tag--blocker"
                    @click="$emit('open-contract', contract)"
                >
                    <span class="cal-readiness__tag-dot" />
                    {{ contract.subsystem }} · {{ contract.component }}
                </button>
                <button
                    type="button"
                    class="cal-readiness__btn cal-readiness__btn--ghost"
                    @click="$emit('open-blockers')"
                >
                    детали блокеров
                </button>
                <button
                    type="button"
                    class="cal-readiness__btn cal-readiness__btn--primary"
                    @click="$emit('open-pump-wizard')"
                >
                    мастер калибровки насосов
                </button>
            </div>
        </div>

        <div class="cal-readiness__bar">
            <span
                v-for="contract in contracts"
                :key="contract.id"
                class="cal-readiness__segment"
                :class="`cal-readiness__segment--${contract.status}`"
                :title="`${contract.title}: ${statusLabel(contract.status)}`"
            />
        </div>
    </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { CalibrationContract, ContractStatus } from '@/composables/useCalibrationContracts';

interface Props {
    contracts: CalibrationContract[];
    summary: { passed: number; total: number; blockers: number };
}

const props = defineProps<Props>();

defineEmits<{
    (e: 'open-blockers'): void;
    (e: 'open-pump-wizard'): void;
    (e: 'open-contract', contract: CalibrationContract): void;
}>();

const blockerContracts = computed(() =>
    props.contracts.filter((c) => c.status === 'blocker'),
);

function statusLabel(status: ContractStatus): string {
    switch (status) {
        case 'passed':
            return 'пройден';
        case 'blocker':
            return 'блокер';
        case 'active':
            return 'активный';
        case 'optional':
            return 'опционально';
        default:
            return '';
    }
}
</script>

<style scoped>
.cal-readiness {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 0.65rem 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 0.5rem;
}

.cal-readiness__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    flex-wrap: wrap;
}

.cal-readiness__title {
    display: flex;
    align-items: baseline;
    gap: 0.55rem;
    flex-wrap: wrap;
}

.cal-readiness__label {
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 700;
    opacity: 0.6;
}

.cal-readiness__count {
    font-size: 0.82rem;
    opacity: 0.85;
}

.cal-readiness__count strong {
    font-weight: 700;
}

.cal-readiness__tags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem;
}

.cal-readiness__tag {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.22rem 0.55rem;
    font-size: 0.72rem;
    font-family: ui-monospace, monospace;
    border-radius: 9999px;
    border: 1px solid transparent;
    cursor: pointer;
    background: transparent;
    color: inherit;
}

.cal-readiness__tag--blocker {
    background: rgba(251, 191, 36, 0.1);
    border-color: rgba(251, 191, 36, 0.4);
    color: rgb(234, 179, 8);
}

.cal-readiness__tag--blocker:hover {
    background: rgba(251, 191, 36, 0.18);
}

.cal-readiness__tag-dot {
    width: 6px;
    height: 6px;
    border-radius: 9999px;
    background: currentColor;
}

.cal-readiness__btn {
    padding: 0.25rem 0.65rem;
    border-radius: 0.3rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 0.72rem;
}

.cal-readiness__btn--ghost:hover {
    background: rgba(148, 163, 184, 0.08);
}

.cal-readiness__btn--primary {
    background: rgb(56, 189, 248);
    border-color: rgb(56, 189, 248);
    color: #0f172a;
    font-weight: 500;
}

.cal-readiness__btn--primary:hover {
    background: rgb(14, 165, 233);
}

.cal-readiness__bar {
    display: flex;
    gap: 3px;
    height: 7px;
}

.cal-readiness__segment {
    flex: 1 1 0;
    border-radius: 2px;
    background: rgba(148, 163, 184, 0.2);
    transition: background 160ms ease;
}

.cal-readiness__segment--passed {
    background: rgb(34, 197, 94);
}

.cal-readiness__segment--blocker {
    background: rgb(251, 191, 36);
}

.cal-readiness__segment--active {
    background: rgb(56, 189, 248);
}

.cal-readiness__segment--optional {
    background: rgba(148, 163, 184, 0.4);
}
</style>
