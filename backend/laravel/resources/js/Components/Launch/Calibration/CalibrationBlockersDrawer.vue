<template>
    <Teleport to="body">
        <transition name="cal-drawer">
            <div v-if="open" class="cal-drawer-overlay" @click.self="$emit('close')">
                <aside class="cal-drawer" role="dialog" aria-modal="true">
                    <header class="cal-drawer__header">
                        <div>
                            <div class="cal-drawer__title">Детали блокеров</div>
                            <div class="cal-drawer__subtitle">
                                {{ blockers.length }} контрактов требуют действия
                            </div>
                        </div>
                        <button type="button" class="cal-drawer__close" @click="$emit('close')">×</button>
                    </header>

                    <div class="cal-drawer__body">
                        <div v-if="blockers.length === 0" class="cal-drawer__empty">
                            Активных блокеров нет — все обязательные контракты закрыты.
                        </div>

                        <ul v-else class="cal-drawer__list">
                            <li v-for="contract in blockers" :key="contract.id" class="cal-drawer__item">
                                <div class="cal-drawer__item-head">
                                    <span class="cal-drawer__item-tag">
                                        {{ contract.subsystem }} · {{ contract.component }}
                                    </span>
                                    <span class="cal-drawer__item-status">блокер</span>
                                </div>
                                <div class="cal-drawer__item-title">{{ contract.title }}</div>
                                <div v-if="contract.description" class="cal-drawer__item-desc">
                                    {{ contract.description }}
                                </div>
                                <button
                                    v-if="contract.action"
                                    type="button"
                                    class="cal-drawer__item-btn"
                                    @click="$emit('navigate', contract)"
                                >
                                    {{ contract.action.label }} →
                                </button>
                            </li>
                        </ul>
                    </div>
                </aside>
            </div>
        </transition>
    </Teleport>
</template>

<script setup lang="ts">
import type { CalibrationContract } from '@/composables/useCalibrationContracts';

interface Props {
    open: boolean;
    blockers: CalibrationContract[];
}

defineProps<Props>();

defineEmits<{
    (e: 'close'): void;
    (e: 'navigate', contract: CalibrationContract): void;
}>();
</script>

<style scoped>
.cal-drawer-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 50;
    display: flex;
    justify-content: flex-end;
}

.cal-drawer {
    width: min(420px, 95vw);
    height: 100vh;
    background: var(--bg-surface, #1e293b);
    border-left: 1px solid rgba(148, 163, 184, 0.25);
    box-shadow: -8px 0 24px rgba(0, 0, 0, 0.25);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.cal-drawer__header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 0.85rem 1rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
}

.cal-drawer__title {
    font-size: 1rem;
    font-weight: 700;
}

.cal-drawer__subtitle {
    font-size: 0.75rem;
    opacity: 0.7;
    margin-top: 0.1rem;
}

.cal-drawer__close {
    background: transparent;
    border: none;
    color: inherit;
    font-size: 1.4rem;
    cursor: pointer;
    line-height: 1;
    padding: 0 0.25rem;
}

.cal-drawer__body {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 0.8rem 1rem;
}

.cal-drawer__empty {
    padding: 1.5rem 0.75rem;
    opacity: 0.6;
    font-size: 0.85rem;
    text-align: center;
}

.cal-drawer__list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
}

.cal-drawer__item {
    padding: 0.7rem 0.8rem;
    border-radius: 0.45rem;
    border: 1px solid rgba(251, 191, 36, 0.3);
    background: rgba(251, 191, 36, 0.05);
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}

.cal-drawer__item-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
}

.cal-drawer__item-tag {
    font-family: ui-monospace, monospace;
    font-size: 0.7rem;
    opacity: 0.75;
}

.cal-drawer__item-status {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 700;
    color: rgb(250, 204, 21);
}

.cal-drawer__item-title {
    font-weight: 600;
    font-size: 0.9rem;
}

.cal-drawer__item-desc {
    font-size: 0.78rem;
    opacity: 0.8;
    line-height: 1.35;
}

.cal-drawer__item-btn {
    align-self: flex-start;
    padding: 0.3rem 0.6rem;
    border-radius: 0.3rem;
    background: rgb(56, 189, 248);
    color: #0f172a;
    border: none;
    font-size: 0.77rem;
    font-weight: 500;
    cursor: pointer;
}

.cal-drawer__item-btn:hover {
    background: rgb(14, 165, 233);
}

.cal-drawer-enter-from,
.cal-drawer-leave-to {
    opacity: 0;
}
.cal-drawer-enter-active,
.cal-drawer-leave-active {
    transition: opacity 200ms ease;
}
.cal-drawer-enter-active .cal-drawer,
.cal-drawer-leave-active .cal-drawer {
    transition: transform 220ms ease;
}
.cal-drawer-enter-from .cal-drawer,
.cal-drawer-leave-to .cal-drawer {
    transform: translateX(100%);
}
</style>
