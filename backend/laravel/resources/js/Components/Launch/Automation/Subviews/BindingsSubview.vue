<template>
  <div class="flex flex-col gap-3.5">
    <section>
      <div
        class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] mb-1.5"
      >
        Обязательные роли
      </div>
      <div class="border border-[var(--border-muted)] rounded-md overflow-hidden">
        <div
          class="grid items-center px-3 py-2 bg-[var(--bg-elevated)] text-[11px] uppercase tracking-wider text-[var(--text-dim)]"
          :style="GRID_STYLE"
        >
          <span>Роль</span>
          <span>Узел</span>
          <span>Канал/комментарий</span>
          <span>Статус</span>
        </div>

        <div
          v-for="row in REQUIRED"
          :key="row.key"
          class="grid items-center px-3 py-2 gap-2 border-t border-[var(--border-muted)]"
          :style="GRID_STYLE"
        >
          <span class="flex items-center gap-1.5 text-sm">
            <Ic
              v-if="row.iconName"
              :name="row.iconName"
              class="text-brand"
            />
            {{ row.label }}
            <span class="text-alert font-mono ml-0.5">*</span>
          </span>
          <Select
            :model-value="assignments[row.key] != null ? String(assignments[row.key]) : ''"
            :options="nodeOptionsForRole(row.key)"
            mono
            size="sm"
            @update:model-value="(v: string) => onUpdate(row.key, v)"
          />
          <span class="font-mono text-[11px] text-[var(--text-dim)] truncate">
            role: {{ row.role }}
          </span>
          <span class="flex items-center gap-1.5 flex-wrap">
            <Chip :tone="rowStatus(row.key, true).tone">
              <template
                v-if="rowStatus(row.key, true).pending"
                #icon
              >
                <span class="inline-block w-1.5 h-1.5 rounded-full bg-warn animate-pulse" />
              </template>
              {{ rowStatus(row.key, true).label }}
            </Chip>
            <Button
              v-if="rowStatus(row.key, true).canBind"
              size="sm"
              variant="secondary"
              :disabled="bindingNodeIds.has(Number(assignments[row.key]))"
              @click="onBindClick(row.key)"
            >
              {{ bindingNodeIds.has(Number(assignments[row.key])) ? '…' : 'Привязать' }}
            </Button>
          </span>
        </div>
      </div>
    </section>

    <section>
      <div
        class="text-[10px] font-bold uppercase tracking-widest text-[var(--text-dim)] mb-1.5"
      >
        Опциональные роли
      </div>
      <div class="border border-[var(--border-muted)] rounded-md overflow-hidden">
        <div
          class="grid items-center px-3 py-2 bg-[var(--bg-elevated)] text-[11px] uppercase tracking-wider text-[var(--text-dim)]"
          :style="GRID_STYLE"
        >
          <span>Роль</span>
          <span>Узел</span>
          <span>Канал/комментарий</span>
          <span>Статус</span>
        </div>

        <div
          v-for="row in OPTIONAL"
          :key="row.key"
          class="grid items-center px-3 py-2 gap-2 border-t border-[var(--border-muted)]"
          :style="GRID_STYLE"
        >
          <span class="text-sm">{{ row.label }}</span>
          <Select
            :model-value="assignments[row.key] != null ? String(assignments[row.key]) : ''"
            :options="nodeOptionsForRole(row.key)"
            mono
            size="sm"
            @update:model-value="(v: string) => onUpdate(row.key, v)"
          />
          <span class="font-mono text-[11px] text-[var(--text-dim)] truncate">
            role: {{ row.role }}
          </span>
          <span class="flex items-center gap-1.5 flex-wrap">
            <Chip :tone="rowStatus(row.key, false).tone">
              <template
                v-if="rowStatus(row.key, false).pending"
                #icon
              >
                <span class="inline-block w-1.5 h-1.5 rounded-full bg-warn animate-pulse" />
              </template>
              {{ rowStatus(row.key, false).label }}
            </Chip>
            <Button
              v-if="rowStatus(row.key, false).canBind"
              size="sm"
              variant="secondary"
              :disabled="bindingNodeIds.has(Number(assignments[row.key]))"
              @click="onBindClick(row.key)"
            >
              {{ bindingNodeIds.has(Number(assignments[row.key])) ? '…' : 'Привязать' }}
            </Button>
          </span>
        </div>
      </div>
    </section>

    <Hint :show="showHints">
      В выпадающем списке доступны только узлы, привязанные к этой зоне
      (<span class="font-mono">✓</span> bound, <span class="font-mono">⏳</span>
      pending). Нода считается привязанной после получения
      <span class="font-mono">config_report</span> от железа: backend промоутит
      <span class="font-mono">pending_zone_id → zone_id</span> и переводит
      <span class="font-mono">lifecycle_state := ASSIGNED_TO_ZONE</span>.
      <template v-if="unboundCount > 0">
        Доступно ещё {{ unboundCount }} непривязанных узлов —
        <a
          class="underline text-brand"
          href="/devices/add"
          target="_blank"
          rel="noopener"
        >зарегистрировать</a>.
      </template>
    </Hint>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Select from '@/Components/Shared/Primitives/Select.vue'
