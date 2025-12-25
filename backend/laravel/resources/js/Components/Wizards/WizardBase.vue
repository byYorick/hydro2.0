<template>
  <div class="wizard-base">
    <!-- Прогресс-бар шагов -->
    <div class="mb-6">
      <div class="flex items-center justify-between">
        <div
          v-for="(step, index) in steps"
          :key="step.id"
          class="flex items-center flex-1"
        >
          <div class="flex items-center">
            <div
              :class="[
                'w-10 h-10 rounded-full flex items-center justify-center text-sm font-semibold transition-all',
                currentStep > index
                  ? 'bg-[color:var(--accent-green)] text-white'
                  : currentStep === index
                  ? 'bg-[color:var(--accent-cyan)] text-white ring-2 ring-[color:var(--accent-cyan)] ring-offset-2'
                  : 'bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]'
              ]"
            >
              <span v-if="currentStep > index">✓</span>
              <span v-else>{{ index + 1 }}</span>
            </div>
            <span
              :class="[
                'ml-3 text-sm font-medium',
                currentStep >= index ? 'text-[color:var(--text-primary)]' : 'text-[color:var(--text-muted)]'
              ]"
            >
              {{ step.title }}
            </span>
          </div>
          <div
            v-if="index < steps.length - 1"
            :class="[
              'flex-1 h-0.5 mx-4 transition-colors',
              currentStep > index ? 'bg-[color:var(--accent-green)]' : 'bg-[color:var(--border-muted)]'
            ]"
          />
        </div>
      </div>
    </div>

    <!-- Описание текущего шага -->
    <div v-if="currentStepData?.description" class="mb-4 p-4 rounded-lg bg-[color:var(--bg-elevated)] border border-[color:var(--border-muted)]">
      <p class="text-sm text-[color:var(--text-muted)]">
        {{ currentStepData.description }}
      </p>
    </div>

    <!-- Ошибки валидации -->
    <div
      v-if="stepErrors.length > 0"
      class="mb-4 p-4 rounded-lg bg-[color:var(--badge-danger-bg)] border border-[color:var(--badge-danger-border)]"
    >
      <ul class="list-disc list-inside text-sm text-[color:var(--badge-danger-text)]">
        <li v-for="(error, index) in stepErrors" :key="index">
          {{ error }}
        </li>
      </ul>
    </div>

    <!-- Контент шага (slot) -->
    <div class="wizard-content">
      <slot :step="currentStepData" :stepIndex="currentStep" />
    </div>

    <!-- Навигация -->
    <div class="mt-6 flex items-center justify-between">
      <Button
        v-if="!isFirstStep"
        variant="secondary"
        @click="handlePrev"
        :disabled="!canGoPrev"
      >
        Назад
      </Button>
      <div v-else />

      <div class="flex gap-2">
        <Button
          v-if="!isLastStep"
          variant="primary"
          @click="handleNext"
          :disabled="!canGoNext"
        >
          Далее
        </Button>
        <Button
          v-else
          variant="primary"
          @click="handleSubmit"
          :disabled="!isValid || submitting"
          :loading="submitting"
        >
          {{ submitLabel }}
        </Button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Button from '@/Components/Button.vue'
import type { WizardState, WizardStep } from '@/composables/useWizardState'

interface Props {
  wizardState: WizardState
  submitLabel?: string
  submitting?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  submitLabel: 'Завершить',
  submitting: false,
})

const emit = defineEmits<{
  next: []
  prev: []
  submit: []
}>()

const currentStepData = computed<WizardStep | undefined>(() => {
  return props.wizardState.steps.value[props.wizardState.currentStep.value]
})

const stepErrors = computed<string[]>(() => {
  const stepKey = `step_${props.wizardState.currentStep.value}`
  return props.wizardState.errors.value[stepKey] || []
})

const currentStep = computed(() => props.wizardState.currentStep.value)
const steps = computed(() => props.wizardState.steps.value)
const isValid = computed(() => props.wizardState.isValid.value)
const canGoNext = computed(() => props.wizardState.canGoNext.value)
const canGoPrev = computed(() => props.wizardState.canGoPrev.value)
const isFirstStep = computed(() => props.wizardState.isFirstStep.value)
const isLastStep = computed(() => props.wizardState.isLastStep.value)

const handleNext = async () => {
  await props.wizardState.next()
  emit('next')
}

const handlePrev = () => {
  props.wizardState.prev()
  emit('prev')
}

const handleSubmit = async () => {
  await props.wizardState.submit()
  emit('submit')
}
</script>

<style scoped>
.wizard-base {
  @apply w-full;
}

.wizard-content {
  @apply min-h-[200px];
}
</style>

