<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 flex items-center justify-center p-4"
      :class="rootClass"
      role="presentation"
      data-testid="app-modal-root"
    >
      <div
        class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80"
        data-testid="app-modal-backdrop"
        @click="$emit('close')"
      ></div>
      <div
        ref="dialogRef"
        class="relative w-full rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-4 max-h-[90vh] overflow-y-auto shadow-[var(--shadow-card)] focus:outline-none"
        :class="size === 'xlarge' ? 'max-w-6xl' : size === 'large' ? 'max-w-4xl' : 'max-w-lg'"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
        :aria-labelledby="title ? titleId : undefined"
        :aria-label="title ? undefined : 'Диалог'"
        :data-testid="$attrs['data-testid']"
      >
        <div
          :id="titleId"
          class="mb-2 text-base font-semibold text-[color:var(--text-primary)]"
        >
          {{ title }}
        </div>
        <div class="mb-4 text-sm text-[color:var(--text-muted)]">
          <slot></slot>
        </div>
        <div class="flex justify-end gap-2">
          <Button
            v-if="!hideDefaultCancel"
            variant="secondary"
            size="sm"
            type="button"
            @click="$emit('close')"
          >
            Отмена
          </Button>
          <slot name="footer"></slot>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useAttrs, watch } from 'vue'
import Button from './Button.vue'

interface Props {
  open?: boolean
  title?: string
  size?: 'default' | 'large' | 'xlarge'
  hideDefaultCancel?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  title: '',
  size: 'default',
  hideDefaultCancel: false,
})

const emit = defineEmits<{
  close: []
}>()

const titleId = `app-modal-title-${Math.random().toString(36).slice(2, 10)}`
const dialogRef = ref<HTMLElement | null>(null)
let previouslyFocused: HTMLElement | null = null

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
  }
}

watch(() => props.open, async (isOpen) => {
  if (typeof window === 'undefined') {
    return
  }

  if (isOpen) {
    previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
    window.addEventListener('keydown', onKeydown)
    await nextTick()
    dialogRef.value?.focus()
    return
  }

  window.removeEventListener('keydown', onKeydown)
  previouslyFocused?.focus()
  previouslyFocused = null
}, { immediate: true })

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', onKeydown)
  }
})

defineOptions({
  inheritAttrs: false,
})

const attrs = useAttrs()

/** Базовый слой поверх drawers (z-50); можно поднять через class, напр. z-[70]. */
const rootClass = computed(() => {
  const extra = attrs.class
  const hasZ = typeof extra === 'string'
    ? /\bz-/.test(extra)
    : Array.isArray(extra)
      ? extra.some((item) => typeof item === 'string' && /\bz-/.test(item))
      : Boolean(extra && typeof extra === 'object' && Object.keys(extra as object).some((key) => key.startsWith('z-')))
  return [hasZ ? null : 'z-[60]', extra]
})
</script>