import Chip from '@/Components/Shared/Primitives/Chip.vue'
import type { ChipTone } from '@/Components/Shared/Primitives/Chip.vue'
import Hint from '@/Components/Shared/Primitives/Hint.vue'
import Button from '@/Components/Button.vue'
import Ic from '@/Components/Icons/Ic.vue'
import type { IcName } from '@/Components/Icons/Ic.vue'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type {
  ZoneAutomationSectionAssignments,
  ZoneAutomationBindRole,
} from '@/composables/zoneAutomationTypes'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'
import {
  matchesAnyBindingRole,
  matchesAnyChannel,
} from '@/composables/zoneAutomationNodeMatching'

const props = defineProps<{
  zoneId: number
  assignments: ZoneAutomationSectionAssignments
  availableNodes: readonly SetupWizardNode[]
  bindingNodeIds?: ReadonlySet<number>
}>()

const emit = defineEmits<{
  (e: 'update:assignments', next: ZoneAutomationSectionAssignments): void
  (e: 'bind-node', nodeId: number): void
}>()

const { showHints } = useLaunchPreferences()

interface RoleDef {
  key: ZoneAutomationBindRole
  label: string
  role: string
  iconName?: IcName
}

interface RoleFilterSpec {
  typeCandidates: string[]
  channelCandidates: string[]
  bindingRoleCandidates: string[]
}

const REQUIRED: RoleDef[] = [
  { key: 'irrigation', label: 'Полив', role: 'pump_main / irrigation', iconName: 'drop' },
  { key: 'ph_correction', label: 'Коррекция pH', role: 'ph_dose', iconName: 'beaker' },
  { key: 'ec_correction', label: 'Коррекция EC', role: 'ec_dose', iconName: 'zap' },
]

const OPTIONAL: RoleDef[] = [
  { key: 'light', label: 'Свет', role: 'light_actuator' },
  { key: 'soil_moisture_sensor', label: 'Влажность субстрата', role: 'soil_moisture_sensor' },
  { key: 'co2_sensor', label: 'Сенсор CO₂', role: 'co2_sensor' },
  { key: 'co2_actuator', label: 'Исполнитель CO₂', role: 'co2_actuator' },
  { key: 'root_vent_actuator', label: 'Корневая вентиляция', role: 'root_vent_actuator' },
]

const GRID_STYLE = 'grid-template-columns: 170px 200px 1fr 220px'

const ASSIGNED_ROLE_KEYS: ZoneAutomationBindRole[] = [
  'irrigation',
  'ph_correction',
  'ec_correction',
  'light',
  'soil_moisture_sensor',
  'co2_sensor',
  'co2_actuator',
  'root_vent_actuator',
]

const ROLE_FILTER_SPECS: Record<ZoneAutomationBindRole, RoleFilterSpec> = {
  irrigation: {
    typeCandidates: ['irrig', 'pump', 'pump_node', 'relay', 'relay_node'],
    channelCandidates: ['pump_main', 'drain', 'drain_main', 'drain_valve', 'valve_solution_supply', 'valve_solution_fill', 'valve_irrigation'],
    bindingRoleCandidates: ['pump_main', 'drain'],
  },
  ph_correction: {
    typeCandidates: ['ph', 'ph_node'],
    channelCandidates: ['pump_acid', 'pump_base', 'ph_sensor'],
    bindingRoleCandidates: ['pump_acid', 'pump_base'],
  },
  ec_correction: {
    typeCandidates: ['ec', 'ec_node'],
    channelCandidates: ['pump_a', 'pump_b', 'pump_c', 'pump_d', 'ec_sensor'],
    bindingRoleCandidates: ['pump_a', 'pump_b', 'pump_c', 'pump_d'],
  },
  light: {
    typeCandidates: ['light', 'light_node', 'relay', 'relay_node'],
    channelCandidates: ['light', 'light_main', 'white_light', 'uv_light'],
    bindingRoleCandidates: ['light', 'light_actuator'],
  },
  soil_moisture_sensor: {
    typeCandidates: ['soil', 'substrate', 'climate', 'climate_node'],
    channelCandidates: ['soil_moisture', 'soil_moisture_pct', 'substrate_moisture'],
    bindingRoleCandidates: ['soil_moisture_sensor'],
  },
  co2_sensor: {
    typeCandidates: ['climate', 'climate_node'],
    channelCandidates: ['co2_ppm'],
    bindingRoleCandidates: ['co2_sensor'],
  },
  co2_actuator: {
    typeCandidates: ['climate', 'climate_node', 'relay', 'relay_node'],
    channelCandidates: ['co2_inject'],
    bindingRoleCandidates: ['co2_actuator'],
  },
  root_vent_actuator: {
    typeCandidates: ['climate', 'climate_node', 'relay', 'relay_node'],
    channelCandidates: ['root_vent', 'fan_root'],
    bindingRoleCandidates: ['root_vent_actuator'],
  },
}

