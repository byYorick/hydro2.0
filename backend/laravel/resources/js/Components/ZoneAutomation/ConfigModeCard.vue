<template>
  <section
    class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-3"
    data-testid="config-mode-card"
  >
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
      <div>
        <div class="flex items-center gap-2">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            Режим конфигурации
          </h3>
          <Badge
            v-if="!loading && state"
            :variant="state.config_mode === 'live' ? 'warning' : 'neutral'"
            data-testid="config-mode-badge"
          >
            {{ state.config_mode === 'live' ? '✏️ Live tuning' : '🔒 Locked' }}
          </Badge>
          <span
            v-if="loading"
            class="text-xs text-[color:var(--text-dim)] animate-pulse"
          >загрузка...</span>
        </div>
        <p class="text-xs text-[color:var(--text-dim)] mt-1">
          <code>locked</code> — snapshot цикла, <code>live</code> — hot-reload правок через TTL.
        </p>
        <p
          v-if="state?.config_mode === 'live' && countdownLabel"
          class="text-xs text-amber-500 dark:text-amber-400 mt-1"
          data-testid="config-mode-countdown"
        >
          ⏱ {{ countdownLabel }}
        </p>
        <p
          v-if="state"
          class="text-xs text-[color:var(--text-muted)] mt-1"
        >
          revision: <code>{{ state.config_revision }}</code>
        </p>
      </div>

      <div class="w-full lg:w-auto flex flex-col gap-2">
        <div
          class="inline-flex gap-1 rounded-xl border border-[color:var(--border-muted)] p-1 bg-[color:var(--surface-card)]"
          :class="{ 'opacity-60': loading || saving }"
        >
          <button
            type="button"
            class="rounded-lg px-4 py-1.5 text-sm font-medium transition-all duration-150 min-w-[4.5rem]"
            :class="state?.config_mode === 'locked'
              ? 'bg-[color:var(--accent,#3b82f6)] text-white shadow-sm'
              : 'text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)]/60'"
            :disabled="!canEdit || loading || saving || state?.config_mode === 'locked'"
            data-testid="config-mode-switch-locked"
            @click="requestLocked"
          >
            locked
          </button>
          <button
            type="button"
            class="rounded-lg px-4 py-1.5 text-sm font-medium transition-all duration-150 min-w-[4.5rem]"
            :class="state?.config_mode === 'live'
              ? 'bg-[color:var(--accent,#3b82f6)] text-white shadow-sm'
              : 'text-[color:var(--text-muted)] hover:bg-[color:var(--surface-muted)]/60'"
            :disabled="!canSetLive || loading || saving || state?.config_mode === 'live' || controlMode === 'auto'"
            data-testid="config-mode-switch-live"
            @click="openLiveDialog"
          >
            live
          </button>
        </div>
        <p
          v-if="controlMode === 'auto' && state?.config_mode !== 'live'"
          class="text-xs text-[color:var(--text-dim)]"
        >
          Live недоступен при <code>control_mode=auto</code>.
        </p>
        <p
          v-if="saving"
          class="text-xs text-[color:var(--text-dim)] text-right"
        >
          Сохранение...
        </p>
        <p
          v-if="errorMessage"
          class="text-xs text-rose-500 dark:text-rose-400 text-right"
          data-testid="config-mode-error"
        >
          {{ errorMessage }}
        </p>
      </div>
    </div>

    <div
      v-if="state?.config_mode === 'live' && canSetLive"
      class="flex flex-wrap items-center gap-2 pt-1"
    >
      <button
        type="button"
        class="text-xs underline text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]"
        data-testid="config-mode-extend"
        @click="openExtendDialog"
      >
        Продлить TTL
      </button>
    </div>

    <!-- Enter-live dialog -->
    <div
      v-if="liveDialog.open"
      class="mt-3 border border-[color:var(--border-muted)] rounded-lg p-3 space-y-2 bg-[color:var(--surface-muted)]/40"
      data-testid="config-mode-live-dialog"
    >
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">Длительность live (минут, 5..10080)</span>
        <input
          v-model.number="liveDialog.ttlMin"
          type="number"
          min="5"
          max="10080"
          class="input input-bordered text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">Причина (&ge; 3 символов)</span>
        <input
          v-model="liveDialog.reason"
          type="text"
          minlength="3"
          maxlength="500"
          class="input input-bordered text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <div class="flex gap-2 justify-end">
        <button
          type="button"
          class="text-xs px-3 py-1 rounded border border-[color:var(--border-muted)]"
          @click="liveDialog.open = false"
        >
          Отмена
        </button>
        <button
          type="button"
          class="text-xs px-3 py-1 rounded bg-[color:var(--accent,#3b82f6)] text-white disabled:opacity-50"
          :disabled="saving || liveDialog.reason.length < 3 || liveDialog.ttlMin < 5"
          data-testid="config-mode-live-confirm"
          @click="confirmLive"
        >
          Включить live
        </button>
      </div>
    </div>

    <!-- Extend dialog -->
    <div
      v-if="extendDialog.open"
      class="mt-3 border border-[color:var(--border-muted)] rounded-lg p-3 space-y-2 bg-[color:var(--surface-muted)]/40"
      data-testid="config-mode-extend-dialog"
    >
      <label class="flex flex-col gap-1 text-xs">
        <span class="text-[color:var(--text-dim)]">Новое время окончания (минут от now, 5..10080)</span>
        <input
          v-model.number="extendDialog.ttlMin"
          type="number"
          min="5"
          max="10080"
          class="input input-bordered text-sm px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
        />
      </label>
      <div class="flex gap-2 justify-end">
        <button
          type="button"
          class="text-xs px-3 py-1 rounded border border-[color:var(--border-muted)]"
          @click="extendDialog.open = false"
        >
          Отмена
        </button>
        <button
          type="button"
          class="text-xs px-3 py-1 rounded bg-[color:var(--accent,#3b82f6)] text-white disabled:opacity-50"
          :disabled="saving || extendDialog.ttlMin < 5"
          @click="confirmExtend"
        >
          Продлить
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import {
  type ConfigModeState,
  zoneConfigModeApi,
} from '@/services/api/zoneConfigMode'

