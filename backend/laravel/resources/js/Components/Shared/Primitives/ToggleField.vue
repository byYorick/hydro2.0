<template>
  <label
    :class="[
      'flex items-center gap-2 cursor-pointer text-xs',
      inline ? '' : 'h-8',
      disabled ? 'opacity-55 cursor-not-allowed' : '',
    ]"
  >
    <button
      type="button"
      role="switch"
      :aria-checked="modelValue"
      :disabled="disabled"
      :class="[
        'relative w-[30px] h-[18px] rounded-full p-0 border-0 transition-colors duration-150 shrink-0',
        modelValue ? 'bg-brand' : 'bg-[var(--border-strong)]',
      ]"
      @click="toggle"
    >
      <span
        :class="[
          'absolute top-0.5 w-3.5 h-3.5 rounded-full bg-white shadow transition-[left] duration-150',
          modelValue ? 'left-[14px]' : 'left-0.5',
        ]"
      />
    </button>
    <span
      v-if="label"
      class="font-mono text-[11px] text-[var(--text-muted)]"
    >{{ label }}</span>
    <slot />
  </label>
</template>

<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    modelValue: boolean
    label?: string
    inline?: boolean
    disabled?: boolean
  }>(),
  { inline: false, disabled: false },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

function toggle() {
  if (props.disabled) return
  emit('update:modelValue', !props.modelValue)
}
</script>
