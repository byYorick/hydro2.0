<template>
  <div
    class="base-wizard"
    :class="{ 'base-wizard--dark': darkMode }"
  >
    <header class="base-wizard__header">
      <slot name="header">
        <h2
          v-if="title"
          class="base-wizard__title"
        >
          {{ title }}
        </h2>
      </slot>
      <slot
        name="progress"
        :visible-steps="visibleSteps"
        :current-index="currentIndex"
      >
        <ol
          class="base-wizard__progress"
          :aria-label="'Шаги мастера'"
        >
          <li
            v-for="(step, index) in visibleSteps"
            :key="step.id"
            class="base-wizard__progress-item"
            :class="{
              'is-active': step.id === modelValue,
              'is-done': index < currentIndex,
              'is-pending': index > currentIndex,
            }"
          >
            <button
              type="button"
              class="base-wizard__progress-btn"
              :aria-current="step.id === modelValue ? 'step' : undefined"
              :disabled="!stepIsReachable(step.id, index)"
              @click="jumpTo(step.id)"
            >
              <span class="base-wizard__progress-idx">{{ index + 1 }}</span>
              <span class="base-wizard__progress-title">{{ step.title }}</span>
            </button>
          </li>
        </ol>
      </slot>
    </header>

    <section
      class="base-wizard__content"
      role="group"
      :aria-labelledby="`wizard-step-${activeStep?.id}`"
    >
      <slot
        :name="`step-${activeStep?.id ?? 'unknown'}`"
        :step="activeStep"
      ></slot>
    </section>

    <footer class="base-wizard__footer">
      <slot
        name="navigation"
        v-bind="navigationState"
      >
        <div class="base-wizard__nav">
          <button
            type="button"
            class="base-wizard__btn base-wizard__btn--secondary"
            :disabled="isFirst"
            @click="goBack"
          >
            {{ backLabel }}
          </button>
          <button
            v-if="!isLast"
            type="button"
            class="base-wizard__btn base-wizard__btn--primary"
            :disabled="!forwardAllowed"
            :title="forwardBlockedReason"
            @click="goForward"
          >
            {{ nextLabel }}
          </button>
          <button
            v-else
            type="button"
            class="base-wizard__btn base-wizard__btn--primary"
            :disabled="!forwardAllowed || submitting"
            :title="forwardBlockedReason"
            @click="submit"
          >
            {{ submitting ? submittingLabel : submitLabel }}
          </button>
          <button
            type="button"
            class="base-wizard__btn base-wizard__btn--ghost"
            @click="cancel"
          >
            {{ cancelLabel }}
          </button>
        </div>
      </slot>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue';
import type { CanProceedFn, WizardNavigationState, WizardStep } from './types';

interface Props {
    steps: WizardStep[];
    modelValue: string;
    canProceed?: CanProceedFn;
    title?: string;
    submitting?: boolean;
    backLabel?: string;
    nextLabel?: string;
    submitLabel?: string;
    submittingLabel?: string;
    cancelLabel?: string;
    darkMode?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
    canProceed: () => true,
    title: '',
    submitting: false,
    backLabel: 'Назад',
    nextLabel: 'Далее',
    submitLabel: 'Готово',
    submittingLabel: 'Отправка…',
    cancelLabel: 'Отмена',
    darkMode: true,
});

const emit = defineEmits<{
    (event: 'update:modelValue', step: string): void;
    (event: 'submit'): void;
    (event: 'cancel'): void;
    (event: 'navigate', from: string, to: string): void;
}>();

const visibleSteps = computed<WizardStep[]>(() =>
    props.steps.filter((step) => step.visible !== false),
);

const currentIndex = computed(() => {
    const idx = visibleSteps.value.findIndex((step) => step.id === props.modelValue);
    return idx < 0 ? 0 : idx;
});

const activeStep = computed<WizardStep | undefined>(() => visibleSteps.value[currentIndex.value]);

const isFirst = computed(() => currentIndex.value === 0);
const isLast = computed(() => currentIndex.value === visibleSteps.value.length - 1);

const proceedResult = computed(() => {
    if (!activeStep.value) return { ok: true } as const;
    const outcome = props.canProceed(activeStep.value.id);
    if (typeof outcome === 'boolean') {
        return outcome ? ({ ok: true } as const) : ({ ok: false, reason: '' } as const);
    }
    return outcome;
});

const forwardAllowed = computed(() => proceedResult.value.ok);
const forwardBlockedReason = computed(() =>
    !proceedResult.value.ok && 'reason' in proceedResult.value ? proceedResult.value.reason : undefined,
);

