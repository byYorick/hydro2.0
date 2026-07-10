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
          <button
            type="button"
            class="h-9 px-3 rounded-lg border text-xs font-semibold transition-colors"
            :class="processStoppingOnly
              ? 'border-[color:var(--accent-red)] text-[color:var(--accent-red)] bg-[color:var(--bg-elevated)]'
              : 'border-[color:var(--border-muted)] text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="processStoppingOnly = !processStoppingOnly"
          >
            Останавливают процесс
          </button>
        </div>

        <template #actions>
          <div
            v-if="selectedCount"
            class="text-xs text-[color:var(--text-dim)]"
          >
            Выбрано: {{ selectedCount }}
          </div>
          <label
            v-if="selectableAlerts.length"
            class="flex items-center gap-2 text-xs text-[color:var(--text-dim)] cursor-pointer select-none"
            data-testid="alerts-select-all"
          >
            <input
              type="checkbox"
              class="h-4 w-4 accent-[color:var(--accent-cyan)]"
              :checked="allVisibleSelected"
              @change="toggleSelectAll"
            />
            Выбрать все видимые
          </label>
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

      <div
        v-if="!isInitialLoading && groupedAlertSections.length > 0"
        class="flex flex-wrap items-center gap-2"
        data-testid="alerts-section-counts"
      >
        <button
          v-if="alertSectionCounts.automation_block > 0"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] px-2.5 py-1 text-xs font-semibold text-[color:var(--badge-danger-text)] transition-opacity hover:opacity-90"
          data-testid="alerts-count-automation-block"
          @click="scrollToAlertSection('automation_block')"
        >
          <span>{{ PROCESS_STOPPING_SECTION_TITLE.automation_block }}</span>
          <Badge
            variant="danger"
            size="xs"
          >
            {{ alertSectionCounts.automation_block }}
          </Badge>
        </button>
        <button
          v-if="alertSectionCounts.safety > 0"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] px-2.5 py-1 text-xs font-semibold text-[color:var(--badge-warning-text)] transition-opacity hover:opacity-90"
          data-testid="alerts-count-safety"
          @click="scrollToAlertSection('safety')"
        >
          <span>{{ PROCESS_STOPPING_SECTION_TITLE.safety }}</span>
          <Badge
            variant="warning"
            size="xs"
          >
            {{ alertSectionCounts.safety }}
          </Badge>
        </button>
        <button
          v-if="alertSectionCounts.other_active > 0"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-2.5 py-1 text-xs font-semibold text-[color:var(--text-primary)] transition-opacity hover:opacity-90"
          data-testid="alerts-count-other"
          @click="scrollToAlertSection('other_active')"
        >
          <span>{{ PROCESS_STOPPING_SECTION_TITLE.other_active }}</span>
          <Badge
            variant="neutral"
            size="xs"
          >
            {{ alertSectionCounts.other_active }}
          </Badge>
        </button>
        <button
          v-if="alertSectionCounts.activeTotal > 0"
          type="button"
          class="inline-flex items-center gap-1.5 rounded-full border border-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)] px-2.5 py-1 text-xs font-semibold text-[color:var(--accent-cyan)] transition-opacity hover:opacity-90"
          data-testid="alerts-count-active-total"
          @click="scrollToFirstActiveSection"
        >
          <span>Активные</span>
          <Badge
            variant="info"
            size="xs"
          >
            {{ alertSectionCounts.activeTotal }}
          </Badge>
        </button>
      </div>

      <div
        data-testid="alerts-table"
        class="space-y-4"
      >
        <DataTableV2
          v-if="isInitialLoading"
          :columns="columns"
          :rows="[]"
          :loading="true"
          table-test-id="alerts-table-loading"
          container-class="h-[240px]"
        />

        <div
          v-else-if="groupedAlertSections.length === 0"
          class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] px-4 py-8 text-center"
        >
          <div class="text-sm font-semibold text-[color:var(--text-primary)]">
            Алерты по текущим фильтрам не найдены
          </div>
          <div class="mt-1 text-xs text-[color:var(--text-dim)]">
            Измените фильтры или обновите список.
          </div>
        </div>

        <template v-else>
          <section
            v-for="section in groupedAlertSections"
            :key="section.key"
            class="overflow-hidden rounded-xl border bg-[color:var(--bg-surface)]"
            :class="sectionShellClass(section.tone)"
            :data-testid="`alerts-section-${section.key}`"
          >
            <div
              class="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-3"
              :class="sectionHeaderClass(section.tone)"
            >
              <div class="flex items-center gap-2">
                <span class="text-sm font-semibold">
                  {{ section.title }}
                </span>
                <Badge
                  :variant="sectionBadgeVariant(section.tone)"
                  size="sm"
                >
                  {{ section.items.length }}
                </Badge>
              </div>
              <span class="text-xs text-[color:var(--text-dim)]">
                {{ sectionHint(section.key) }}
              </span>
            </div>

            <div
              v-for="zoneGroup in sectionZoneGroups(section)"
              :key="`${section.key}-${zoneGroup.testIdSuffix}`"
              :data-testid="zoneGroup.showHeader ? `alerts-zone-group-${zoneGroup.testIdSuffix}` : undefined"
            >
              <div
                v-if="zoneGroup.showHeader"
                class="flex items-center gap-2 border-t border-b border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] px-4 py-2"
              >
                <span class="text-xs font-semibold uppercase tracking-wide text-[color:var(--text-muted)]">
                  {{ zoneGroup.zoneName }}
                </span>
                <Badge
                  :variant="sectionBadgeVariant(section.tone)"
                  size="xs"
                >
                  {{ zoneGroup.items.length }}
                </Badge>
              </div>

              <DataTableV2
                :columns="columns"
                :rows="zoneGroup.items"
                :loading="false"
                :table-test-id="zoneGroupTableTestId(section.key, zoneGroup.testIdSuffix)"
                row-test-id-prefix="alert-row-"
                container-class="max-h-[420px]"
                :virtualize="true"
                :virtualize-threshold="100"
                :virtual-item-size="56"
                :row-class="alertRowClass"
                row-clickable
                @row-click="openDetails"
              >
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

              <template #cell-severity="{ row }">
                <div class="flex items-center gap-2">
                  <span
                    class="h-8 w-1 rounded-full"
                    :class="severityRailClass(row)"
                    aria-hidden="true"
                  ></span>
                  <Badge
                    :variant="severityBadgeVariant(row)"
                    size="sm"
                  >
                    {{ severityLabel(row) }}
                  </Badge>
                </div>
              </template>

              <template #cell-type="{ row }">
                <div class="min-w-0">
                  <span class="truncate block max-w-[320px] text-[color:var(--text-primary)] font-medium">
                    {{ getAlertMeta(row).title }}
                  </span>
                  <span
                    v-if="row.code"
                    class="mt-0.5 block truncate font-mono text-[11px] text-[color:var(--text-dim)]"
                  >
                    {{ row.code }}
                  </span>
                </div>
              </template>

              <template #cell-process="{ row }">
                <Badge
                  v-if="processStoppingKind(row)"
                  variant="danger"
                  size="sm"
                  :data-testid="`alert-process-stop-badge-${row.id}`"
                  :data-process-stopping-kind="processStoppingKind(row)"
                >
                  {{ PROCESS_STOPPING_BADGE_LABEL[processStoppingKind(row)!] }}
                </Badge>
                <span
                  v-else
                  class="text-[color:var(--text-dim)]"
                >
                  —
                </span>
              </template>

              <template #cell-zone="{ row }">
                <Link
                  v-if="row.zone_id"
                  class="truncate block max-w-[220px] text-[color:var(--accent-cyan)] font-medium hover:underline"
                  :href="zoneAlertsTabUrl(row.zone_id)"
                  :data-testid="`alert-zone-link-${row.id}`"
                  @click.stop
                >
                  {{ zoneLabel(row) }}
                </Link>
                <span
                  v-else
                  class="truncate block max-w-[220px]"
                >
                  —
                </span>
              </template>

              <template #cell-created_at="{ row }">
                {{ formatDate(row.created_at) }}
              </template>

              <template #cell-status="{ row }">
                <Badge
                  :variant="statusBadgeVariant(row)"
                  size="sm"
                >
                  {{ translateStatus(row.status) }}
                </Badge>
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
          </section>
        </template>
      </div>
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

    <AlertDetailModal
      :open="Boolean(selectedAlert)"
      :alert="selectedAlert"
      :resolve-loading="confirm.loading"
      @close="closeDetails"
      @resolve="resolveFromDetails"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import type { BadgeVariant } from '@/Components/Badge.vue'
