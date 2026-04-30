<template>
  <header
    class="relative flex items-center justify-between gap-5 px-5 h-12 border-b border-[var(--border-muted)] bg-[var(--bg-surface-strong)] backdrop-blur-sm sticky top-0 z-20"
  >
    <div class="flex items-center gap-5">
      <div class="flex items-center gap-2 text-sm">
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M12 3c3 4 7 7 7 11a7 7 0 01-14 0c0-4 4-7 7-11z"
            stroke="var(--brand)"
            stroke-width="1.6"
            stroke-linejoin="round"
          />
          <path
            d="M12 9v7"
            stroke="var(--growth)"
            stroke-width="1.6"
            stroke-linecap="round"
          />
          <path
            d="M9.5 12l2.5 2 2.5-2"
            stroke="var(--growth)"
            stroke-width="1.6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <strong class="font-semibold tracking-tight">Hydroflow</strong>
        <span class="text-xs text-[var(--text-dim)]">· v2.0·ae3</span>
      </div>

      <nav class="flex items-center gap-1.5 text-xs">
        <slot name="breadcrumbs">
          <Link
            :href="dashboardHref"
            class="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
          >
            Dashboard
          </Link>
          <span class="text-[var(--text-dim)]">/</span>
          <span class="text-[var(--text-primary)]">Мастер запуска</span>
        </slot>
      </nav>
    </div>

    <div class="flex items-center gap-2">
      <span
        v-for="pill in pills"
        :key="pill.key"
        :class="[
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] border',
          pillToneClass(pill.status),
        ]"
        :title="`${pill.label}: ${pill.status}`"
      >
        <span :class="['inline-block w-1.5 h-1.5 rounded-full', dotClass(pill.status)]"></span>
        <span class="font-mono">{{ pill.label }}</span>
      </span>

      <span
        v-if="userEmail"
        class="hidden md:inline-flex items-center px-2.5 py-1 rounded-full text-[11px] border border-[var(--border-muted)] bg-[var(--bg-elevated)] text-[var(--text-muted)] font-mono"
        :title="userEmail"
      >
        {{ userEmail }}
      </span>

      <button
        ref="settingsBtn"
        type="button"
        :aria-label="open ? 'Закрыть настройки' : 'Открыть настройки'"
        :aria-expanded="open"
        class="ml-1 w-8 h-8 inline-flex items-center justify-center rounded-md border border-[var(--border-muted)] bg-[var(--bg-surface)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--border-strong)]"
        @click.stop="open = !open"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <circle
            cx="8"
            cy="8"
            r="2.2"
            stroke="currentColor"
            stroke-width="1.4"
          />
          <path
            d="M8 1.6v1.6M8 12.8v1.6M14.4 8h-1.6M3.2 8H1.6M12.5 3.5l-1.1 1.1M4.6 11.4l-1.1 1.1M12.5 12.5l-1.1-1.1M4.6 4.6L3.5 3.5"
            stroke="currentColor"
            stroke-width="1.4"
            stroke-linecap="round"
          />
        </svg>
      </button>
    </div>

    <LaunchSettingsPopover
      v-if="open"
      :quick-jump-steps="quickJumpSteps"
      @jump="onPopoverJump"
    />
  </header>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Link } from '@inertiajs/vue3'
import LaunchSettingsPopover from './LaunchSettingsPopover.vue'
import { useServiceHealth, type ServiceStatus } from '@/composables/useServiceHealth'
import { route } from '@/utils/route'

import type { LaunchStep } from './types'

const dashboardHref = computed(() => {
  try {
    return route('dashboard')
  } catch {
    return '/dashboard'
  }
})

defineProps<{
  userEmail?: string | null
  quickJumpSteps?: readonly LaunchStep[]
}>()

const emit = defineEmits<{ (e: 'jump', index: number): void }>()

const { pills } = useServiceHealth()

function onPopoverJump(i: number) {
  emit('jump', i)
  open.value = false
}

const open = ref(false)
const settingsBtn = ref<HTMLButtonElement | null>(null)

function onOutsideClick(e: MouseEvent) {
  if (!open.value) return
  if (settingsBtn.value && settingsBtn.value.contains(e.target as Node)) return
  open.value = false
}

onMounted(() => {
  document.addEventListener('click', onOutsideClick)
})
onUnmounted(() => {
  document.removeEventListener('click', onOutsideClick)
})

function pillToneClass(status: ServiceStatus): string {
  return {
    online: 'bg-growth-soft text-growth border-growth-soft',
    degraded: 'bg-warn-soft text-warn border-warn-soft',
    offline: 'bg-alert-soft text-alert border-alert-soft',
    unknown: 'bg-[var(--bg-elevated)] text-[var(--text-muted)] border-[var(--border-muted)]',
  }[status]
}

function dotClass(status: ServiceStatus): string {
  return {
    online: 'bg-growth',
    degraded: 'bg-warn',
    offline: 'bg-alert',
    unknown: 'bg-[var(--text-dim)]',
  }[status]
}
</script>
