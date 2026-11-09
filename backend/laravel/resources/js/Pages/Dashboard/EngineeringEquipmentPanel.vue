<template>
  <section
    class="equipment-workspace space-y-4"
    aria-label="Диагностика оборудования"
  >
    <div class="grid grid-cols-2 gap-3 xl:grid-cols-4">
      <div class="surface-card p-4">
        <p class="text-xs text-[color:var(--text-muted)]">
          Блокируют процесс
        </p>
        <p class="mt-2 text-3xl font-semibold tabular-nums text-[color:var(--status-critical)]">
          {{ blockedCount }}
        </p>
        <p class="mt-1 text-xs text-[color:var(--text-muted)]">
          Зоны с подтверждённой блокировкой
        </p>
      </div>
      <div class="surface-card p-4">
        <p class="text-xs text-[color:var(--text-muted)]">
          Узлы не на связи
        </p>
        <p class="mt-2 text-3xl font-semibold tabular-nums">
          {{ loaded ? scopedDevices.filter(d => d.status === 'offline').length : '—' }}
        </p>
        <p class="mt-1 text-xs text-[color:var(--text-muted)]">
          По доступному списку оборудования
        </p>
      </div>
      <div class="surface-card p-4">
        <p class="text-xs text-[color:var(--text-muted)]">
          Без свежей сводки
        </p>
        <p class="mt-2 text-3xl font-semibold tabular-nums">
          {{ scopedZones.filter(z => !telemetrySummaryIsFresh(z, now)).length }}
        </p>
        <p class="mt-1 text-xs text-[color:var(--text-muted)]">
          Зоны · обновление старше 5 минут или неизвестно
        </p>
      </div>
      <div class="surface-card p-4">
        <p class="text-xs text-[color:var(--text-muted)]">
          Насосы без калибровки
        </p><p class="mt-2 text-3xl font-semibold tabular-nums">
          {{ loaded ? scopedDevices.reduce((count, device) => count + missingPumpCalibration(device), 0) : '—' }}
        </p><p class="mt-1 text-xs text-[color:var(--text-muted)]">
          Привязанные насосные каналы без результата
        </p>
      </div>
    </div>
    <div class="surface-card p-4 text-sm text-[color:var(--text-muted)]">
      Связь с узлом и свежесть измерений проверяются отдельно. Причина сбоя определяется по данным узла и событиям зоны.
    </div>
    <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div
        class="flex flex-wrap gap-2"
        role="group"
        aria-label="Состояние оборудования"
      >
        <button
          v-for="item in filters"
          :key="item.id"
          type="button"
          class="btn min-h-11 px-3 text-xs"
          :class="filter === item.id ? 'btn-outline' : 'btn-ghost'"
          :aria-pressed="filter === item.id"
          @click="filter = item.id"
        >
          {{ item.label }}
        </button>
      </div>
      <SelectField
        v-model="selectedZone"
        class="sm:max-w-52"
        aria-label="Зона оборудования"
      >
        <option value="">
          Все зоны
        </option><option
          v-for="zone in zones"
          :key="zone.id"
          :value="String(zone.id)"
        >
          {{ zone.name }}
        </option>
      </SelectField>
      <TextField
        v-model="search"
        class="sm:max-w-xs"
        placeholder="Узел, канал или зона"
        aria-label="Поиск оборудования"
      />
    </div>
    <div
      v-if="!loaded && !error"
      class="surface-card p-5"
      role="status"
      aria-label="Загрузка оборудования"
    >
      <SkeletonBlock
        :lines="5"
        line-height="2.5rem"
      />
    </div>
    <EmptyState
      v-else-if="error && !loaded"
      title="Не удалось загрузить оборудование"
      :description="error"
      container-class="surface-card py-8"
    >
      <template #action>
        <Button
          variant="secondary"
          @click="loadDevices"
        >
          Повторить
        </Button>
      </template>
    </EmptyState>
    <template v-else>
      <div
        v-if="error"
        class="surface-card flex flex-wrap items-center justify-between gap-3 p-4 text-sm text-[color:var(--status-warning)]"
        role="status"
      >
        <span>Не удалось обновить список. Показаны последние загруженные данные.</span><Button
          size="sm"
          variant="secondary"
          :disabled="loading"
          @click="loadDevices"
        >
          Повторить
        </Button>
      </div>
      <EmptyState
        v-if="!visibleDevices.length"
        title="Нет оборудования по выбранным условиям"
        description="Измените фильтр или поиск. Полный каталог доступен в разделе «Оборудование»."
        container-class="surface-card py-8"
      />
      <div
        v-else
        class="surface-card overflow-hidden"
      >
        <div
          class="equipment-head bg-[color:var(--bg-elevated)] text-xs text-[color:var(--text-muted)]"
          aria-hidden="true"
        >
          <span>Узел / зона</span><span>Наблюдение</span><span>Контекст процесса</span><span>Последний пакет</span><span>Проверка</span>
        </div>
        <article
          v-for="device in visibleDevices"
          :key="device.id"
          class="equipment-row border-t border-[color:var(--border-muted)]"
        >
          <div class="min-w-0">
            <Link
              :href="`/devices/${device.id}`"
              class="break-words text-sm font-semibold hover:underline"
            >
              {{ device.uid || device.name || `Узел ${device.id}` }}
            </Link><p class="mt-1 text-xs text-[color:var(--text-muted)]">
              {{ zoneName(device) }}
            </p>
          </div>
          <div>
            <Badge :variant="device.status === 'online' ? 'ok' : device.status === 'offline' ? 'danger' : 'warning'">
              {{ translateDeviceStatus(device.status) }}
            </Badge><p class="mt-1 text-xs text-[color:var(--text-muted)]">
              {{ channelLabel(device) }}
            </p><p
              v-if="missingPumpCalibration(device)"
              class="mt-1 text-xs text-[color:var(--status-warning)]"
            >
              Без калибровки насосов: {{ missingPumpCalibration(device) }}
            </p>
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            {{ zoneFor(device)?.automation_block?.blocked ? zoneFor(device)?.automation_block?.message || 'Автоматика остановлена' : zoneFor(device) ? 'Подтверждённой блокировки зоны нет' : 'Контекст зоны недоступен' }}
          </div>
          <div class="text-xs text-[color:var(--text-muted)]">
            {{ formatSeen(device) }}
          </div>
          <Link
            :href="`/devices/${device.id}`"
            class="btn btn-outline min-h-11 text-xs"
          >
            Проверить узел →
          </Link>
        </article>
      </div>
      <p class="flex flex-wrap items-center justify-between gap-2 text-xs text-[color:var(--text-muted)]">
        <span>Показано {{ visibleDevices.length }} из {{ filteredDevices.length }} узлов по условиям поиска.</span><Link
          href="/devices"
          class="text-[color:var(--status-info)] hover:underline"
        >
          Всё оборудование →
        </Link>
      </p>
      <Pagination
        v-if="filteredDevices.length > perPage"
        v-model:current-page="currentPage"
        v-model:per-page="perPage"
        :total="filteredDevices.length"
      />
      <div class="flex flex-wrap items-center justify-between gap-3 text-xs text-[color:var(--text-muted)]">
        <span>Список обновлён: {{ loadedAt }}</span><Button
          variant="secondary"
          size="sm"
          :disabled="loading"
          @click="loadDevices"
        >
          {{ loading ? 'Обновление…' : 'Обновить оборудование' }}
        </Button>
      </div>
    </template>
    <EngineeringIssuesPanel :issues="buildEngineeringIssues(scopedZones)" />
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Link } from '@inertiajs/vue3'
import { api } from '@/services/api'
import type { Device } from '@/types'
import type { UnifiedZone } from '@/composables/useUnifiedDashboard'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import EmptyState from '@/Components/EmptyState.vue'
import SkeletonBlock from '@/Components/SkeletonBlock.vue'
import TextField from '@/Components/TextField.vue'
import SelectField from '@/Components/SelectField.vue'
import Pagination from '@/Components/Pagination.vue'
import EngineeringIssuesPanel from './EngineeringIssuesPanel.vue'
const translateDeviceStatus = (status: string) => ({ online: 'На связи', offline: 'Нет связи', degraded: 'Требует проверки', unknown: 'Состояние неизвестно' }[status] || 'Состояние неизвестно')
import { buildEngineeringIssues, telemetrySummaryIsFresh } from './dashboardRoleView'
import { useUrlState } from '@/composables/useUrlState'

