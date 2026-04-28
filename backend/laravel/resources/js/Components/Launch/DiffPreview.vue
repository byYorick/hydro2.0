<template>
  <div class="flex flex-col gap-2">
    <div
      v-if="!hasChanges"
      class="px-3 py-3 rounded-md border border-dashed border-[var(--border-strong)] bg-[var(--bg-elevated)] text-xs text-[var(--text-muted)] text-center"
    >
      Overrides не заданы — применятся значения рецепта.
    </div>

    <div
      v-else
      class="border border-[var(--border-muted)] rounded-lg overflow-hidden bg-[var(--bg-surface)]"
    >
      <div class="flex items-center justify-between gap-2 px-3 py-2 border-b border-[var(--border-muted)] bg-[var(--bg-elevated)]">
        <span class="text-xs font-medium text-[var(--text-muted)]">Изменения logic profile</span>
        <span class="font-mono text-[11px] text-brand-ink">{{ diffRows.length }} измен.</span>
      </div>
      <div class="overflow-x-auto">
        <div class="min-w-[760px]">
          <div
            class="grid items-center px-3 py-2 bg-[var(--bg-elevated)] text-[11px] uppercase tracking-wider text-[var(--text-dim)]"
            style="grid-template-columns: 24px 1.4fr 1fr 1fr"
          >
            <span aria-hidden="true"></span>
            <span>Путь</span>
            <span>Текущее</span>
            <span>Новое</span>
          </div>
          <div
            v-for="row in diffRows"
            :key="row.path"
            :data-op="row.op"
            class="grid items-center px-3 py-1.5 border-t border-[var(--border-muted)] hover:bg-[var(--bg-elevated)]"
            style="grid-template-columns: 24px 1.4fr 1fr 1fr"
          >
            <span class="flex items-center">
              <span
                class="inline-block w-2 h-2 rounded-sm"
                :class="dotClass(row.op)"
              ></span>
            </span>
            <span
              class="min-w-0 font-mono text-[11px] text-[var(--text-muted)] truncate"
              :title="row.path"
            >{{ row.path }}</span>
            <span
              class="min-w-0 font-mono text-xs text-[var(--text-dim)] break-all"
              :class="row.op === 'replace' ? 'line-through' : ''"
            >
              {{ row.op === 'add' ? '—' : formatValue(row.previous) }}
            </span>
            <span class="min-w-0 font-mono text-xs text-brand-ink break-all">
              {{ row.op === 'remove' ? '—' : formatValue(row.next) }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { compare, type Operation } from 'fast-json-patch'
import { computed } from 'vue'

interface DiffRow {
  path: string
  op: 'add' | 'remove' | 'replace'
  previous: unknown
  next: unknown
}

const props = defineProps<{
  current: Record<string, unknown>
  next: Record<string, unknown>
}>()

const diffRows = computed<DiffRow[]>(() => {
  const ops = compare(stripUndefined(props.current), stripUndefined(props.next))
  return ops
    .filter(
      (op): op is Extract<Operation, { op: 'add' | 'remove' | 'replace' }> =>
        ['add', 'remove', 'replace'].includes(op.op),
    )
    .map((op) => {
      const prev = resolve(props.current, op.path)
      const nxt = 'value' in op ? (op as unknown as { value: unknown }).value : undefined
      return {
        path: op.path,
        op: op.op,
        previous: prev,
        next: nxt,
      }
    })
})

const hasChanges = computed(() => diffRows.value.length > 0)

function stripUndefined<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) return obj.map(stripUndefined) as unknown as T
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    if (v === undefined) continue
    out[k] = stripUndefined(v)
  }
  return out as T
}

function resolve(obj: Record<string, unknown>, pointer: string): unknown {
  if (!pointer.startsWith('/')) return undefined
  const parts = pointer
    .slice(1)
    .split('/')
    .map((p) => p.replace(/~1/g, '/').replace(/~0/g, '~'))
  let cur: unknown = obj
  for (const part of parts) {
    if (cur && typeof cur === 'object' && part in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[part]
    } else {
      return undefined
    }
  }
  return cur
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function dotClass(op: 'add' | 'remove' | 'replace'): string {
  if (op === 'add') return 'bg-growth'
  if (op === 'remove') return 'bg-alert'
  return 'bg-warn'
}
</script>
