<template>
  <component
    :is="label ? 'label' : 'div'"
    :class="rootClass"
  >
    <span
      v-if="label"
      class="field-label shrink-0"
    >{{ label }}</span>
    <select
      v-model="model"
      class="input-select min-w-0"
      :class="[inline ? 'flex-1' : 'w-full', controlClass, attrs.class]"
      :disabled="disabled || undefined"
      :aria-invalid="error ? 'true' : undefined"
      :aria-describedby="error ? errorId : undefined"
      v-bind="inputAttrs"
    >
      <slot></slot>
    </select>
    <span
      v-if="hint && !error"
      class="text-xs text-[color:var(--text-dim)]"
      :class="inline ? 'basis-full' : ''"
    >{{ hint }}</span>
    <span
      v-if="error"
      :id="errorId"
      class="field-error"
      :class="inline ? 'basis-full' : ''"
      role="alert"
    >{{ error }}</span>
  </component>
</template>

<script setup lang="ts">
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

interface Props {
  label?: string
  error?: string
  hint?: string
  inline?: boolean
  disabled?: boolean
  controlClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  label: '',
  error: '',
  hint: '',
  inline: false,
  disabled: false,
  controlClass: '',
})

const model = defineModel<string | number | boolean | null>({ default: '' })
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