interface Props {
  zoneId: number
  controlMode: 'auto' | 'semi' | 'manual'
  /** роль текущего пользователя */
  role: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'changed', state: ConfigModeState): void
  (e: 'state-loaded', state: ConfigModeState): void
}>()

const state = ref<ConfigModeState | null>(null)
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref<string | null>(null)

const canEdit = computed(() =>
  ['operator', 'agronomist', 'engineer', 'admin'].includes(props.role),
)
const canSetLive = computed(() =>
  ['agronomist', 'engineer', 'admin'].includes(props.role),
)

const liveDialog = reactive({ open: false, ttlMin: 60, reason: '' })
const extendDialog = reactive({ open: false, ttlMin: 60 })

const nowTick = ref<number>(Date.now())
let tickHandle: ReturnType<typeof setInterval> | null = null

const countdownLabel = computed(() => {
  if (!state.value?.live_until) return ''
  const remainingMs = new Date(state.value.live_until).getTime() - nowTick.value
  if (remainingMs <= 0) return 'TTL истёк — скоро будет revert в locked'
  const sec = Math.floor(remainingMs / 1000)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  return h > 0 ? `${h}ч ${m}м ${s}с до revert` : `${m}м ${s}с до revert`
})

async function load() {
  loading.value = true
  errorMessage.value = null
  try {
    state.value = await zoneConfigModeApi.show(props.zoneId)
    if (state.value) emit('state-loaded', state.value)
  } catch (err: unknown) {
    errorMessage.value = extractError(err) ?? 'Ошибка загрузки режима'
  } finally {
    loading.value = false
  }
}

async function requestLocked() {
  const reason = window.prompt('Причина перехода в locked:')
  if (!reason || reason.trim().length < 3) return
  await doUpdate({ mode: 'locked', reason })
}

function openLiveDialog() {
  liveDialog.reason = ''
  liveDialog.ttlMin = 60
  liveDialog.open = true
}

function openExtendDialog() {
  extendDialog.ttlMin = 60
  extendDialog.open = true
}

async function confirmLive() {
  const liveUntil = new Date(Date.now() + liveDialog.ttlMin * 60_000).toISOString()
  await doUpdate({ mode: 'live', reason: liveDialog.reason, live_until: liveUntil })
  liveDialog.open = false
}

async function confirmExtend() {
  const liveUntil = new Date(Date.now() + extendDialog.ttlMin * 60_000).toISOString()
  saving.value = true
  errorMessage.value = null
  try {
    await zoneConfigModeApi.extend(props.zoneId, { live_until: liveUntil })
    await load()
    if (state.value) emit('changed', state.value)
    extendDialog.open = false
  } catch (err: unknown) {
    errorMessage.value = extractError(err) ?? 'Ошибка продления TTL'
  } finally {
    saving.value = false
  }
}

async function doUpdate(payload: {
  mode: 'locked' | 'live'
  reason: string
  live_until?: string
}) {
  saving.value = true
  errorMessage.value = null
  try {
    await zoneConfigModeApi.update(props.zoneId, payload)
    await load()
    if (state.value) emit('changed', state.value)
  } catch (err: unknown) {
    errorMessage.value = extractError(err) ?? 'Ошибка сохранения режима'
  } finally {
    saving.value = false
  }
}

function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { response?: { data?: { message?: string; code?: string } } }
    const data = anyErr.response?.data
    if (data?.message) return data.message
    if (data?.code) return data.code
  }
  return null
}

onMounted(() => {
  void load()
  tickHandle = setInterval(() => {
    nowTick.value = Date.now()
  }, 1_000)
})

onBeforeUnmount(() => {
  if (tickHandle !== null) clearInterval(tickHandle)
})

watch(() => props.zoneId, () => {
  void load()
})
</script>
