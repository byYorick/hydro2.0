<script setup lang="ts">
import { Head, Link } from '@inertiajs/vue3'
import axios from 'axios'
import { computed, onMounted, reactive, ref } from 'vue'
import { route } from '@/utils/route'

type ControlMode = 'auto' | 'semi' | 'manual'

interface ClimateState {
  greenhouse_id: number
  climate_enabled: boolean
  control_mode: ControlMode
  left_position_pct: number
  right_position_pct: number
  recommended_left_position_pct: number
  recommended_right_position_pct: number
  last_sent_left_position_pct: number | null
  last_sent_right_position_pct: number | null
  decision_reason: string | null
  decision_factors: Record<string, unknown> | null
  weather_fresh: boolean
  inside_climate_fresh: boolean
  active_manual_override_id: number | null
  next_scheduled_tick_at: string | null
  last_task_id: number | null
  last_error_code: string | null
  last_error_message: string | null
  active_alerts_summary: string[] | null
  last_decision_at: string | null
  last_command_at: string | null
}

const props = defineProps<{
  auth?: { user?: { role?: string | null } }
  greenhouse: { id: number; name: string | null }
}>()

const state = ref<ClimateState | null>(null)
const loading = ref(true)
const savingMode = ref(false)
const savingOverride = ref(false)
const error = ref<string | null>(null)
const controlMode = ref<ControlMode>('auto')
const controlModes: ControlMode[] = ['auto', 'semi', 'manual']

const overrideForm = reactive({
  left_position_pct: 40,
  right_position_pct: 40,
  ttl_sec: 1800,
  return_mode: 'auto' as ControlMode,
  reason: 'operator_request',
})

const canOperate = computed(() => {
  const role = props.auth?.user?.role ?? 'viewer'
  return ['operator', 'admin', 'agronomist', 'engineer'].includes(role)
})

const greenhouseLabel = computed(() => props.greenhouse.name ?? `Теплица #${props.greenhouse.id}`)

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return 'нет данных'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString()
}

function boolLabel(value: boolean): string {
  return value ? 'fresh' : 'stale'
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '-' : `${value}%`
}

function normalizeState(raw: unknown): ClimateState | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }
  return raw as ClimateState
}

async function loadState(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const response = await axios.get(`/api/greenhouses/${props.greenhouse.id}/climate/state`)
    const next = normalizeState(response.data?.data?.state)
    state.value = next
    if (next?.control_mode) {
      controlMode.value = next.control_mode
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'load_failed'
  } finally {
    loading.value = false
  }
}

async function updateMode(): Promise<void> {
  if (!canOperate.value || savingMode.value) {
    return
  }
  savingMode.value = true
  error.value = null
  try {
    const response = await axios.post(`/api/greenhouses/${props.greenhouse.id}/climate/control-mode`, {
      control_mode: controlMode.value,
    })
    state.value = normalizeState(response.data?.data)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'mode_update_failed'
  } finally {
    savingMode.value = false
  }
}

async function storeOverride(): Promise<void> {
  if (!canOperate.value || savingOverride.value) {
    return
  }
  savingOverride.value = true
  error.value = null
  try {
    await axios.post(`/api/greenhouses/${props.greenhouse.id}/climate/manual-override`, {
      left_position_pct: Math.max(0, Math.min(100, Math.round(overrideForm.left_position_pct))),
      right_position_pct: Math.max(0, Math.min(100, Math.round(overrideForm.right_position_pct))),
      ttl_sec: Math.max(60, Math.min(86400, Math.round(overrideForm.ttl_sec))),
      return_mode: overrideForm.return_mode,
      reason: overrideForm.reason,
    })
    await loadState()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'override_failed'
  } finally {
    savingOverride.value = false
  }
}

async function deleteOverride(): Promise<void> {
  if (!canOperate.value || savingOverride.value) {
    return
  }
  savingOverride.value = true
  error.value = null
  try {
    await axios.delete(`/api/greenhouses/${props.greenhouse.id}/climate/manual-override`)
    await loadState()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'override_delete_failed'
  } finally {
    savingOverride.value = false
  }
}

onMounted(loadState)
</script>

