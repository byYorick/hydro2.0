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
      class="space-y-2.5"
    >
      <!-- Основные поля: компактная сетка ключ–значение -->
      <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2">
        <div class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-xs">
          <span class="text-[color:var(--text-dim)] whitespace-nowrap">тип</span>
          <span class="font-sans font-semibold text-[color:var(--text-primary)] break-words">{{ getAlertTitle(alert) }}</span>

          <span class="text-[color:var(--text-dim)] whitespace-nowrap">статус</span>
          <span class="font-sans text-[color:var(--text-primary)]">{{ translateStatus(alert.status) }}</span>

          <template v-if="alert.code">
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">код</span>
            <span class="text-[color:var(--text-primary)]">{{ alert.code }}</span>
          </template>

          <template v-if="alert.source">
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">источник</span>
            <span class="font-sans text-[color:var(--text-primary)]">{{ alert.source }}</span>
          </template>

          <template v-if="alert.severity">
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">severity</span>
            <span class="text-[color:var(--text-primary)]">{{ alert.severity }}</span>
          </template>

          <template v-if="alert.node_uid">
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">node</span>
            <span class="text-[color:var(--text-primary)]">{{ alert.node_uid }}</span>
          </template>

          <template v-if="alert.hardware_id">
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">hw</span>
            <span class="text-[color:var(--text-primary)]">{{ alert.hardware_id }}</span>
          </template>

          <template v-if="typeof alert.error_count === 'number'">
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">count</span>
            <span class="text-[color:var(--text-primary)]">{{ alert.error_count }}</span>
          </template>

          <span class="text-[color:var(--text-dim)] whitespace-nowrap">создан</span>
          <span class="font-sans text-[color:var(--text-primary)]">{{ formatAlertDate(alert.created_at) }}</span>

          <template v-if="alert.resolved_at">
            <span class="text-[color:var(--text-dim)] whitespace-nowrap">решён</span>
            <span class="font-sans text-[color:var(--text-primary)]">{{ formatAlertDate(alert.resolved_at) }}</span>
          </template>
        </div>
      </div>

      <!-- Сообщение / описание / рекомендация -->
      <div
        v-if="message || description || recommendation"
        class="space-y-1.5"
      >
        <div
          v-if="message"
          class="space-y-0.5"
        >
          <p class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
            Сообщение
          </p>
          <p class="text-xs leading-snug text-[color:var(--text-primary)]">
            {{ message }}
          </p>
        </div>
        <div
          v-if="description"
          class="space-y-0.5"
        >
          <p class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
            Описание
          </p>
          <p class="text-xs leading-snug text-[color:var(--text-primary)]">
            {{ description }}
          </p>
        </div>
        <div
          v-if="recommendation"
          class="space-y-0.5"
        >
          <p class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">
            Что делать
          </p>
          <p class="text-xs leading-snug text-[color:var(--text-primary)]">
            {{ recommendation }}
          </p>
        </div>
      </div>

      <!-- Payload details (сворачиваемый) -->
      <div v-if="detailsJson">
        <button
          type="button"
          class="flex w-full items-center gap-1.5 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-2.5 py-1.5 transition-colors hover:bg-[color:var(--bg-elevated)]/80"
          @click="payloadExpanded = !payloadExpanded"
        >
          <span class="text-[11px] text-[color:var(--text-dim)]">{{ payloadExpanded ? '⌄' : '›' }}</span>
          <span class="text-[11px] uppercase tracking-wide text-[color:var(--text-dim)]">Payload</span>
          <div class="ml-auto flex items-center gap-1.5">
            <span
              v-if="copyState === 'copied'"
              class="text-[11px] text-[color:var(--accent-green)]"
            >Скопировано</span>
            <span
              v-else-if="copyState === 'failed'"
              class="text-[11px] text-[color:var(--accent-red)]"
            >Ошибка</span>
            <span
              class="h-5 px-2 text-[11px] rounded border border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] transition-colors"
              :class="copyState === 'copying' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'"
              @click.stop="copyPayload"
            >
              {{ copyState === 'copying' ? '...' : 'Копировать' }}
            </span>
          </div>
        </button>
        <pre
          v-if="payloadExpanded"
          class="mt-1 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] p-2 text-[10px] overflow-x-auto text-[color:var(--text-primary)] leading-relaxed"
        >{{ detailsJson }}</pre>
      </div>
    </div>

    <template #footer>
      <Button
        v-if="alert && canResolve"
        variant="success"
        size="sm"
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
const payloadExpanded = ref(false)

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

