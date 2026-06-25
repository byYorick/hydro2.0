<template>
  <article
    class="settings-field-card"
    :data-testid="testId"
  >
    <header class="mb-3 flex items-start justify-between gap-2">
      <div class="min-w-0">
        <label
          v-if="fieldId"
          :for="fieldId"
          class="settings-field-card__label"
        >
          {{ label }}
          <span
            v-if="unit"
            class="normal-case tracking-normal text-[color:var(--text-dim)] font-normal ml-1"
          >
            ({{ unit }})
          </span>
        </label>
        <div
          v-else
          class="settings-field-card__label"
        >
          {{ label }}
          <span
            v-if="unit"
            class="normal-case tracking-normal text-[color:var(--text-dim)] font-normal ml-1"
          >
            ({{ unit }})
          </span>
        </div>
      </div>
      <SettingsFieldHelp
        v-if="description || help"
        :title="label"
        :summary="description"
        :help="help"
        :test-id="helpTestId || `${testId}-help`"
      />
    </header>

    <div class="settings-field-card__control">
      <slot />
    </div>

    <p
      v-if="description && showDescription"
      class="settings-field-card__hint"
    >
      {{ description }}
    </p>

    <div
      v-if="$slots.meta"
      class="mt-2 text-[10px] uppercase tracking-wide text-[color:var(--text-muted)]"
    >
      <slot name="meta" />
    </div>
  </article>
</template>

<script setup lang="ts">
import SettingsFieldHelp from '@/Components/Settings/SettingsFieldHelp.vue'

withDefaults(defineProps<{
  label: string
  description?: string
  help?: string
  unit?: string
  fieldId?: string
  testId?: string
  helpTestId?: string
  showDescription?: boolean
}>(), {
  description: '',
  help: '',
  unit: '',
  fieldId: '',
  testId: 'settings-field-card',
  helpTestId: '',
  showDescription: true,
})
</script>
