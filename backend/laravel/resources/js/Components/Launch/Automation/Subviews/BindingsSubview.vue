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
            :options="nodeOptions"
            mono
            size="sm"
            @update:model-value="(v: string) => onUpdate(row.key, v)"
          />
          <span class="font-mono text-[11px] text-[var(--text-dim)] truncate">
            role: {{ row.role }}
          </span>
          <span>
            <Chip
              v-if="assignments[row.key]"
              tone="growth"
            >
              привязано
            </Chip>
            <Chip
              v-else
              tone="alert"
            >
              не задано
            </Chip>
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
            :options="nodeOptions"
            mono
            size="sm"
            @update:model-value="(v: string) => onUpdate(row.key, v)"
          />
          <span class="font-mono text-[11px] text-[var(--text-dim)] truncate">
            role: {{ row.role }}
          </span>
          <span>
            <Chip
              v-if="assignments[row.key]"
              tone="growth"
            >
              привязано
            </Chip>
            <Chip
              v-else
              tone="neutral"
            >
              опц.
            </Chip>
          </span>
        </div>
      </div>
    </section>

    <Hint :show="showHints">
      Привязки идентичны схеме <span class="font-mono">assignmentsSchema</span>.
      ESP32 узлы публикуют список ролей в bridge — выбор канала фиксируется
      в <span class="font-mono">zone.assignments</span>.
    </Hint>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Select from '@/Components/Shared/Primitives/Select.vue'
import Chip from '@/Components/Shared/Primitives/Chip.vue'
import Hint from '@/Components/Shared/Primitives/Hint.vue'
import Ic from '@/Components/Icons/Ic.vue'
import type { IcName } from '@/Components/Icons/Ic.vue'
import { useLaunchPreferences } from '@/composables/useLaunchPreferences'
import type {
  ZoneAutomationSectionAssignments,
  ZoneAutomationBindRole,
} from '@/composables/zoneAutomationTypes'
import type { AutomationNode as SetupWizardNode } from '@/types/AutomationNode'

const props = defineProps<{
  assignments: ZoneAutomationSectionAssignments
  availableNodes: readonly SetupWizardNode[]
}>()

const emit = defineEmits<{
  (e: 'update:assignments', next: ZoneAutomationSectionAssignments): void
}>()

const { showHints } = useLaunchPreferences()

interface RoleDef {
  key: ZoneAutomationBindRole
  label: string
  role: string
  iconName?: IcName
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

const GRID_STYLE = 'grid-template-columns: 170px 200px 1fr 130px'

const nodeOptions = computed(() => [
  { value: '', label: '— не задано —' },
  ...props.availableNodes.map((n) => ({
    value: String(n.id),
    label: nodeLabel(n),
  })),
])

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
</script>
