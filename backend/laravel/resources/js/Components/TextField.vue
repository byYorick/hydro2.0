<template>
  <component
    :is="label ? 'label' : 'div'"
    :class="rootClass"
  >
    <span
      v-if="label"
      class="field-label shrink-0"
    >{{ label }}</span>
    <span
      class="flex min-w-0 items-center gap-2"
      :class="inline ? 'flex-1' : 'w-full'"
    >
      <textarea
        v-if="multiline"
        ref="control"
        v-model="model"
        class="input-field min-w-0 w-full"
        :class="[controlClass, attrs.class]"
        :rows="rows"
        :disabled="disabled || undefined"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
        v-bind="inputAttrs"
      ></textarea>
      <input
        v-else
        ref="control"
        v-model="model"
        class="input-field min-w-0"
        :class="[inline ? 'flex-1' : 'w-full', controlClass, attrs.class]"
        :type="type"
        :disabled="disabled || undefined"
        :aria-invalid="error ? 'true' : undefined"
        :aria-describedby="describedBy"
        v-bind="inputAttrs"
      />
      <span
        v-if="suffix"
        class="shrink-0 text-xs text-[color:var(--text-muted)]"
      >{{ suffix }}</span>
    </span>
    <span
      v-if="hint && !error"
      :id="hintId"
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
import { computed, onMounted, ref, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

interface Props {
  label?: string
  error?: string
  hint?: string
  suffix?: string
  inline?: boolean
  multiline?: boolean
  rows?: number | string
  type?: string
  disabled?: boolean
  controlClass?: string
}

const props = withDefaults(defineProps<Props>(), {
  label: '',
  error: '',
  hint: '',
  suffix: '',
  inline: false,
  multiline: false,
  rows: 3,
  type: 'text',
  disabled: false,
  controlClass: '',
})

const model = defineModel<string | number | boolean | null>({ default: '' })
const attrs = useAttrs()
const control = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)
const errorId = `field-error-${Math.random().toString(36).slice(2, 10)}`
const hintId = `field-hint-${Math.random().toString(36).slice(2, 10)}`

const describedBy = computed(() => {
  if (props.error) {
    return errorId
  }
  if (props.hint) {
    return hintId
  }
  return undefined
})

const inputAttrs = computed(() => {
  const { class: _class, type: _type, ...rest } = attrs
  return rest
})

const rootClass = computed(() => [
  props.inline
    ? 'flex min-w-0 flex-wrap items-center gap-2'
    : 'flex min-w-0 flex-col gap-1',
  attrs.class,
])

onMounted(() => {
  const element = control.value
  if (element?.hasAttribute('autofocus')) {
    element.focus()
  }
})

defineExpose({
  focus: () => control.value?.focus(),
})
</script>