import AlertDetailModal from '@/Components/Alerts/AlertDetailModal.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import DataTableV2 from '@/Components/DataTableV2.vue'
import FilterBar from '@/Components/FilterBar.vue'
import PageHeader from '@/Components/PageHeader.vue'
import { translateStatus } from '@/utils/i18n'
import {
  useAlertsPage,
  type AlertRecord,
  type GroupedAlertSection,
  type GroupedAlertSectionKey,
  type GroupedAlertZoneGroup,
} from '@/composables/useAlertsPage'
import {
  alertBadgeVariant,
  alertSeveritySortWeight,
  normalizeAlertSeverity,
  resolveEffectiveAlertSeverity,
  severityRailClass,
  type NormalizedAlertSeverity,
} from '@/utils/alertMeta'
import {
  alertProcessStoppingKind,
  PROCESS_STOPPING_BADGE_LABEL,
  PROCESS_STOPPING_SECTION_TITLE,
} from '@/utils/automationBlock'
import { zoneAlertsTabUrl } from '@/utils/alertContext'

const {
  statusFilter,
  zoneIdFilter,
  sourceFilter,
  severityFilter,
  categoryFilter,
  searchQuery,
  recentOnly,
  alarmsOnly,
  processStoppingOnly,
  groupedAlertSections,
  alertSectionCounts,
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
  openDetails,
  closeDetails,
  toastSuppressionSec,
  isResolved,
  formatDate,
  getAlertMeta,
  loadAlerts,
} = useAlertsPage()

