<template>
    <button
        type="button"
        class="cal-nav-item"
        :class="{
            'cal-nav-item--active': active,
            'cal-nav-item--passed': state === 'passed',
            'cal-nav-item--blocker': state === 'blocker',
            'cal-nav-item--waiting': state === 'waiting',
            'cal-nav-item--optional': state === 'optional',
        }"
        @click="$emit('click')"
    >
        <span class="cal-nav-item__icon" :aria-label="iconLabel">{{ iconGlyph }}</span>
        <span class="cal-nav-item__body">
            <span class="cal-nav-item__title">{{ title }}</span>
            <span v-if="subtitle" class="cal-nav-item__subtitle">{{ subtitle }}</span>
        </span>
        <span v-if="count" class="cal-nav-item__count">{{ count }}</span>
        <span v-else-if="waitingLabel" class="cal-nav-item__waiting">{{ waitingLabel }}</span>
    </button>
</template>

<script setup lang="ts">
import { computed } from 'vue';

export type NavState = 'passed' | 'active' | 'blocker' | 'waiting' | 'optional';

interface Props {
    title: string;
    subtitle?: string;
    count?: string;
    state: NavState;
    active?: boolean;
    index?: number;
    waitingLabel?: string;
}

const props = withDefaults(defineProps<Props>(), {
    subtitle: '',
    count: '',
    active: false,
    index: 0,
    waitingLabel: '',
});

defineEmits<{ (e: 'click'): void }>();

const iconGlyph = computed(() => {
    if (props.active) return String(props.index || '•');
    switch (props.state) {
        case 'passed':
            return '✓';
        case 'blocker':
            return '!';
        case 'waiting':
            return '…';
        case 'optional':
            return '○';
        default:
            return '•';
    }
});

const iconLabel = computed(() => {
    switch (props.state) {
        case 'passed':
            return 'пройден';
        case 'blocker':
            return 'блокер';
        case 'waiting':
            return 'ждёт';
        case 'optional':
            return 'опционально';
        default:
            return 'активный';
    }
});
</script>

<style scoped>
.cal-nav-item {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
    width: 100%;
    padding: 0.55rem 0.6rem;
    border-radius: 0.45rem;
    border: 1px solid transparent;
    background: transparent;
    color: inherit;
    cursor: pointer;
    text-align: left;
    font-size: 0.82rem;
    transition: border-color 140ms ease, background 140ms ease;
}

.cal-nav-item:hover {
    background: rgba(148, 163, 184, 0.06);
}

.cal-nav-item--active {
    border-color: rgba(56, 189, 248, 0.55);
    background: rgba(56, 189, 248, 0.08);
}

.cal-nav-item__icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 22px;
    height: 22px;
    border-radius: 0.35rem;
    font-weight: 700;
    font-size: 0.72rem;
    flex-shrink: 0;
    background: rgba(148, 163, 184, 0.15);
}

.cal-nav-item--passed .cal-nav-item__icon {
    background: rgba(34, 197, 94, 0.2);
    color: rgb(134, 239, 172);
}

.cal-nav-item--blocker .cal-nav-item__icon {
    background: rgba(251, 191, 36, 0.22);
    color: rgb(250, 204, 21);
}

.cal-nav-item--active .cal-nav-item__icon {
    background: rgb(56, 189, 248);
    color: #0f172a;
}

.cal-nav-item--waiting .cal-nav-item__icon,
.cal-nav-item--optional .cal-nav-item__icon {
    background: rgba(148, 163, 184, 0.12);
    color: rgba(148, 163, 184, 0.85);
}

.cal-nav-item__body {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    flex: 1 1 auto;
    min-width: 0;
}

.cal-nav-item__title {
    font-weight: 600;
    line-height: 1.2;
}

.cal-nav-item__subtitle {
    font-size: 0.7rem;
    opacity: 0.6;
    line-height: 1.25;
}

.cal-nav-item__count {
    padding: 0.05rem 0.35rem;
    border-radius: 9999px;
    background: rgba(148, 163, 184, 0.15);
    font-size: 0.7rem;
    font-weight: 600;
    flex-shrink: 0;
}

.cal-nav-item--active .cal-nav-item__count {
    background: rgba(56, 189, 248, 0.25);
    color: rgb(125, 211, 252);
}

.cal-nav-item__waiting {
    padding: 0.05rem 0.35rem;
    border-radius: 0.25rem;
    background: rgba(251, 191, 36, 0.12);
    color: rgb(250, 204, 21);
    font-size: 0.65rem;
    flex-shrink: 0;
    white-space: nowrap;
}
</style>
