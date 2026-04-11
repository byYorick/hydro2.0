<template>
  <AppLayout>
    <div class="space-y-4">
      <PageHeader
        title="Алерты"
        subtitle="Операционные предупреждения и статус подтверждения."
        eyebrow="мониторинг"
      />

      <FilterBar>
        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Статус:</label>
          <select
            v-model="statusFilter"
            data-testid="alerts-filter-active"
            class="input-select flex-1 sm:w-auto sm:min-w-[160px]"
          >
            <option value="active">
              Только активные
            </option>
            <option value="resolved">
              Только решённые
            </option>
            <option value="all">
              Все
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Зона:</label>
          <select
            v-model="zoneIdFilter"
            data-testid="alerts-filter-zone"
            class="input-select flex-1 sm:w-auto sm:min-w-[180px]"
          >
            <option value="">
              Все зоны
            </option>
            <option
              v-for="zone in zoneOptions"
              :key="zone.id"
              :value="String(zone.id)"
            >
              {{ zone.name }}
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Источник:</label>
          <select
            v-model="sourceFilter"
            class="input-select flex-1 sm:w-auto sm:min-w-[150px]"
          >
            <option value="">
              Все
            </option>
            <option value="biz">
              biz
            </option>
            <option value="infra">
              infra
            </option>
            <option value="node">
              node
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Критичность:</label>
          <select
            v-model="severityFilter"
            class="input-select flex-1 sm:w-auto sm:min-w-[150px]"
          >
            <option value="">
              Все
            </option>
            <option value="critical">
              critical
            </option>
            <option value="error">
              error
            </option>
            <option value="warning">
              warning
            </option>
            <option value="info">
              info
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Категория:</label>
          <select
            v-model="categoryFilter"
            class="input-select flex-1 sm:w-auto sm:min-w-[170px]"
          >
            <option value="">
              Все
            </option>
            <option value="agronomy">
              agronomy
            </option>
            <option value="operations">
              operations
            </option>
            <option value="infrastructure">
              infrastructure
            </option>
            <option value="node">
              node
            </option>
            <option value="safety">
              safety
            </option>
            <option value="config">
              config
            </option>
            <option value="other">
              other
            </option>
          </select>
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Поиск:</label>
          <input
            v-model="searchQuery"
            placeholder="тип / код / сообщение"
            class="input-field flex-1 sm:w-60"
          />
        </div>

        <div class="flex items-center gap-2 flex-1 sm:flex-none">
          <label class="text-sm text-[color:var(--text-muted)] shrink-0">Подавление:</label>
          <input
            v-model.number="toastSuppressionSec"
            type="number"
            min="0"
            max="600"
            step="5"
            class="input-field w-24"
          />
          <span class="text-xs text-[color:var(--text-dim)]">сек</span>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
            :class="recentOnly
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="recentOnly = !recentOnly"
          >
            24ч
          </button>
          <button
            type="button"
            class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
            :class="alarmsOnly
              ? 'border-[color:var(--accent-amber)] text-[color:var(--accent-amber)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="alarmsOnly = !alarmsOnly"
          >
            Тревоги
          </button>
        </div>

        <template #actions>
          <div
            v-if="selectedCount"
            class="text-xs text-[color:var(--text-dim)]"
          >
            Выбрано: {{ selectedCount }}
          </div>
          <Button
            size="sm"
            variant="outline"
            :disabled="isRefreshing"
            @click="loadAlerts"
          >
            {{ isRefreshing ? 'Обновляем...' : 'Обновить' }}
          </Button>
          <Button
            v-if="selectedCount"
            size="sm"
            variant="secondary"
            @click="bulkConfirm.open = true"
          >
            Подтвердить выбранные
          </Button>
        </template>
      </FilterBar>

      <DataTableV2
        :columns="columns"
        :rows="filteredAlerts"
        :loading="isInitialLoading"
        table-test-id="alerts-table"
        row-test-id-prefix="alert-row-"
        container-class="h-[720px]"
        :virtualize="true"
        :virtualize-threshold="100"
        :virtual-item-size="52"
        row-clickable
        @row-click="openDetails"
      >
        <template #header-select>
          <input
            type="checkbox"
            class="h-4 w-4 accent-[color:var(--accent-cyan)]"
            :checked="allVisibleSelected"
            :disabled="selectableAlerts.length === 0"
            @change="toggleSelectAll"
            @click.stop
          />
        </template>

        <template #cell-select="{ row }">
          <input
            type="checkbox"
            class="h-4 w-4 accent-[color:var(--accent-cyan)]"
            :checked="selectedIds.has(row.id)"
            :disabled="isResolved(row)"
            @change="toggleSelection(row)"
            @click.stop
          />
        </template>

        <template #cell-zone="{ row }">
          <span class="truncate block max-w-[220px]">
            {{ row.zone?.name || (row.zone_id ? `Zone #${row.zone_id}` : '-') }}
          </span>
        </template>

        <template #cell-type="{ row }">
          <span class="truncate block max-w-[320px]">
            {{ getAlertMeta(row).title }}
          </span>
        </template>

        <template #cell-created_at="{ row }">
          {{ formatDate(row.created_at) }}
        </template>

        <template #cell-status="{ row }">
          {{ translateStatus(row.status) }}
        </template>

        <template #row-actions="{ row }">
          <Button
            size="sm"
            variant="secondary"
            :data-testid="`alert-resolve-btn-${row.id}`"
            :disabled="isResolved(row)"
            @click.stop="openResolve(row)"
          >
            Подтвердить
          </Button>
        </template>
      </DataTableV2>
    </div>

    <ConfirmModal
      :open="confirm.open"
      title="Подтвердить алерт"
      message="Вы уверены, что алерт будет помечен как решённый?"
      :loading="confirm.loading"
      @close="closeConfirm"
      @confirm="doResolve"
    />

    <ConfirmModal
      :open="bulkConfirm.open"
      title="Подтвердить выбранные"
      message="Подтвердить выбранные алерты?"
      :loading="bulkConfirm.loading"
      @close="bulkConfirm.open = false"
      @confirm="resolveSelected"
    />

    <div
      v-if="selectedAlert"
      class="fixed inset-0 z-50"
    >
      <div
        class="absolute inset-0 bg-[color:var(--bg-main)] opacity-70"
        @click="closeDetails"
      ></div>
      <div
        class="absolute right-0 top-0 h-full w-full max-w-md bg-[color:var(--bg-surface-strong)] border-l border-[color:var(--border-muted)] p-5 overflow-y-auto"
      >
        <div class="flex items-center justify-between mb-4">
          <div class="text-base font-semibold">
            Детали алерта
          </div>
          <Button
            size="sm"
            variant="outline"
            @click="closeDetails"
          >
            Закрыть
          </Button>
        </div>
        <div class="space-y-4 text-sm text-[color:var(--text-muted)]">
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Тип
            </div>
            <div class="text-[color:var(--text-primary)] font-semibold">
              {{ getAlertMeta(selectedAlert).title }}
            </div>
          </div>
          <div
            v-if="selectedAlert.code"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Код
            </div>
            <div class="text-[color:var(--text-primary)] font-semibold">
              {{ selectedAlert.code }}
            </div>
          </div>
          <div
            v-if="selectedAlert.source"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Источник
            </div>
            <div class="text-[color:var(--text-primary)] font-semibold">
              {{ selectedAlert.source }}
            </div>
          </div>
          <div
            v-if="selectedAlertMessage"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Сообщение
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ selectedAlertMessage }}
            </div>
          </div>
          <div
            v-if="getAlertMeta(selectedAlert).recommendation"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Рекомендация
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ getAlertMeta(selectedAlert).recommendation }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Статус
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ translateStatus(selectedAlert.status) }}
            </div>
          </div>
          <div class="space-y-1">
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Создан
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ formatDate(selectedAlert.created_at) }}
            </div>
          </div>
          <div
            v-if="selectedAlert.resolved_at"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Подтвержден
            </div>
            <div class="text-[color:var(--text-primary)]">
              {{ formatDate(selectedAlert.resolved_at) }}
            </div>
          </div>
          <div
            v-if="selectedAlert.zone_id"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Зона
            </div>
            <Link
              class="text-[color:var(--accent-cyan)] font-semibold hover:underline"
              :href="`/zones/${selectedAlert.zone_id}`"
            >
              {{ selectedAlert.zone?.name || `Zone #${selectedAlert.zone_id}` }}
            </Link>
          </div>
          <div
            v-if="detailsJson"
            class="space-y-1"
          >
            <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">
              Детали
            </div>
            <pre class="text-xs whitespace-pre-wrap rounded-lg border border-[color:var(--border-muted)] p-3 bg-[color:var(--bg-surface)]">
{{ detailsJson }}
            </pre>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import DataTableV2 from '@/Components/DataTableV2.vue'
