<template>
  <component
    :is="label ? 'label' : 'div'"
    :class="rootClass"
  >
    <span
      v-if="label"
      class="field-label shrink-0"
    >
      {{ label }}<span
        v-if="required"
        class="text-status-critical"
      > *</span>
    </span>
    <span
      class="flex min-w-0 items-center gap-2"
      :class="inline ? 'flex-1' : 'w-full'"
    >
      <textarea
        v-if="multiline"
        :id="controlId"
        ref="control"
        class="input-field min-w-0 flex-1"
        :class="inputClass"
        :rows="rows"
        :value="displayValue"
        :disabled="disabled || undefined"
        :required="required || undefined"
        v-bind="inputAttrs"
        :aria-invalid="isInvalid ? 'true' : undefined"
        :aria-describedby="describedBy"
        @input="onInput"
      ></textarea>
      <input
        v-else
        :id="controlId"
        ref="control"
        class="input-field min-w-0 flex-1"
        :class="inputClass"
        type="text"
        :value="displayValue"
        :disabled="disabled || undefined"
        :required="required || undefined"
        v-bind="inputAttrs"
        :aria-invalid="isInvalid ? 'true' : undefined"
        :aria-describedby="describedBy"
        @input="onInput"
      />
      <span
        v-if="suffix"
        class="shrink-0 text-xs text-[color:var(--text-muted)]"
      >{{ suffix }}</span>
    </span>
    <span
      v-if="hint && !error"
      :id="hintId"
      class="field-hint"
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
import { applyFieldModifiers, type FieldModelValue } from './fieldValue'

defineOptions({ inheritAttrs: false })

interface Props {
  label?: string
  error?: string
  hint?: string
  inline?: boolean
  multiline?: boolean
  rows?: number
  suffix?: string
  disabled?: boolean
  required?: boolean
  invalid?: boolean
  inputClass?: string | string[] | Record<string, boolean>
}

const props = withDefaults(defineProps<Props>(), {
  label: '',
  error: '',
  hint: '',
  inline: false,
  multiline: false,
  rows: 3,
  suffix: '',
  disabled: false,
  required: false,
  invalid: false,
  inputClass: '',
})

const [model, modifiers] = defineModel<FieldModelValue>({
  default: '',
  set(value) {
    return applyFieldModifiers(value, modifiers)
  },
})

const attrs = useAttrs()
const control = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)
const uid = `field-${Math.random().toString(36).slice(2, 10)}`
const errorId = `${uid}-error`
const hintId = `${uid}-hint`

const controlId = computed(() => {
  const id = attrs.id
  return typeof id === 'string' && id.length > 0 ? id : uid
})

const inputAttrs = computed(() => {
  const { class: _class, id: _id, onInput: _onInput, ...rest } = attrs
  return rest
})

const displayValue = computed(() => (model.value == null ? '' : String(model.value)))

const isInvalid = computed(() => props.invalid || Boolean(props.error))

const describedBy = computed(() => {
  if (props.error) return errorId
  if (props.hint) return hintId
  return undefined
})

const rootClass = computed(() => [
  props.inline
    ? 'flex min-w-0 flex-wrap items-center gap-2'
    : 'flex min-w-0 flex-col gap-1',
  attrs.class,
])

function callListener(listener: unknown, event: Event): void {
  if (typeof listener === 'function') {
    listener(event)
    return
  }
  if (Array.isArray(listener)) {
    listener.forEach((entry) => {
      if (typeof entry === 'function') {
        entry(event)
      }
    })
  }
}

function onInput(event: Event): void {
  const target = event.target as HTMLInputElement | HTMLTextAreaElement
  const type = target instanceof HTMLInputElement ? target.type : 'text'
  const next = type === 'number'
    ? applyFieldModifiers(target.value, { number: true })
    : target.value
  model.value = next
  callListener(attrs.onInput, event)
}

function focus(): void {
  control.value?.focus()
}

onMounted(() => {
  if (control.value?.hasAttribute('autofocus')) {
    control.value.focus()
  }
})

defineExpose({ focus })
</script>