const props = defineProps<{ zones: UnifiedZone[]; now: number }>()
const devices = ref<Device[]>([]), loading = ref(false), loaded = ref(false), error = ref('')
const loadedAt = ref('—')
const currentPage = ref(1), perPage = ref(12)
const search = useUrlState({ key: 'nodeSearch', defaultValue: '', debounceMs: 200 })
type Filter = 'all' | 'attention' | 'unknown'
const filter = useUrlState<Filter>({ key: 'nodes', defaultValue: 'attention', parse: value => value === 'all' || value === 'unknown' ? value : 'attention' })
const filters: Array<{ id: Filter; label: string }> = [{ id: 'attention', label: 'Требуют проверки' }, { id: 'all', label: 'Всё оборудование' }, { id: 'unknown', label: 'Состояние неизвестно' }]
const selectedZone = useUrlState({ key: 'nodeZone', defaultValue: '', parse: value => value && props.zones.some(zone => String(zone.id) === value) ? value : '' })
const scopedZones = computed(() => props.zones.filter(zone => !selectedZone.value || String(zone.id) === selectedZone.value))
const scopedDevices = computed(() => devices.value.filter(device => !selectedZone.value || String(device.zone_id ?? device.zone?.id) === selectedZone.value))
const blockedCount = computed(() => scopedZones.value.filter(z => z.automation_block?.blocked).length)
const zonesById = computed(() => new Map(props.zones.map(z => [z.id, z])))
const zoneFor = (device: Device) => zonesById.value.get(device.zone_id ?? device.zone?.id ?? 0)
const zoneName = (device: Device) => zoneFor(device)?.name || device.zone?.name || 'Без назначенной зоны'
const filteredDevices = computed(() => scopedDevices.value.filter(d => {
  const zone = zoneFor(d)
  const attention = d.status !== 'online' || missingPumpCalibration(d) > 0 || Boolean(zone?.automation_block?.blocked) || Boolean(zone && !telemetrySummaryIsFresh(zone, props.now))
  const matches = filter.value === 'all' || (filter.value === 'attention' ? attention : d.status === 'unknown')
  return matches && `${d.uid} ${d.name ?? ''} ${zoneName(d)} ${channelLabel(d)}`.toLowerCase().includes(search.value.trim().toLowerCase())
}).sort((a, b) => Number(b.status === 'offline') - Number(a.status === 'offline') || a.id - b.id))
const visibleDevices = computed(() => filteredDevices.value.slice((currentPage.value - 1) * perPage.value, currentPage.value * perPage.value))
watch([search, filter, selectedZone, perPage], () => { currentPage.value = 1 })
watch(() => filteredDevices.value.length, count => { currentPage.value = Math.max(1, Math.min(currentPage.value, Math.ceil(count / perPage.value))) })
function missingPumpCalibration(device: Device): number {
  return (device.channels ?? []).filter(channel => {
    const isBoundPump = ['pump_a', 'pump_b', 'pump_c', 'pump_d', 'pump_acid', 'pump_base'].includes(channel.binding_role ?? '')
    return isBoundPump && !(typeof channel.pump_calibration?.ml_per_sec === 'number' && channel.pump_calibration.ml_per_sec > 0)
  }).length
}
function channelLabel(device: Device): string {
  return device.channels?.map(c => c.channel).join(' · ') || 'Каналы — в карточке узла'
}
function formatSeen(device: Device): string {
  const raw = device.last_heartbeat_at || device.last_seen_at
  const at = Date.parse(raw ?? '')
  if (!Number.isFinite(at)) return 'Время неизвестно'
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(at)
}
let disposed = false
async function loadDevices(): Promise<void> {
  if (loading.value) return
  loading.value = true
  try {
    const result = await api.nodes.list()
    if (disposed) return
    devices.value = result
    loaded.value = true
    loadedAt.value = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(Date.now())
    error.value = ''
  } catch {
    if (!disposed) error.value = 'Проверьте подключение и повторите запрос.'
  } finally {
    if (!disposed) loading.value = false
  }
}
onMounted(() => { void loadDevices() })
watch(() => props.zones, () => { void loadDevices() })
onBeforeUnmount(() => { disposed = true })
</script>

<style scoped>
.equipment-workspace { container: equipment / inline-size; }
.equipment-head, .equipment-row { display:grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1.2fr) minmax(0, 1.2fr) minmax(0, .9fr) minmax(0, 1fr); gap:1rem; align-items:center; padding:1rem 1.25rem; }
.equipment-row { min-height:6rem; }
@container equipment (max-width:1000px) { .equipment-head { display:none; } .equipment-row { grid-template-columns:repeat(2,minmax(0,1fr)); } .equipment-row > :last-child { grid-column:1/-1; } }
@media(max-width:480px) { .equipment-row { padding:1rem; } }
</style>