import FilterBar from '@/Components/FilterBar.vue'
import PageHeader from '@/Components/PageHeader.vue'
import { translateStatus } from '@/utils/i18n'
import { useAlertsPage, type AlertRecord } from '@/composables/useAlertsPage'

const {
  statusFilter,
  zoneIdFilter,
  sourceFilter,
  severityFilter,
  categoryFilter,
  searchQuery,
  recentOnly,
  alarmsOnly,
  filteredAlerts,
  zoneOptions,
  selectableAlerts,
  isRefreshing,
  isInitialLoading,
  selectedIds,
  selectedCount,
  allVisibleSelected,
  toggleSelection,
  toggleSelectAll,
  confirm,
  bulkConfirm,
  openResolve,
  closeConfirm,
  doResolve,
  resolveSelected,
  selectedAlert,
  selectedAlertMessage,
  detailsJson,
  openDetails,
  closeDetails,
  toastSuppressionSec,
  isResolved,
  formatDate,
  getAlertMeta,
  loadAlerts,
} = useAlertsPage()

const columns = [
  { key: 'select', label: '', sortable: false, headerClass: 'w-10' },
  { key: 'type', label: 'Тип', sortable: true },
  {
    key: 'zone',
    label: 'Зона',
    sortable: true,
    sortAccessor: (alert: AlertRecord) => alert.zone?.name || `Zone #${alert.zone_id}`,
  },
  {
    key: 'created_at',
    label: 'Время',
    sortable: true,
    sortAccessor: (alert: AlertRecord) => new Date(alert.created_at).getTime(),
  },
  { key: 'status', label: 'Статус', sortable: true },
]
</script>
