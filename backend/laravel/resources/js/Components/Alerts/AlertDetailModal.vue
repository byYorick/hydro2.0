<template>
  <Modal
    :open="open"
    title="Детали алерта"
    size="large"
    data-testid="zone-alert-details-modal"
    @close="$emit('close')"
  >
    <div
      v-if="alert"
      class="space-y-4 text-sm"
    >
      <div class="grid gap-4 md:grid-cols-2">
        <div class="space-y-1">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            Тип
          </div>
          <div class="font-semibold text-[color:var(--text-primary)]">
            {{ getAlertTitle(alert) }}
          </div>
        </div>
        <div class="space-y-1">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            Статус
          </div>
          <div class="font-semibold text-[color:var(--text-primary)]">
            {{ translateStatus(alert.status) }}
          </div>
        </div>
        <div
          v-if="alert.code"
          class="space-y-1"
        >
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            Код
          </div>
          <div class="font-mono text-[color:var(--text-primary)]">
            {{ alert.code }}
          </div>
        </div>
        <div
          v-if="alert.source"
          class="space-y-1"
        >
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            Источник
          </div>
          <div class="text-[color:var(--text-primary)]">
            {{ alert.source }}
          </div>
        </div>
        <div class="space-y-1">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            Создан
          </div>
          <div class="text-[color:var(--text-primary)]">
            {{ formatAlertDate(alert.created_at) }}
          </div>
        </div>
        <div
          v-if="alert.resolved_at"
          class="space-y-1"
        >
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            Решён
          </div>
          <div class="text-[color:var(--text-primary)]">
            {{ formatAlertDate(alert.resolved_at) }}
          </div>
        </div>
      </div>

      <div
        v-if="alert.severity || alert.node_uid || alert.hardware_id || typeof alert.error_count === 'number'"
        class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]/25 p-3"
      >
        <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
          Контекст
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <span
            v-if="alert.severity"
            class="metric-pill"
          >
            severity <span class="text-[color:var(--text-primary)]">{{ String(alert.severity) }}</span>
          </span>
          <span
            v-if="alert.node_uid"
            class="metric-pill"
          >
            node <span class="font-mono text-[color:var(--text-primary)]">{{ alert.node_uid }}</span>
          </span>
          <span
            v-if="alert.hardware_id"
            class="metric-pill"
          >
            hw <span class="font-mono text-[color:var(--text-primary)]">{{ alert.hardware_id }}</span>
          </span>
          <span
            v-if="typeof alert.error_count === 'number'"
            class="metric-pill"
          >
            count <span class="text-[color:var(--text-primary)]">{{ alert.error_count }}</span>
          </span>
        </div>
      </div>

      <div
        v-if="message"
        class="space-y-1"
      >
        <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
          Сообщение
        </div>
        <div class="text-[color:var(--text-primary)]">
          {{ message }}
        </div>
      </div>

      <div
        v-if="description"
        class="space-y-1"
      >
        <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
          Описание
        </div>
        <div class="text-[color:var(--text-primary)]">
          {{ description }}
        </div>
      </div>

      <div
        v-if="recommendation"
        class="space-y-1"
      >
        <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
          Что делать
        </div>
        <div class="text-[color:var(--text-primary)]">
          {{ recommendation }}
        </div>
      </div>

      <div
        v-if="detailsJson"
        class="space-y-1"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
            Payload details
          </div>
          <div class="flex items-center gap-2">
            <span
              v-if="copyState === 'copied'"
              class="text-xs text-[color:var(--accent-green)]"
            >
              Скопировано
            </span>
            <span
              v-else-if="copyState === 'failed'"
              class="text-xs text-[color:var(--accent-red)]"
            >
              Не удалось скопировать
            </span>
            <Button
              size="sm"
              variant="outline"
              :disabled="copyState === 'copying'"
              @click="copyPayload"
            >
              {{ copyState === 'copying' ? 'Копирую...' : 'Скопировать' }}
            </Button>
          </div>
        </div>
        <pre class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-3 text-xs overflow-x-auto text-[color:var(--text-primary)]">{{ detailsJson }}</pre>
      </div>
    </div>

    <template #footer>
      <Button
        v-if="alert && canResolve"
        variant="success"
        :disabled="resolveLoading"
        data-testid="zone-alert-resolve-button"
        @click="$emit('resolve')"
      >
        {{ resolveLoading ? 'Решаю...' : 'Решить' }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from '@/Components/Button.vue'
import Modal from '@/Components/Modal.vue'
import { translateStatus } from '@/utils/i18n'
import type { Alert } from '@/types/Alert'
import {
  detailsToString,
  formatAlertDate,
  getAlertDescription,
  getAlertMessage,
  getAlertRecommendation,
  getAlertTitle,
  normalizeAlertStatus,
} from '@/utils/alertMeta'

const props = defineProps<{
  open: boolean
  alert: Alert | null
  resolveLoading: boolean
}>()

defineEmits<{
  close: []
  resolve: []
}>()

const canResolve = computed(() => props.alert ? normalizeAlertStatus(props.alert.status) !== 'RESOLVED' : false)
const message = computed(() => (props.alert ? getAlertMessage(props.alert) : ''))
const description = computed(() => (props.alert ? getAlertDescription(props.alert) : ''))
const recommendation = computed(() => (props.alert ? getAlertRecommendation(props.alert) : ''))

const copyState = ref<'idle' | 'copying' | 'copied' | 'failed'>('idle')

const detailsJson = computed(() => {
  if (!props.alert?.details) return ''
  try {
    return JSON.stringify(props.alert.details, null, 2)
  } catch {
    return detailsToString(props.alert.details)
  }
})

async function copyPayload(): Promise<void> {
  if (!detailsJson.value) return
  copyState.value = 'copying'

  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(detailsJson.value)
    } else if (typeof document !== 'undefined') {
      const textarea = document.createElement('textarea')
      textarea.value = detailsJson.value
      textarea.setAttribute('readonly', 'true')
      textarea.style.position = 'fixed'
      textarea.style.top = '0'
      textarea.style.left = '0'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    } else {
      throw new Error('Clipboard unavailable')
    }

    copyState.value = 'copied'
    window.setTimeout(() => {
      if (copyState.value === 'copied') copyState.value = 'idle'
    }, 1500)
  } catch {
    copyState.value = 'failed'
    window.setTimeout(() => {
      if (copyState.value === 'failed') copyState.value = 'idle'
    }, 2000)
  }
}
</script>

