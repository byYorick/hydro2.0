<template>
    <div class="diff-preview">
        <header class="diff-preview__header">
            <h4 class="diff-preview__title">Diff overrides → zone.logic_profile</h4>
            <p class="diff-preview__hint">
                Только поля из overrides будут применены к zone.logic_profile. Остальные поля зоны
                сохранятся без изменений.
            </p>
        </header>

        <div v-if="!hasChanges" class="diff-preview__empty">
            Overrides не заданы — применятся значения рецепта.
        </div>

        <table v-else class="diff-preview__table">
            <thead>
                <tr>
                    <th>Путь</th>
                    <th>Было</th>
                    <th>Станет</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="row in diffRows" :key="row.path" :class="`diff-preview__row--${row.op}`">
                    <td>
                        <code>{{ row.path }}</code>
                    </td>
                    <td>
                        <code v-if="row.op !== 'add'">{{ formatValue(row.previous) }}</code>
                        <span v-else>—</span>
                    </td>
                    <td>
                        <code v-if="row.op !== 'remove'">{{ formatValue(row.next) }}</code>
                        <span v-else>—</span>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</template>

<script setup lang="ts">
import { compare, type Operation } from 'fast-json-patch';
import { computed } from 'vue';

interface DiffRow {
    path: string;
    op: 'add' | 'remove' | 'replace';
    previous: unknown;
    next: unknown;
}

interface Props {
    current: Record<string, unknown>;
    next: Record<string, unknown>;
}

const props = defineProps<Props>();

const diffRows = computed<DiffRow[]>(() => {
    const ops = compare(stripUndefined(props.current), stripUndefined(props.next));
    return ops
        .filter((op): op is Extract<Operation, { op: 'add' | 'remove' | 'replace' }> =>
            ['add', 'remove', 'replace'].includes(op.op),
        )
        .map((op) => {
            const prev = resolve(props.current, op.path);
            const nxt = 'value' in op ? (op as unknown as { value: unknown }).value : undefined;
            return {
                path: op.path,
                op: op.op,
                previous: prev,
                next: nxt,
            };
        });
});

const hasChanges = computed(() => diffRows.value.length > 0);

function stripUndefined<T>(obj: T): T {
    if (obj === null || typeof obj !== 'object') return obj;
    if (Array.isArray(obj)) {
        return obj.map(stripUndefined) as unknown as T;
    }
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
        if (v === undefined) continue;
        out[k] = stripUndefined(v);
    }
    return out as T;
}

function resolve(obj: Record<string, unknown>, pointer: string): unknown {
    if (!pointer.startsWith('/')) return undefined;
    const parts = pointer
        .slice(1)
        .split('/')
        .map((p) => p.replace(/~1/g, '/').replace(/~0/g, '~'));
    let cur: unknown = obj;
    for (const part of parts) {
        if (cur && typeof cur === 'object' && part in (cur as Record<string, unknown>)) {
            cur = (cur as Record<string, unknown>)[part];
        } else {
            return undefined;
        }
    }
    return cur;
}

function formatValue(v: unknown): string {
    if (v === null || v === undefined) return '—';
    if (typeof v === 'object') return JSON.stringify(v);
    return String(v);
}
</script>

<style scoped>
.diff-preview {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.diff-preview__title {
    font-size: 0.875rem;
    font-weight: 600;
    margin: 0;
}

.diff-preview__hint {
    font-size: 0.75rem;
    opacity: 0.75;
    margin: 0;
}

.diff-preview__empty {
    padding: 0.75rem;
    font-size: 0.85rem;
    background: rgba(148, 163, 184, 0.08);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 0.375rem;
    opacity: 0.8;
}

.diff-preview__table {
    border-collapse: collapse;
    font-size: 0.8rem;
    width: 100%;
}

.diff-preview__table th,
.diff-preview__table td {
    text-align: left;
    padding: 0.35rem 0.5rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    vertical-align: top;
}

.diff-preview__table th {
    font-weight: 600;
    opacity: 0.7;
    font-size: 0.7rem;
    text-transform: uppercase;
}

.diff-preview__row--add td { background: rgba(34, 197, 94, 0.08); }
.diff-preview__row--remove td { background: rgba(239, 68, 68, 0.08); }
.diff-preview__row--replace td { background: rgba(56, 189, 248, 0.08); }

.diff-preview code {
    font-family: ui-monospace, monospace;
    font-size: 0.75rem;
}
</style>
