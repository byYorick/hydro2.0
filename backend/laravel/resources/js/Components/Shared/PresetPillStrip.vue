<template>
  <div
    class="flex flex-col gap-2.5 p-3 rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)]"
    :data-testid="testId"
  >
    <div class="flex items-center justify-between gap-2 flex-wrap">
      <span class="text-xs font-semibold text-[var(--text-primary)]">
        {{ label }}
      </span>
      <div
        v-if="$slots.actions"
        class="flex items-center gap-1.5 flex-wrap"
      >
        <slot name="actions" />
      </div>
    </div>

    <div class="flex gap-1.5 flex-wrap">
      <button
        v-for="item in items"
        :key="itemKey(item.key)"
        type="button"
        :class="tileClass(isActive(item.key), Boolean(item.disabled) || disabled)"
        :disabled="disabled || item.disabled"
        :data-testid="item.testId"
        :title="item.title"
        @click="onSelect(item)"
      >
        <span class="text-xs font-semibold inline-flex items-center gap-1">
          {{ item.label }}
          <span
            v-if="item.locked"
            class="text-[10px] font-normal"
            aria-hidden="true"
          >🔒</span>
        </span>
        <span
          v-if="item.meta"
          class="font-mono text-[10px]"
          :class="isActive(item.key) ? 'opacity-75' : 'text-[var(--text-dim)]'"
        >
          {{ item.meta }}
        </span>
      </button>

      <slot name="extra" />
    </div>

    <p
      v-if="description"
      class="text-[11px] text-[var(--text-muted)] leading-snug"
    >
      {{ description }}
    </p>
  </div>
</template>

<script setup lang="ts">
export type PresetPillKey = string | number | null

export interface PresetPillItem {
  key: PresetPillKey
  label: string
  meta?: string
  locked?: boolean
  disabled?: boolean
  title?: string
  testId?: string
}

const props = withDefaults(defineProps<{
  items: PresetPillItem[]
  modelValue: PresetPillKey
  label?: string
  description?: string
  disabled?: boolean
  testId?: string
}>(), {
  label: 'Пресет',
  description: '',
  disabled: false,
  testId: 'preset-pill-strip',
})

const emit = defineEmits<{
  'update:modelValue': [key: PresetPillKey]
  select: [key: PresetPillKey]
}>()

function itemKey(key: PresetPillKey): string {
  return key === null ? '__null__' : String(key)
}

function isActive(key: PresetPillKey): boolean {
  return props.modelValue === key
}

function tileClass(active: boolean, isDisabled: boolean): string {
  return [
    'px-3 py-2 border rounded-sm text-left flex flex-col items-start gap-0.5 min-w-[120px] transition-colors',
    active
      ? 'bg-brand text-white border-brand font-semibold'
      : 'bg-[var(--bg-surface)] text-[var(--text-primary)] border-[var(--border-muted)] hover:border-brand',
    isDisabled ? 'opacity-55 cursor-not-allowed' : 'cursor-pointer',
  ].join(' ')
}

function onSelect(item: PresetPillItem): void {
  if (props.disabled || item.disabled) {
    return
  }
  if (props.modelValue === item.key) {
    return
  }
  emit('update:modelValue', item.key)
  emit('select', item.key)
}
</script>
