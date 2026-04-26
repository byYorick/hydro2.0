<template>
  <Teleport to="body">
    <transition name="hf-drawer">
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex justify-end bg-black/45 backdrop-blur-sm"
        @click.self="$emit('close')"
      >
        <aside
          class="w-[min(420px,95vw)] h-screen flex flex-col bg-[var(--bg-surface-strong)] border-l border-[var(--border-muted)] shadow-2xl"
          role="dialog"
          aria-modal="true"
        >
          <header
            class="flex items-start justify-between gap-3 px-4 py-3 border-b border-[var(--border-muted)]"
          >
            <div class="min-w-0">
              <div class="text-sm font-semibold text-[var(--text-primary)]">
                {{ title }}
              </div>
              <div class="text-[11px] text-[var(--text-dim)] mt-0.5">
                {{ blockers.length }} {{ blockers.length === 1 ? 'контракт требует' : 'контрактов требуют' }} действия
              </div>
            </div>
            <button
              type="button"
              class="w-7 h-7 inline-flex items-center justify-center rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]"
              @click="$emit('close')"
            >
              <Ic name="x" />
            </button>
          </header>

          <div class="flex-1 overflow-y-auto px-3 py-3">
            <div
              v-if="blockers.length === 0"
              class="text-sm text-[var(--text-dim)] py-6 text-center"
            >
              Активных блокеров нет — все обязательные контракты закрыты.
            </div>

            <ul
              v-else
              class="flex flex-col gap-2"
            >
              <li
                v-for="contract in blockers"
                :key="contract.id"
                class="rounded-md border border-[var(--border-muted)] bg-[var(--bg-elevated)] p-3 flex flex-col gap-1.5"
              >
                <div class="flex items-center justify-between gap-2 flex-wrap">
                  <Chip tone="warn">
                    <span class="font-mono">{{ contract.subsystem }} · {{ contract.component }}</span>
                  </Chip>
                  <Chip tone="alert">
                    <span class="font-mono text-[10px]">блокер</span>
                  </Chip>
                </div>
                <div class="text-sm font-medium text-[var(--text-primary)]">
                  {{ contract.title }}
                </div>
                <div
                  v-if="contract.description"
                  class="text-[11px] text-[var(--text-muted)] leading-relaxed"
                >
                  {{ contract.description }}
                </div>
                <button
                  v-if="contract.action"
                  type="button"
                  class="mt-1 self-start px-2.5 py-1 rounded-md border border-brand text-brand text-[11px] hover:bg-brand-soft transition-colors"
                  @click="$emit('navigate', contract)"
                >
                  {{ contract.action.label }} →
                </button>
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </transition>
  </Teleport>
</template>

<script setup lang="ts">
import { Chip } from '@/Components/Shared/Primitives'
import Ic from '@/Components/Icons/Ic.vue'

/**
 * Универсальный shape блокера для Automation/Calibration drawer'ов.
 * Совместим с AutomationContract и CalibrationContract — оба имеют
 * id/subsystem/component/title/description?/action?.
 */
export interface BlockerContract {
  id: string
  subsystem: string
  component: string
  title: string
  description?: string
  action?: { label: string; target?: string }
}

defineProps<{
  open: boolean
  blockers: readonly BlockerContract[]
  title?: string
}>()

defineEmits<{
  (e: 'close'): void
  (e: 'navigate', contract: BlockerContract): void
}>()
</script>

<style scoped>
.hf-drawer-enter-active,
.hf-drawer-leave-active {
  transition: opacity 180ms ease;
}
.hf-drawer-enter-from,
.hf-drawer-leave-to {
  opacity: 0;
}
.hf-drawer-enter-active aside,
.hf-drawer-leave-active aside {
  transition: transform 200ms ease;
}
.hf-drawer-enter-from aside,
.hf-drawer-leave-to aside {
  transform: translateX(8px);
}
</style>