const navigationState = computed<WizardNavigationState>(() => ({
    currentStep: props.modelValue,
    currentIndex: currentIndex.value,
    total: visibleSteps.value.length,
    visibleSteps: visibleSteps.value,
    canGoBack: !isFirst.value,
    canGoForward: forwardAllowed.value,
    isFirst: isFirst.value,
    isLast: isLast.value,
}));

watch(
    () => visibleSteps.value.map((step) => step.id).join('|'),
    (joined) => {
        if (!joined) return;
        if (!visibleSteps.value.some((step) => step.id === props.modelValue)) {
            emit('update:modelValue', visibleSteps.value[0]?.id ?? '');
        }
    },
    { immediate: true },
);

function stepIsReachable(stepId: string, index: number): boolean {
    return index <= currentIndex.value;
}

function goBack(): void {
    if (isFirst.value) return;
    const prev = visibleSteps.value[currentIndex.value - 1];
    if (!prev) return;
    emit('navigate', props.modelValue, prev.id);
    emit('update:modelValue', prev.id);
}

function goForward(): void {
    if (!forwardAllowed.value || isLast.value) return;
    const next = visibleSteps.value[currentIndex.value + 1];
    if (!next) return;
    emit('navigate', props.modelValue, next.id);
    emit('update:modelValue', next.id);
}

function jumpTo(stepId: string): void {
    if (stepId === props.modelValue) return;
    const targetIndex = visibleSteps.value.findIndex((step) => step.id === stepId);
    if (targetIndex < 0) return;
    if (targetIndex > currentIndex.value) return;
    emit('navigate', props.modelValue, stepId);
    emit('update:modelValue', stepId);
}

function submit(): void {
    if (!forwardAllowed.value) return;
    emit('submit');
}

function cancel(): void {
    emit('cancel');
}
</script>

<style scoped>
.base-wizard {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
}

.base-wizard__title {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0 0 0.5rem;
}

.base-wizard__progress {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    list-style: none;
    padding: 0;
    margin: 0;
}

.base-wizard__progress-item {
    flex: 1 1 140px;
    min-width: 120px;
}

.base-wizard__progress-btn {
    width: 100%;
    text-align: left;
    background: transparent;
    border: 1px solid rgba(148, 163, 184, 0.35);
    padding: 0.6rem 0.75rem;
    border-radius: 0.5rem;
    color: inherit;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    transition: background 160ms ease, border-color 160ms ease;
}

.base-wizard__progress-btn:disabled {
    cursor: not-allowed;
    opacity: 0.55;
}

.is-active .base-wizard__progress-btn {
    border-color: rgba(56, 189, 248, 0.7);
    background: rgba(56, 189, 248, 0.08);
}

.is-done .base-wizard__progress-btn {
    border-color: rgba(34, 197, 94, 0.55);
    background: rgba(34, 197, 94, 0.06);
}

.base-wizard__progress-idx {
    font-variant-numeric: tabular-nums;
    font-weight: 600;
    color: rgba(148, 163, 184, 0.9);
}

.is-active .base-wizard__progress-idx {
    color: rgb(56, 189, 248);
}

.is-done .base-wizard__progress-idx {
    color: rgb(34, 197, 94);
}

.base-wizard__progress-title {
    font-weight: 500;
}

.base-wizard__content {
    min-height: 240px;
}

.base-wizard__nav {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: flex-end;
}

.base-wizard__btn {
    padding: 0.5rem 1rem;
    border-radius: 0.375rem;
    border: 1px solid transparent;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.875rem;
    transition: background 140ms ease, border-color 140ms ease;
}

.base-wizard__btn:disabled {
    cursor: not-allowed;
    opacity: 0.55;
}

.base-wizard__btn--primary {
    background: rgb(56, 189, 248);
    color: #0f172a;
}

.base-wizard__btn--primary:hover:not(:disabled) {
    background: rgb(14, 165, 233);
}

.base-wizard__btn--secondary {
    background: rgba(148, 163, 184, 0.1);
    border-color: rgba(148, 163, 184, 0.35);
    color: inherit;
}

.base-wizard__btn--secondary:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.2);
}

.base-wizard__btn--ghost {
    background: transparent;
    color: inherit;
    border-color: transparent;
}

.base-wizard__btn--ghost:hover:not(:disabled) {
    background: rgba(148, 163, 184, 0.1);
}
</style>