function zoneLabel(alert: AlertRecord): string {
  return alert.zone?.name || (alert.zone_id ? `Зона #${alert.zone_id}` : '—')
}

function resolveFromDetails(): void {
  if (!selectedAlert.value || isResolved(selectedAlert.value)) return
  openResolve(selectedAlert.value)
}

const columns = [
  { key: 'select', label: '', sortable: false, headerClass: 'w-10' },
  {
    key: 'severity',
    label: 'Критичность',
    sortable: true,
    headerClass: 'w-36',
    sortAccessor: (alert: AlertRecord) => severitySortWeight(alert),
  },
  { key: 'type', label: 'Тип', sortable: true },
  {
    key: 'process',
    label: 'Стоп',
    sortable: true,
    headerClass: 'w-32',
    sortAccessor: (alert: AlertRecord) => processStoppingKind(alert) || '',
  },
  {
    key: 'zone',
    label: 'Зона',
    sortable: true,
    sortAccessor: (alert: AlertRecord) => alert.zone?.name || `Зона #${alert.zone_id}`,
  },
  {
    key: 'created_at',
    label: 'Время',
    sortable: true,
    sortAccessor: (alert: AlertRecord) => new Date(alert.created_at).getTime(),
  },
  { key: 'status', label: 'Статус', sortable: true },
]

function severityValue(alert: AlertRecord): NormalizedAlertSeverity {
  return normalizeAlertSeverity(resolveEffectiveAlertSeverity(alert))
}

