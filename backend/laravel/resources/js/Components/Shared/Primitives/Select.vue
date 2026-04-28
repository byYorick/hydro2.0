<template>
  <div class="relative">
    <select
      :value="modelValue ?? ''"
      :disabled="disabled"
      :class="[
        'block w-full appearance-none rounded-lg border px-3 pr-9 outline-none transition-[border-color,box-shadow,background-color] duration-150 bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]',
        invalid
          ? 'border-alert focus:border-alert focus:ring-2 focus:ring-alert-soft focus-visible:border-alert focus-visible:ring-2 focus-visible:ring-alert-soft'
          : 'border-[var(--border-muted)] focus:border-brand focus:ring-2 focus:ring-brand-soft focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand-soft',
        mono ? 'font-mono' : 'font-sans',
        disabled
          ? 'cursor-not-allowed border-[var(--border-muted)] bg-[var(--bg-elevated)] text-[var(--text-dim)] opacity-100'
          : 'cursor-default hover:border-[var(--border-strong)]',
        sizeClass,
      ]"
      @change="onChange"
    >
      <option
        v-if="placeholder"
        value=""
      >
        {{ placeholder }}
      </option>
      <template
        v-for="opt in normalizedOptions"
        :key="String(opt.value)"
      >
        <option :value="String(opt.value)">
          {{ opt.label }}
        </option>
      </template>
    </select>
    <span
      :class="[
        'pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2',
        props.disabled ? 'text-[var(--text-dim)]' : 'text-[var(--text-muted)]',
      ]"
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 14 14"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M3 5l4 4 4-4"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type SelectOption = { value: string | number; label: string }

const props = withDefaults(
  defineProps<{
    modelValue: string | number | null | undefined
    options: Array<SelectOption | string>
    placeholder?: string
    mono?: boolean
    disabled?: boolean
    invalid?: boolean
    size?: 'sm' | 'md' | 'lg'
  }>(),
  { size: 'md' },
)

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const normalizedOptions = computed<SelectOption[]>(() =>
  props.options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o)),
)

const sizeClass = computed(
  () =>
    ({
      sm: 'h-7 text-xs',
      md: 'h-8 text-sm',
      lg: 'h-10 text-base',
    })[props.size],
)

function onChange(e: Event) {
  emit('update:modelValue', (e.target as HTMLSelectElement).value)
}
</script>
