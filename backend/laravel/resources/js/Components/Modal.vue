<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 flex"
      :class="[rootClass, placement === 'center' ? 'items-center justify-center p-4' : placement === 'workspace' ? 'items-center justify-center sm:p-4' : placement === 'left' ? 'justify-start' : 'justify-end']"
      role="presentation"
      data-testid="app-modal-root"
    >
      <div
        class="absolute inset-0 bg-[color:var(--bg-main)] opacity-80"
        data-testid="app-modal-backdrop"
        @click="$emit('close')"
      ></div>
      <div
        :id="dialogId"
        ref="dialogRef"
        class="relative w-full border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] shadow-[var(--shadow-elevated)] focus:outline-none"
        :class="placement === 'center'
          ? ['rounded-2xl p-4 max-h-[90vh] overflow-y-auto', size === 'xlarge' ? 'max-w-6xl' : size === 'large' ? 'max-w-4xl' : 'max-w-lg']
          : placement === 'workspace'
            ? 'flex h-[100dvh] min-h-0 max-w-5xl flex-col overflow-hidden sm:h-[92dvh] sm:rounded-2xl'
            : 'flex h-full min-h-0 max-w-sm flex-col'"
        role="dialog"
        aria-modal="true"
        tabindex="-1"
        :aria-labelledby="title ? titleId : undefined"
        :aria-label="title ? undefined : 'Диалог'"
        :data-testid="$attrs['data-testid']"
      >
        <div :class="placement === 'center' ? 'mb-2' : 'flex shrink-0 items-center justify-between gap-3 border-b border-[color:var(--border-muted)] px-5 py-4'">
          <div
            :id="titleId"
            class="text-base font-semibold text-[color:var(--text-primary)]"
          >
            {{ title }}
          </div>
          <button
            v-if="placement !== 'center'"
            type="button"
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[color:var(--status-info)]"
            :aria-label="placement === 'workspace' ? 'Закрыть окно' : 'Закрыть панель'"
            @click="emit('close')"
          >
            <svg
              class="h-5 w-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="1.5"
              aria-hidden="true"
            >
              <path d="m6 6 12 12M6 18 18 6" />
            </svg>
          </button>
        </div>
        <div
          class="text-sm text-[color:var(--text-muted)]"
          :class="placement === 'center' ? 'mb-4' : placement === 'workspace' ? 'min-h-0 flex-1 overflow-hidden' : 'min-h-0 flex-1 overflow-y-auto overscroll-contain p-5'"
        >
          <slot></slot>
        </div>
        <div
          v-if="!hideDefaultCancel || $slots.footer"
          class="flex flex-wrap justify-end gap-2"
          :class="placement !== 'center' ? 'shrink-0 border-t border-[color:var(--border-muted)] p-4' : ''"
        >
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
  placement?: 'center' | 'left' | 'right' | 'workspace'
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  title: '',
  size: 'default',
  hideDefaultCancel: false,
  placement: 'center',
})

const emit = defineEmits<{
  close: []
}>()

const titleId = `app-modal-title-${Math.random().toString(36).slice(2, 10)}`
const dialogRef = ref<HTMLElement | null>(null)
let previouslyFocused: HTMLElement | null = null

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

function focusableElements(): HTMLElement[] {
  if (!dialogRef.value) {
    return []
  }
  return Array.from(dialogRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    .filter((element) => !element.hasAttribute('disabled') && element.tabIndex !== -1 && !element.closest('[hidden], [inert]'))
}

function onKeydown(event: KeyboardEvent): void {
  // Nested dialogs own Escape and focus until they close.
  const roots = Array.from(document.querySelectorAll<HTMLElement>('[data-testid="app-modal-root"]'))
  roots.sort((a, b) => (Number.parseInt(getComputedStyle(a).zIndex) || 0) - (Number.parseInt(getComputedStyle(b).zIndex) || 0))
  const topRoot = roots[roots.length - 1]
  if (topRoot && !topRoot.contains(dialogRef.value)) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }

  if (event.key !== 'Tab' || !dialogRef.value) {
    return
  }

  const items = focusableElements()
  if (items.length === 0) {
    event.preventDefault()
    dialogRef.value.focus()
    return
  }

  const currentIndex = items.indexOf(document.activeElement as HTMLElement)
  event.preventDefault()
  if (event.shiftKey) {
    const nextIndex = currentIndex <= 0 ? items.length - 1 : currentIndex - 1
    items[nextIndex]?.focus()
    return
  }
  const nextIndex = currentIndex === -1 || currentIndex >= items.length - 1 ? 0 : currentIndex + 1
  items[nextIndex]?.focus()
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
      previouslyFocused?.focus()
  }
})

defineOptions({
  inheritAttrs: false,
})

const attrs = useAttrs()
const dialogId = computed(() => typeof attrs.id === 'string' ? attrs.id : undefined)

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
