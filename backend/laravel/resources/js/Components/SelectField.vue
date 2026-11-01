<template>
  <label class="flex min-w-0 flex-col gap-1">
    <span
      v-if="label"
      class="field-label"
    >{{ label }}</span>
    <select
      v-model="model"
      class="input-select w-full"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? errorId : undefined"
      v-bind="attrs"
    >
      <slot />
    </select>
    <span
      v-if="error"
      :id="errorId"
      class="field-error"
      role="alert"
    >{{ error }}</span>
  </label>
</template>

<script setup lang="ts">
import { useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

interface Props {
  label?: string
  error?: string
}

withDefaults(defineProps<Props>(), {
  label: '',
  error: '',
})

const model = defineModel<string | number>({ default: '' })
const attrs = useAttrs()
const errorId = `field-error-${Math.random().toString(36).slice(2, 10)}`
</script>