const assignedIds = computed(() => {
  const ids = new Set<number>()
  for (const key of ASSIGNED_ROLE_KEYS) {
    const v = props.assignments[key]
    if (typeof v === 'number' && v > 0) ids.add(v)
  }
  return ids
})

const visibleNodes = computed(() =>
  props.availableNodes.filter(
    (n) => n.zone_id === props.zoneId
      || n.pending_zone_id === props.zoneId
      || assignedIds.value.has(n.id)
      || (n.zone_id == null && n.pending_zone_id == null),
  ),
)

const unboundCount = computed(() => {
  let count = 0
  for (const n of props.availableNodes) {
    if (n.zone_id !== props.zoneId && n.pending_zone_id !== props.zoneId) count++
  }
  return count
})

function nodeMatchesRole(node: SetupWizardNode, role: ZoneAutomationBindRole): boolean {
  const spec = ROLE_FILTER_SPECS[role]
  const normalizedType = String(node.type ?? '').toLowerCase()
  const typeMatched = spec.typeCandidates.includes(normalizedType)
  const channelMatched = matchesAnyChannel(node, spec.channelCandidates)
  const bindingRoleMatched = matchesAnyBindingRole(node, spec.bindingRoleCandidates)

  return typeMatched || channelMatched || bindingRoleMatched
}

function nodeOptionsForRole(role: ZoneAutomationBindRole): Array<{ value: string; label: string }> {
  return [
    { value: '', label: '— не задано —' },
    ...visibleNodes.value
      .filter((node) => nodeMatchesRole(node, role))
      .map((node) => ({
        value: String(node.id),
        label: nodeOptionLabel(node),
      })),
  ]
}

function nodeOptionLabel(n: SetupWizardNode): string {
  const base = nodeLabel(n)
  if (n.zone_id === props.zoneId) return `✓ ${base}`
  if (n.pending_zone_id === props.zoneId && !n.zone_id) return `⏳ ${base}`
  return `○ ${base}`
}

const bindingNodeIds = computed<ReadonlySet<number>>(
  () => props.bindingNodeIds ?? new Set<number>(),
)

const nodeById = computed<Map<number, SetupWizardNode>>(() => {
  const map = new Map<number, SetupWizardNode>()
  for (const n of props.availableNodes) {
    map.set(n.id, n)
  }
  return map
})

interface RowStatus {
  label: string
  tone: ChipTone
  canBind: boolean
  pending: boolean
}

function rowStatus(role: ZoneAutomationBindRole, required: boolean): RowStatus {
  const id = props.assignments[role]
  if (id == null) {
    return required
      ? { label: 'не задано', tone: 'alert', canBind: false, pending: false }
      : { label: 'опц.', tone: 'neutral', canBind: false, pending: false }
  }
  const node = nodeById.value.get(Number(id))
  if (!node) {
    return { label: 'нода недоступна', tone: 'alert', canBind: true, pending: false }
  }
  if (node.pending_zone_id === props.zoneId && !node.zone_id) {
    return { label: 'привязка…', tone: 'warn', canBind: false, pending: true }
  }
  if (node.zone_id === props.zoneId) {
    return { label: 'привязано', tone: 'growth', canBind: true, pending: false }
  }
  return { label: 'не привязано', tone: 'alert', canBind: true, pending: false }
}

function nodeLabel(n: SetupWizardNode): string {
  const id = n.uid ?? n.name ?? `Node #${n.id}`
  const type = n.type ?? 'unknown'
  return `${id} · ${type}`
}

function onUpdate(role: ZoneAutomationBindRole, raw: string): void {
  const next: ZoneAutomationSectionAssignments = { ...props.assignments }
  const id = raw === '' ? null : Number(raw)
  next[role] = id != null && Number.isFinite(id) ? id : null
  emit('update:assignments', next)
}

function onBindClick(role: ZoneAutomationBindRole): void {
  const id = props.assignments[role]
  if (typeof id !== 'number' || id <= 0) return
  emit('bind-node', id)
}
</script>
