<template>
  <label :class="rootClass">
    <span
      v-if="label"
      class="field-label shrink-0"
    >{{ label }}</span>
    <select
      v-model="model"
      class="input-select min-w-0"
      :class="inline ? 'flex-1' : 'w-full'"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? errorId : undefined"
      v-bind="inputAttrs"
    >
      <slot></slot>
    </select>
    <span
      v-if="error"
      :id="errorId"
      class="field-error"
      :class="inline ? 'basis-full' : ''"
      role="alert"
    >{{ error }}</span>
  </label>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

interface Props {
  label?: string
  error?: string
  inline?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: '',
  error: '',
  inline: false,
})

const model = defineModel<string | number>({ default: '' })
const attrs = useAttrs()
const errorId = `field-error-${Math.random().toString(36).slice(2, 10)}`

const inputAttrs = computed(() => {
  const { class: _class, ...rest } = attrs
  return rest
})

const rootClass = computed(() => [
  props.inline
    ? 'flex min-w-0 flex-wrap items-center gap-2'
    : 'flex min-w-0 flex-col gap-1',
  attrs.class,
])
</script>
