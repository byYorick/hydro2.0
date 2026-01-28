<template>
  <div
    class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden bg-[color:var(--bg-surface)]"
    :data-testid="tableTestId"
  >
    <div :class="containerClasses">
      <table :class="tableClasses">
        <thead class="bg-[color:var(--bg-surface-strong)] text-[color:var(--text-muted)]">
          <tr>
            <th
              v-for="column in columns"
              :key="column.key"
              class="px-3 py-2 text-left font-semibold border-b border-[color:var(--border-muted)]"
              :class="[column.headerClass, alignClass(column.align)]"
            >
              <button
                v-if="column.sortable"
                type="button"
                class="inline-flex items-center gap-1 hover:text-[color:var(--text-primary)]"
                @click="toggleSort(column)"
              >
                <span>{{ column.label }}</span>
                <span class="text-xs">
                  {{ sortIcon(column) }}
                </span>
              </button>
              <span v-else>
                <slot
                  :name="`header-${column.key}`"
                  :column="column"
                >
                  {{ column.label }}
                </slot>
              </span>
            </th>
            <th
              v-if="hasRowActions"
              class="px-3 py-2 text-left font-semibold border-b border-[color:var(--border-muted)]"
              :class="actionsHeaderClass"
            >
              {{ actionsLabel }}
            </th>
          </tr>
        </thead>

        <tbody v-if="!useVirtual">
          <tr v-if="loading">
            <td
              :colspan="columns.length + (hasRowActions ? 1 : 0)"
              class="px-3 py-6"
            >
              <SkeletonBlock
                :lines="skeletonLines"
                line-height="0.75rem"
              />
            </td>
          </tr>
          <tr v-else-if="sortedRows.length === 0">
            <td
              :colspan="columns.length + (hasRowActions ? 1 : 0)"
              class="px-3 py-6"
            >
              <slot name="empty">
                <EmptyState
                  :title="emptyTitle"
                  :description="emptyDescription"
                  container-class="py-0"
                />
              </slot>
            </td>
          </tr>
          <tr
            v-for="(row, index) in sortedRows"
            v-else
            :key="getRowKey(row, index)"
            :data-testid="getRowTestId(row, index)"
            class="border-b border-[color:var(--border-muted)] transition-colors"
            :class="[stripedClass(index), rowClass(row, index), rowClickableClass]"
            @click="emitRowClick(row)"
          >
            <td
              v-for="column in columns"
              :key="column.key"
              class="px-3 py-2 text-[color:var(--text-muted)]"
              :class="[column.class, alignClass(column.align)]"
            >
              <slot
                :name="`cell-${column.key}`"
                :row="row"
                :value="getCellValue(row, column)"
                :column="column"
              >
                {{ formatCellValue(getCellValue(row, column)) }}
              </slot>
            </td>
            <td
              v-if="hasRowActions"
              class="px-3 py-2"
            >
              <slot
                name="row-actions"
                :row="row"
                :index="index"
              ></slot>
            </td>
          </tr>
        </tbody>
        <VirtualTable
          v-else
          tag="tbody"
          item-tag="tr"
          :items="sortedRows"
          :item-size="virtualItemSize"
          :key-field="rowKeyField"
          :container-class="containerClass"
        >
          <template #default="{ item, index }">
            <tr
              :key="getRowKey(item, index)"
              :data-testid="getRowTestId(item, index)"
              class="border-b border-[color:var(--border-muted)] transition-colors"
              :class="[stripedClass(index), rowClass(item, index), rowClickableClass]"
              @click="emitRowClick(item)"
            >
              <td
                v-for="column in columns"
                :key="column.key"
                class="px-3 py-2 text-[color:var(--text-muted)]"
                :class="[column.class, alignClass(column.align)]"
              >
                <slot
                  :name="`cell-${column.key}`"
                  :row="item"
                  :value="getCellValue(item, column)"
                  :column="column"
                >
                  {{ formatCellValue(getCellValue(item, column)) }}
                </slot>
              </td>
              <td
                v-if="hasRowActions"
                class="px-3 py-2"
              >
                <slot
                  name="row-actions"
                  :row="item"
                  :index="index"
                ></slot>
              </td>
            </tr>
          </template>
        </VirtualTable>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, useSlots } from 'vue'
import EmptyState from '@/Components/EmptyState.vue'
import SkeletonBlock from '@/Components/SkeletonBlock.vue'
import VirtualTable from '@/Components/VirtualTable.vue'

type SortDirection = 'asc' | 'desc' | null

export interface DataTableColumn<Row = any> {
  key: string
  label: string
  sortable?: boolean
  sortAccessor?: (row: Row) => unknown
  class?: string
  headerClass?: string
  align?: 'left' | 'center' | 'right'
}

