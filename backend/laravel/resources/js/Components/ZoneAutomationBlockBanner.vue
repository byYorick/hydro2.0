<template>
  <section
    v-if="block"
    class="rounded-lg border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]/15 p-3 flex items-start gap-3"
    data-testid="zone-automation-block-banner"
    role="alert"
  >
    <div
      class="mt-0.5 inline-flex items-center justify-center w-6 h-6 rounded-full bg-[color:var(--accent-red)]/20 text-[color:var(--accent-red)] shrink-0"
      aria-hidden="true"
    >
      <span class="text-sm font-semibold">!</span>
    </div>
    <div class="min-w-0 flex-1">
      <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <h3 class="text-sm font-semibold text-[color:var(--accent-red)]">
          Автоматика остановлена ошибкой
        </h3>
        <span
          v-if="block.reason_code"
          class="text-[10px] uppercase tracking-wide text-[color:var(--text-dim)] font-mono"
        >
          {{ block.reason_code }}
        </span>
        <span
          v-if="sinceText"
          class="text-[10px] text-[color:var(--text-dim)]"
        >
          · с {{ sinceText }}
        </span>
      </div>
      <p class="text-sm text-[color:var(--text-primary)] mt-0.5">
        {{ reasonLabel }}
      </p>
      <p
        v-if="block.message"
        class="text-xs text-[color:var(--text-secondary)] mt-0.5 break-words"
      >
        {{ block.message }}
      </p>
      <p class="text-xs text-[color:var(--text-muted)] mt-1">
        {{ hint }}
      </p>
      <div class="mt-2 flex flex-wrap items-center gap-2">
        <button
          v-if="canUnblock"
          type="button"
          class="inline-flex items-center gap-1 rounded-md border border-[color:var(--accent-red)] bg-[color:var(--bg-surface)] px-2.5 py-1 text-xs font-medium text-[color:var(--accent-red)] hover:bg-[color:var(--accent-red)]/10"
          data-testid="zone-automation-block-unblock"
          :disabled="unblocking"
          @click="modalOpen = true"
        >
          Разблокировать
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1 rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-2.5 py-1 text-xs font-medium text-[color:var(--text-primary)] hover:border-[color:var(--accent-red)]"
          data-testid="zone-automation-block-open-alerts"
          @click="$emit('open-alerts')"
        >
          Перейти к алертам
        </button>
        <span
          v-if="block.alerts_count > 1"
          class="text-[11px] text-[color:var(--text-dim)]"
        >
          Активных блокирующих алертов: {{ block.alerts_count }}
        </span>
      </div>
    </div>

    <div
      v-if="modalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      data-testid="zone-operator-unblock-modal"
    >
      <div class="w-full max-w-md rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] p-4 shadow-lg">
        <h4 class="text-sm font-semibold text-[color:var(--text-primary)]">
          Разблокировать автоматику зоны
        </h4>
        <p class="mt-2 text-xs text-[color:var(--text-secondary)]">
          Насосы и клапаны полива будут выключены через history-logger. Активная задача AE3 завершится ошибкой,
          workflow сбросится в idle. Блокирующие алерты задачи закроются. Конфиг pH/EC/targets не чинится.
        </p>
        <label class="mt-3 block text-xs font-medium text-[color:var(--text-muted)]">
          Причина (обязательно)
          <textarea
            v-model="reason"
            rows="3"
            class="mt-1 w-full rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2 py-1.5 text-sm text-[color:var(--text-primary)]"
            data-testid="zone-operator-unblock-reason"
          />
        </label>
        <label class="mt-2 flex items-start gap-2 text-xs text-[color:var(--text-secondary)]">
          <input
            v-model="confirmed"
            type="checkbox"
            class="mt-0.5"
            data-testid="zone-operator-unblock-confirm"
          >
          Понимаю, что это остановит текущий цикл подготовки/полива.
        </label>
        <p
          v-if="errorText"
          class="mt-2 text-xs text-[color:var(--accent-red)]"
          data-testid="zone-operator-unblock-error"
        >
          {{ errorText }}
        </p>
        <div class="mt-3 flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-[color:var(--border-muted)] px-2.5 py-1 text-xs"
            :disabled="unblocking"
            @click="closeModal"
          >
            Отмена
          </button>
          <button
            type="button"
            class="rounded-md bg-[color:var(--accent-red)] px-2.5 py-1 text-xs font-medium text-white disabled:opacity-50"
            data-testid="zone-operator-unblock-submit"
            :disabled="unblocking || !canSubmit"
            @click="submit"
          >
            Разблокировать
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  automationBlockHint,
  automationBlockLabel,
  type AutomationBlockPayload,
} from '@/utils/automationBlock'

interface Props {
  block: AutomationBlockPayload | null
  canUnblock?: boolean
  unblocking?: boolean
  errorText?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  canUnblock: false,
  unblocking: false,
  errorText: null,
})

const emit = defineEmits<{
  (event: 'open-alerts'): void
  (event: 'unblock', payload: { reason: string; confirm: true }): void
}>()

const modalOpen = ref(false)
const reason = ref('')
const confirmed = ref(false)
const canSubmit = computed(() => confirmed.value && reason.value.trim().length >= 3)

function closeModal(): void {
  if (props.unblocking) return
  modalOpen.value = false
  reason.value = ''
  confirmed.value = false
}

function submit(): void {
  if (!canSubmit.value) return
  emit('unblock', { reason: reason.value.trim(), confirm: true })
}

const reasonLabel = computed(() => automationBlockLabel(props.block?.reason_code ?? null))
const hint = computed(() => automationBlockHint(props.block?.reason_code ?? null))

const sinceText = computed(() => {
  const value = props.block?.since
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
})
</script>
