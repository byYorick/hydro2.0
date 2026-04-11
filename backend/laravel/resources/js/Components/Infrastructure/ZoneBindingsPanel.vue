<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-semibold">
        Привязка устройств к ролям
      </h3>
      <Button
        size="sm"
        variant="outline"
        :disabled="saving || loading"
        @click="save"
      >
        {{ saving ? 'Сохранение...' : 'Сохранить привязки' }}
      </Button>
    </div>

    <div
      v-if="loading"
      class="text-sm text-[color:var(--text-muted)]"
    >
      Загрузка...
    </div>

    <div
      v-else-if="error"
      class="text-sm text-red-500"
    >
      {{ error }}
    </div>

    <div
      v-else
      class="space-y-2"
    >
      <div
        v-for="role in ASSIGNMENT_ROLES"
        :key="role.key"
        class="flex items-center gap-3 p-2 rounded bg-[color:var(--bg-elevated)]"
      >
        <div class="w-36 text-xs text-[color:var(--text-muted)] shrink-0">
          {{ role.label }}
          <span
            v-if="role.required"
            class="text-red-400"
          >*</span>
        </div>
        <select
          v-model="assignments[role.key]"
          class="input-select h-8 text-xs flex-1"
        >
          <option :value="null">
            — не назначено —
          </option>
          <option
            v-for="node in nodesByType[role.nodeType]"
            :key="node.id"
            :value="node.id"
          >
            {{ node.name }} ({{ node.uid }})
          </option>
        </select>
      </div>
    </div>

    <div
      v-if="saveError"
      class="text-sm text-red-500"
    >
      {{ saveError }}
    </div>
    <div
      v-if="saveSuccess"
      class="text-sm text-green-500"
    >
      Привязки сохранены
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import Button from '@/Components/Button.vue'
import axios from 'axios'
import { logger } from '@/utils/logger'

interface Props {
  zoneId: number
}

const props = defineProps<Props>()

const ASSIGNMENT_ROLES = [
  { key: 'irrigation', label: 'Полив (ирригация)', nodeType: 'irrig', required: true },
  { key: 'ph_correction', label: 'Коррекция pH', nodeType: 'ph', required: true },
  { key: 'ec_correction', label: 'Коррекция EC', nodeType: 'ec', required: true },
  { key: 'light', label: 'Освещение', nodeType: 'light', required: false },
  { key: 'climate', label: 'Климат', nodeType: 'climate', required: false },
] as const

type AssignmentKey = 'irrigation' | 'ph_correction' | 'ec_correction' | 'light' | 'climate'

// role → binding_role mapping для определения текущих привязок
const BINDING_ROLE_TO_ASSIGNMENT: Record<string, AssignmentKey> = {
  main_pump: 'irrigation',
  drain: 'irrigation',
  ph_acid_pump: 'ph_correction',
  ph_base_pump: 'ph_correction',
  ec_npk_pump: 'ec_correction',
  ec_calcium_pump: 'ec_correction',
  ec_magnesium_pump: 'ec_correction',
  ec_micro_pump: 'ec_correction',
  light: 'light',
  vent: 'climate',
  heater: 'climate',
}

interface Node {
  id: number
  uid: string
  name: string
  type: string
}

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)

const allNodes = ref<Node[]>([])
const assignments = reactive<Record<AssignmentKey, number | null>>({
  irrigation: null,
  ph_correction: null,
  ec_correction: null,
  light: null,
  climate: null,
})

const nodesByType = computed(() => {
  const map: Record<string, Node[]> = {}
  for (const node of allNodes.value) {
    const t = node.type
    if (!map[t]) map[t] = []
    map[t].push(node)
  }
  return map
})

async function load() {
  loading.value = true
  error.value = null
  try {
    // Загружаем ноды зоны
    const nodesResp = await axios.get(`/api/nodes`, { params: { zone_id: props.zoneId, per_page: 100 } })
    allNodes.value = nodesResp.data?.data?.data ?? []

    // Загружаем текущие биндинги через infra instances
    const infraResp = await axios.get(`/api/zones/${props.zoneId}/infrastructure-instances`)
    const instances = infraResp.data?.data ?? []

    // Сбрасываем
    assignments.irrigation = null
    assignments.ph_correction = null
    assignments.ec_correction = null
    assignments.light = null
    assignments.climate = null

    // Восстанавливаем текущие назначения по существующим биндингам
    for (const instance of instances) {
      for (const binding of instance.channel_bindings ?? []) {
        const assignmentRole = BINDING_ROLE_TO_ASSIGNMENT[binding.role]
        if (!assignmentRole) continue
        const nodeId = binding.node_channel?.node_id
        if (!nodeId) continue
        if (assignments[assignmentRole] === null) {
          assignments[assignmentRole] = nodeId
        }
      }
    }
  } catch (e: unknown) {
    error.value = 'Ошибка загрузки данных'
    logger.error('[ZoneBindingsPanel] load failed:', e)
  } finally {
    loading.value = false
  }
}

async function save() {
  saveError.value = null
  saveSuccess.value = false
  saving.value = true
  try {
    const selectedNodeIds = Object.values(assignments).filter((id): id is number => id !== null)
    await axios.post('/api/setup-wizard/apply-device-bindings', {
      zone_id: props.zoneId,
      assignments: { ...assignments },
      selected_node_ids: selectedNodeIds,
    })
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 3000)
    await load()
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message
    saveError.value = msg ?? 'Ошибка сохранения привязок'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