interface Props<Row = any> {
  columns: DataTableColumn<Row>[]
  rows: Row[]
  loading?: boolean
  tableTestId?: string
  rowTestIdPrefix?: string
  rowTestId?: (row: Row, index: number) => string
  rowKey?: string | ((row: Row, index: number) => string | number)
  rowClass?: (row: Row, index: number) => string
  rowClickable?: boolean
  containerClass?: string
  actionsLabel?: string
  actionsHeaderClass?: string
  striped?: boolean
  emptyTitle?: string
  emptyDescription?: string
  virtualize?: boolean
  virtualizeThreshold?: number
  virtualItemSize?: number
  skeletonLines?: number
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  tableTestId: undefined,
  rowTestIdPrefix: '',
  rowKey: 'id',
  rowClass: undefined,
  rowClickable: false,
  containerClass: '',
  actionsLabel: 'Действия',
  actionsHeaderClass: '',
  striped: true,
  emptyTitle: 'Нет данных',
  emptyDescription: 'Элементы появятся позже.',
  virtualize: false,
  virtualizeThreshold: 120,
  virtualItemSize: 48,
  skeletonLines: 5,
})

const emit = defineEmits<{
  (e: 'row-click', row: any): void
}>()

const sortKey = ref<string | null>(null)
const sortDirection = ref<SortDirection>(null)

const slots = useSlots()
const hasRowActions = computed(() => Boolean(slots['row-actions']))
const rowClickableClass = computed(() => (props.rowClickable ? 'cursor-pointer' : ''))

const rowKeyField = computed(() => (typeof props.rowKey === 'string' ? props.rowKey : 'id'))

const sortedRows = computed(() => {
  if (!sortKey.value || !sortDirection.value) {
    return props.rows
  }

  const column = props.columns.find((c) => c.key === sortKey.value)
  const accessor = column?.sortAccessor
  const direction = sortDirection.value

  return [...props.rows].sort((a, b) => {
    const rawA = accessor ? accessor(a) : getCellValue(a, column)
    const rawB = accessor ? accessor(b) : getCellValue(b, column)

    if (rawA == null && rawB == null) return 0
    if (rawA == null) return direction === 'asc' ? 1 : -1
    if (rawB == null) return direction === 'asc' ? -1 : 1

    if (typeof rawA === 'number' && typeof rawB === 'number') {
      return direction === 'asc' ? rawA - rawB : rawB - rawA
    }

    const strA = String(rawA).toLowerCase()
    const strB = String(rawB).toLowerCase()
    if (strA === strB) return 0
    return direction === 'asc' ? (strA > strB ? 1 : -1) : (strA < strB ? 1 : -1)
  })
})

const useVirtual = computed(() => {
  return props.virtualize && !props.loading && sortedRows.value.length > props.virtualizeThreshold
})

const containerClasses = computed(() => {
  return [useVirtual.value ? 'overflow-hidden' : 'overflow-auto', props.containerClass]
})

const tableClasses = computed(() => {
  return ['min-w-full text-sm', useVirtual.value ? 'h-full' : '']
})

const alignClass = (align?: 'left' | 'center' | 'right'): string => {
  if (align === 'center') return 'text-center'
  if (align === 'right') return 'text-right'
  return 'text-left'
}

const stripedClass = (index: number): string => {
  if (!props.striped) return ''
  return index % 2 === 0 ? 'bg-[color:var(--bg-surface-strong)]' : 'bg-[color:var(--bg-surface)]'
}

const rowClass = (row: any, index: number): string => {
  return props.rowClass ? props.rowClass(row, index) : ''
}

const formatCellValue = (value: unknown): string => {
  if (value === null || value === undefined) return '—'
  return String(value)
}

const getCellValue = (row: any, column?: DataTableColumn): unknown => {
  if (!column) return ''
  const key = column.key
  if (!key) return ''
  if (key.includes('.')) {
    return key.split('.').reduce((acc: any, part) => (acc ? acc[part] : undefined), row)
  }
  return row?.[key]
}

const getRowKey = (row: any, index: number): string | number => {
  if (typeof props.rowKey === 'function') {
    return props.rowKey(row, index)
  }
  const key = props.rowKey
  return row?.[key] ?? index
}

const getRowTestId = (row: any, index: number): string | undefined => {
  if (props.rowTestId) {
    return props.rowTestId(row, index)
  }
  if (!props.rowTestIdPrefix) return undefined
  return `${props.rowTestIdPrefix}${getRowKey(row, index)}`
}

const toggleSort = (column: DataTableColumn): void => {
  if (!column.sortable) return

  if (sortKey.value !== column.key) {
    sortKey.value = column.key
    sortDirection.value = 'asc'
    return
  }

  if (sortDirection.value === 'asc') {
    sortDirection.value = 'desc'
    return
  }

  sortDirection.value = null
  sortKey.value = null
}

const sortIcon = (column: DataTableColumn): string => {
  if (sortKey.value !== column.key || !sortDirection.value) return '↕'
  return sortDirection.value === 'asc' ? '↑' : '↓'
}

const emitRowClick = (row: any): void => {
  if (!props.rowClickable) return
  emit('row-click', row)
}
</script>
