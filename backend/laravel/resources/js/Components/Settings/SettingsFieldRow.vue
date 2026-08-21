<template>
  <div
    class="settings-row"
    :class="{ 'settings-row--stacked': stacked }"
    :data-testid="testId"
  >
    <div class="settings-row__main">
      <label
        v-if="fieldId"
        :for="fieldId"
        class="settings-row__label"
        :title="description || undefined"
      >
        {{ label }}
      </label>
      <span
        v-else
        class="settings-row__label"
        :title="description || undefined"
      >
        {{ label }}
      </span>
      <span
        v-if="unit"
        class="settings-row__unit"
      >
        {{ unit }}
      </span>
      <SettingsFieldHelp
        v-if="description || help"
        :title="label"
        :summary="description"
        :help="help"
        :test-id="helpTestId || `${testId}-help`"
      />
      <span
        v-if="changed"
        class="settings-row__changed"
        :data-testid="`${testId}-changed`"
      >
        изменено
      </span>
    </div>

    <div class="settings-row__control">
      <slot />
    </div>
  </div>
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
  changed?: boolean
  stacked?: boolean
}>(), {
  description: '',
  help: '',
  unit: '',
  fieldId: '',
  testId: 'settings-field-row',
  helpTestId: '',
  changed: false,
  stacked: false,
})
</script>
