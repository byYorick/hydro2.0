<template>
  <div class="flex flex-wrap gap-2" role="tablist" :aria-label="ariaLabel">
    <button
      v-for="(tab, index) in tabs"
      :key="tab.id"
      ref="tabRefs"
      type="button"
      role="tab"
      :aria-selected="tab.id === modelValue"
      :aria-disabled="tab.disabled || undefined"
      :tabindex="tab.id === modelValue ? 0 : -1"
      :class="[
        baseClass,
        tab.id === modelValue ? activeClass : inactiveClass,
        tab.disabled ? disabledClass : '',
      ]"
      :disabled="tab.disabled"
      @click="onSelect(tab)"
      @keydown="onKeydown($event, index)"
    >
      <span>{{ tab.label }}</span>
      <span
        v-if="tab.badge !== undefined"
        class="text-[10px] px-1.5 py-0.5 rounded-full bg-[color:var(--bg-elevated)] text-[color:var(--text-dim)]"
      >
        {{ tab.badge }}
      </span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'

interface TabItem {
  id: string
  label: string
  disabled?: boolean
  badge?: string | number
}

interface Props {
  modelValue: string
  tabs: TabItem[]
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  ariaLabel: 'Tabs',
})

const emit = defineEmits<{ (e: 'update:modelValue', value: string): void }>()

const tabRefs = ref<HTMLButtonElement[]>([])

const baseClass = 'inline-flex items-center gap-2 px-3 py-2 text-sm font-semibold rounded-lg border transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent-cyan)]/40'
const activeClass = 'bg-[color:var(--bg-surface-strong)] text-[color:var(--text-primary)] border-[color:var(--border-strong)]'
const inactiveClass = 'text-[color:var(--text-dim)] border-transparent hover:text-[color:var(--text-primary)] hover:bg-[color:var(--bg-elevated)]'
const disabledClass = 'opacity-50 cursor-not-allowed'

const onSelect = (tab: TabItem): void => {
  if (tab.disabled) return
  emit('update:modelValue', tab.id)
}

const focusTab = (index: number): void => {
  const el = tabRefs.value[index]
  if (el) {
    el.focus()
  }
}

const getNextEnabledIndex = (startIndex: number, direction: 1 | -1): number => {
  const total = props.tabs.length
  if (total === 0) return startIndex

  let nextIndex = startIndex
  for (let i = 0; i < total; i += 1) {
    nextIndex = (nextIndex + direction + total) % total
    if (!props.tabs[nextIndex].disabled) {
      return nextIndex
    }
  }

  return startIndex
}

const onKeydown = (event: KeyboardEvent, index: number): void => {
  if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return

  event.preventDefault()
  const direction = event.key === 'ArrowRight' ? 1 : -1
  const nextIndex = getNextEnabledIndex(index, direction)
  const nextTab = props.tabs[nextIndex]
  if (!nextTab || nextTab.disabled) return

  emit('update:modelValue', nextTab.id)
  nextTick(() => focusTab(nextIndex))
}
</script>