function severityLabel(alert: AlertRecord): string {
  return severityValue(alert)
}

function severitySortWeight(alert: AlertRecord): number {
  return alertSeveritySortWeight(alert)
}

function severityBadgeVariant(alert: AlertRecord): BadgeVariant {
  const severity = severityValue(alert)
  if (severity === 'critical' || severity === 'error') return 'danger'
  if (severity === 'warning') return 'warning'
  if (severity === 'info') return 'info'
  return 'neutral'
}

function statusBadgeVariant(alert: AlertRecord): BadgeVariant {
  return alertBadgeVariant(alert.status)
}

function processStoppingKind(alert: AlertRecord) {
  return alertProcessStoppingKind(alert)
}

function alertRowClass(alert: AlertRecord): string {
  const kind = processStoppingKind(alert)
  if (kind === 'automation_block') {
    return 'bg-[color:var(--badge-danger-bg)] hover:bg-[color:var(--badge-danger-bg)]'
  }
  if (kind === 'safety') {
    return 'bg-[color:var(--badge-warning-bg)] hover:bg-[color:var(--badge-warning-bg)]'
  }
  return ''
}

function sectionBadgeVariant(tone: GroupedAlertSection['tone']): BadgeVariant {
  if (tone === 'automation_block') return 'danger'
  if (tone === 'safety') return 'warning'
  if (tone === 'resolved') return 'success'
  return 'neutral'
}

function sectionShellClass(tone: GroupedAlertSection['tone']): string {
  if (tone === 'automation_block') return 'border-[color:var(--badge-danger-border)]'
  if (tone === 'safety') return 'border-[color:var(--badge-warning-border)]'
  if (tone === 'resolved') return 'border-[color:var(--badge-success-border)]'
  return 'border-[color:var(--border-muted)]'
}

function sectionHeaderClass(tone: GroupedAlertSection['tone']): string {
  if (tone === 'automation_block') {
    return 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)] text-[color:var(--badge-danger-text)]'
  }
  if (tone === 'safety') {
    return 'border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] text-[color:var(--badge-warning-text)]'
  }
  if (tone === 'resolved') {
    return 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
  }
  return 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--text-primary)]'
}

function sectionHint(key: GroupedAlertSectionKey): string {
  if (key === 'automation_block') return 'AE3 ждёт ручного подтверждения'
  if (key === 'safety') return 'Остановлен actuator path'
  if (key === 'resolved') return 'История подтверждённых алертов'
  return 'Активные алерты без остановки процесса'
}

type SectionZoneGroup = GroupedAlertZoneGroup & { showHeader: boolean }

function sectionZoneGroups(section: GroupedAlertSection): SectionZoneGroup[] {
  if (section.key !== 'resolved' && section.zoneGroups?.length) {
    return section.zoneGroups.map((zoneGroup) => ({
      ...zoneGroup,
      showHeader: true,
    }))
  }

  return [{
    zoneId: null,
    zoneName: '',
    testIdSuffix: 'all',
    items: section.items,
    showHeader: false,
  }]
}

function zoneGroupTableTestId(sectionKey: GroupedAlertSectionKey, zoneSuffix: string): string {
  if (zoneSuffix === 'all') {
    return `alerts-table-${sectionKey}`
  }

  return `alerts-table-${sectionKey}-${zoneSuffix}`
}

function scrollToAlertSection(key: GroupedAlertSectionKey): void {
  if (typeof document === 'undefined') return
  document.querySelector(`[data-testid="alerts-section-${key}"]`)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

function scrollToFirstActiveSection(): void {
  if (typeof document === 'undefined') return

  const order: GroupedAlertSectionKey[] = ['automation_block', 'safety', 'other_active']
  for (const key of order) {
    const section = document.querySelector(`[data-testid="alerts-section-${key}"]`)
    if (section) {
      section.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
  }

  document.querySelector('[data-testid="alerts-table"]')?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}
</script>
