<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-3" data-testid="config-changes-timeline">
    <header class="flex items-center justify-between gap-2">
      <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
        История изменений конфигурации
      </h3>
      <div class="flex items-center gap-2 text-xs">
        <select
          v-model="selectedNamespace"
          class="text-xs px-2 py-1 rounded border border-[color:var(--border-muted)] bg-[color:var(--surface-card)]"
          data-testid="config-changes-namespace"
          @change="reload"
        >
          <option value="">все namespace</option>
          <option value="zone.config_mode">zone.config_mode</option>
          <option value="zone.correction">zone.correction</option>
          <option value="recipe.phase">recipe.phase</option>
        </select>
        <button
          type="button"
          class="text-xs px-2 py-1 rounded border border-[color:var(--border-muted)]"
          @click="reload"
        >Обновить</button>
      </div>
    </header>

    <p
      v-if="loading"
      class="text-xs text-[color:var(--text-dim)] animate-pulse"
    >загрузка...</p>
    <p
      v-else-if="error"
      class="text-xs text-rose-500 dark:text-rose-400"
    >{{ error }}</p>
    <p
      v-else-if="changes.length === 0"
      class="text-xs text-[color:var(--text-dim)]"
    >Изменений нет.</p>

    <ul
      v-else
      class="space-y-2"
      data-testid="config-changes-list"
    >
      <li
        v-for="entry in changes"
        :key="entry.id"
        class="border border-[color:var(--border-muted)] rounded-lg p-2 bg-[color:var(--surface-muted)]/40"
      >
        <div class="flex flex-wrap items-center gap-2 text-xs">
          <Badge
            :variant="namespaceVariant(entry.namespace)"
          >{{ entry.namespace }}</Badge>
          <span class="text-[color:var(--text-muted)]">rev {{ entry.revision }}</span>
          <span class="text-[color:var(--text-dim)]">
            {{ formatDate(entry.created_at) }}
          </span>
          <span
            v-if="entry.user_id"
            class="text-[color:var(--text-dim)]"
          >user #{{ entry.user_id }}</span>
          <span
            v-else
            class="text-[color:var(--text-dim)]"
          >(system)</span>
        </div>
        <p
          v-if="entry.reason"
          class="text-xs text-[color:var(--text-primary)] mt-1"
        >
          {{ entry.reason }}
        </p>
        <details
          v-if="hasDiff(entry.diff)"
          class="mt-1"
        >
          <summary class="text-xs cursor-pointer text-[color:var(--text-muted)]">
            diff
          </summary>
          <pre class="text-xs mt-1 p-2 rounded bg-[color:var(--surface-card)] overflow-auto max-h-48">{{ JSON.stringify(entry.diff, null, 2) }}</pre>
        </details>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import Badge from '@/Components/Badge.vue'
import type { BadgeVariant } from '@/Components/Badge.vue'
import {
  type ConfigChangeEntry,
  zoneConfigModeApi,
} from '@/services/api/zoneConfigMode'

interface Props {
  zoneId: number
  /** force-reload trigger; parent bumps to invalidate cache */
  reloadKey?: number
}

const props = withDefaults(defineProps<Props>(), { reloadKey: 0 })

const selectedNamespace = ref<string>('')
const changes = ref<ConfigChangeEntry[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function reload() {
  loading.value = true
  error.value = null
  try {
    const resp = await zoneConfigModeApi.changes(
      props.zoneId,
      selectedNamespace.value || undefined,
    )
    changes.value = resp.changes
  } catch (err: unknown) {
    error.value = extractError(err) ?? 'Ошибка загрузки истории'
  } finally {
    loading.value = false
  }
}

function namespaceVariant(namespace: string): BadgeVariant {
  if (namespace === 'zone.config_mode') return 'info'
  if (namespace === 'zone.correction') return 'warning'
  if (namespace === 'recipe.phase') return 'secondary'
  return 'neutral'
}

function formatDate(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

function hasDiff(diff: Record<string, unknown>): boolean {
  return diff !== null && typeof diff === 'object' && Object.keys(diff).length > 0
}

function extractError(err: unknown): string | null {
  if (typeof err === 'object' && err !== null) {
    const anyErr = err as { response?: { data?: { message?: string } } }
    return anyErr.response?.data?.message ?? null
  }
  return null
}

onMounted(reload)
watch(() => props.zoneId, reload)
watch(() => props.reloadKey, reload)
</script>