<template>
  <div
    class="min-h-screen bg-zinc-950 px-4 py-6 text-zinc-100"
    data-testid="greenhouse-climate-dashboard"
  >
    <Head :title="`Климат — ${greenhouseLabel}`" />

    <main class="mx-auto grid max-w-6xl gap-4">
      <header class="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-800 pb-4">
        <div>
          <h1 class="text-2xl font-semibold tracking-normal">
            Климат теплицы
          </h1>
          <p class="mt-1 text-sm text-zinc-400">
            {{ greenhouseLabel }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="h-9 rounded border border-zinc-700 px-3 text-sm text-zinc-200 hover:border-zinc-500 disabled:opacity-50"
            :disabled="loading"
            @click="loadState"
          >
            Обновить
          </button>
          <Link
            :href="route('greenhouses.show', greenhouse.id)"
            class="inline-flex h-9 items-center rounded border border-zinc-700 px-3 text-sm text-zinc-200 hover:border-zinc-500"
          >
            Назад
          </Link>
        </div>
      </header>

      <div
        v-if="error"
        class="border border-red-800 bg-red-950/30 p-3 text-sm text-red-100"
      >
        {{ error }}
      </div>

      <div
        v-if="loading"
        class="h-36 animate-pulse border border-zinc-800 bg-zinc-900/40"
      />

      <template v-else-if="state">
        <section class="grid gap-3 md:grid-cols-4">
          <div class="border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="text-xs uppercase text-zinc-500">Режим</div>
            <div class="mt-2 text-lg font-semibold">{{ state.control_mode }}</div>
          </div>
          <div class="border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="text-xs uppercase text-zinc-500">Левая / правая</div>
            <div class="mt-2 text-lg font-semibold">
              {{ pct(state.left_position_pct) }} / {{ pct(state.right_position_pct) }}
            </div>
          </div>
          <div class="border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="text-xs uppercase text-zinc-500">Рекомендация</div>
            <div class="mt-2 text-lg font-semibold">
              {{ pct(state.recommended_left_position_pct) }} / {{ pct(state.recommended_right_position_pct) }}
            </div>
          </div>
          <div class="border border-zinc-800 bg-zinc-900/40 p-3">
            <div class="text-xs uppercase text-zinc-500">Сенсоры</div>
            <div class="mt-2 text-sm">
              weather {{ boolLabel(state.weather_fresh) }} · inside {{ boolLabel(state.inside_climate_fresh) }}
            </div>
          </div>
        </section>

        <section class="grid gap-4 lg:grid-cols-[1fr_360px]">
          <div class="space-y-4">
            <div class="border border-zinc-800 bg-zinc-900/40 p-4">
              <h2 class="text-sm font-semibold text-zinc-100">Решение runtime</h2>
              <dl class="mt-3 grid gap-3 text-sm md:grid-cols-2">
                <div>
                  <dt class="text-zinc-500">Последняя команда</dt>
                  <dd>{{ pct(state.last_sent_left_position_pct) }} / {{ pct(state.last_sent_right_position_pct) }}</dd>
                </div>
                <div>
                  <dt class="text-zinc-500">Следующий tick</dt>
                  <dd>{{ formatDate(state.next_scheduled_tick_at) }}</dd>
                </div>
                <div>
                  <dt class="text-zinc-500">Последнее решение</dt>
                  <dd>{{ formatDate(state.last_decision_at) }}</dd>
                </div>
                <div>
                  <dt class="text-zinc-500">Последняя команда</dt>
                  <dd>{{ formatDate(state.last_command_at) }}</dd>
                </div>
                <div>
                  <dt class="text-zinc-500">Task</dt>
                  <dd>{{ state.last_task_id ?? '-' }}</dd>
                </div>
                <div>
                  <dt class="text-zinc-500">Override</dt>
                  <dd>{{ state.active_manual_override_id ?? '-' }}</dd>
                </div>
              </dl>
              <div
                v-if="state.decision_reason"
                class="mt-4 border-t border-zinc-800 pt-3 text-sm text-zinc-200"
              >
                {{ state.decision_reason }}
              </div>
              <div
                v-if="state.last_error_code"
                class="mt-3 border border-red-900 bg-red-950/30 p-3 text-sm text-red-100"
              >
                {{ state.last_error_code }}<span v-if="state.last_error_message"> · {{ state.last_error_message }}</span>
              </div>
              <div
                v-if="state.active_alerts_summary?.length"
                class="mt-3 border border-amber-900 bg-amber-950/30 p-3 text-sm text-amber-100"
              >
                <div class="font-medium">Активные ограничения</div>
                <ul class="mt-2 space-y-1">
                  <li
                    v-for="alert in state.active_alerts_summary"
                    :key="alert"
                  >
                    {{ alert }}
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <aside class="space-y-4">
            <div class="border border-zinc-800 bg-zinc-900/40 p-4">
              <h2 class="text-sm font-semibold text-zinc-100">Control mode</h2>
              <div class="mt-3 grid grid-cols-3 gap-1 rounded border border-zinc-800 p-1">
                <button
                  v-for="mode in controlModes"
                  :key="mode"
                  type="button"
                  class="h-9 text-sm"
                  :class="controlMode === mode ? 'bg-emerald-700 text-white' : 'text-zinc-300 hover:bg-zinc-800'"
                  :disabled="!canOperate || savingMode"
                  @click="controlMode = mode"
                >
                  {{ mode }}
                </button>
              </div>
              <button
                type="button"
                class="mt-3 h-9 w-full rounded bg-emerald-700 px-3 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
                :disabled="!canOperate || savingMode"
                @click="updateMode"
              >
                {{ savingMode ? 'Сохранение...' : 'Применить режим' }}
              </button>
            </div>

            <form
              class="border border-zinc-800 bg-zinc-900/40 p-4"
              @submit.prevent="storeOverride"
            >
              <h2 class="text-sm font-semibold text-zinc-100">Manual override</h2>
              <div class="mt-3 grid grid-cols-2 gap-3">
                <label class="text-xs text-zinc-400">
                  Левая, %
                  <input
                    v-model.number="overrideForm.left_position_pct"
                    type="number"
                    min="0"
                    max="100"
                    class="mt-1 h-9 w-full border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100"
                    :disabled="!canOperate || savingOverride"
                  />
                </label>
                <label class="text-xs text-zinc-400">
                  Правая, %
                  <input
                    v-model.number="overrideForm.right_position_pct"
                    type="number"
                    min="0"
                    max="100"
                    class="mt-1 h-9 w-full border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100"
                    :disabled="!canOperate || savingOverride"
                  />
                </label>
                <label class="text-xs text-zinc-400">
                  TTL, сек
                  <input
                    v-model.number="overrideForm.ttl_sec"
                    type="number"
                    min="60"
                    max="86400"
                    class="mt-1 h-9 w-full border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100"
                    :disabled="!canOperate || savingOverride"
                  />
                </label>
                <label class="text-xs text-zinc-400">
                  Вернуть режим
                  <select
                    v-model="overrideForm.return_mode"
                    class="mt-1 h-9 w-full border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100"
                    :disabled="!canOperate || savingOverride"
                  >
                    <option value="auto">auto</option>
                    <option value="semi">semi</option>
                    <option value="manual">manual</option>
                  </select>
                </label>
              </div>
              <label class="mt-3 block text-xs text-zinc-400">
                Причина
                <input
                  v-model="overrideForm.reason"
                  type="text"
                  maxlength="500"
                  class="mt-1 h-9 w-full border border-zinc-700 bg-zinc-950 px-2 text-sm text-zinc-100"
                  :disabled="!canOperate || savingOverride"
                />
              </label>
              <div class="mt-3 grid grid-cols-2 gap-2">
                <button
                  type="submit"
                  class="h-9 rounded bg-emerald-700 px-3 text-sm font-medium text-white hover:bg-emerald-600 disabled:opacity-50"
                  :disabled="!canOperate || savingOverride"
                >
                  {{ savingOverride ? 'Отправка...' : 'Отправить' }}
                </button>
                <button
                  type="button"
                  class="h-9 rounded border border-zinc-700 px-3 text-sm text-zinc-200 hover:border-zinc-500 disabled:opacity-50"
                  :disabled="!canOperate || savingOverride"
                  @click="deleteOverride"
                >
                  Снять
                </button>
              </div>
            </form>
          </aside>
        </section>
      </template>
    </main>
  </div>
</template>
