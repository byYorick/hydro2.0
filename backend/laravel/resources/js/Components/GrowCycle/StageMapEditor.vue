<template>
  <Card>
    <div class="space-y-4">
      <div>
        <h3 class="text-sm font-semibold mb-2">Маппинг фаз рецепта → стадии выращивания</h3>
        <p class="text-xs text-[color:var(--text-muted)] mb-4">
          Настройте соответствие фаз рецепта стадиям выращивания растения
        </p>
      </div>

      <div v-if="phases.length === 0" class="text-sm text-[color:var(--text-muted)]">
        Нет фаз в рецепте
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="(phase, index) in phases"
          :key="phase.id || index"
          class="p-3 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
        >
          <div class="flex items-center justify-between mb-2">
            <div>
              <div class="text-sm font-medium">{{ phase.name }}</div>
              <div class="text-xs text-[color:var(--text-muted)]">
                Фаза {{ phase.phase_index }} • {{ phase.duration_hours }}ч
              </div>
            </div>
          </div>

          <div class="mt-2">
            <label class="block text-xs text-[color:var(--text-muted)] mb-1">Стадия выращивания</label>
            <select
              :value="getStageForPhaseIndex(phase.phase_index)"
              @change="updateStageMapping(phase.phase_index, $event.target.value)"
              class="input-select h-8 w-full text-xs"
            >
              <option
                v-for="stage in availableStages"
                :key="stage.id"
                :value="stage.id"
              >
                {{ stage.icon }} {{ stage.label }}
              </option>
            </select>
          </div>
        </div>
      </div>

      <div v-if="hasChanges" class="flex gap-2">
        <Button size="sm" variant="secondary" @click="resetChanges">Сбросить</Button>
        <Button size="sm" @click="saveChanges" :disabled="saving">
          {{ saving ? 'Сохранение...' : 'Сохранить изменения' }}
        </Button>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { GROW_STAGES, getStageForPhase, type GrowStage } from '@/utils/growStages'

interface Props {
  recipeId: number
  phases: Array<{
    id: number
    phase_index: number
    name: string
    duration_hours: number
  }>
}

const props = defineProps<Props>()

const { showToast } = useToast()
const { api } = useApi(showToast)

const stageMap = ref<Array<{ phase_index: number; stage: GrowStage }>>([])
const originalStageMap = ref<Array<{ phase_index: number; stage: GrowStage }>>([])
const saving = ref(false)

const availableStages = computed(() => Object.values(GROW_STAGES))

const hasChanges = computed(() => {
  return JSON.stringify(stageMap.value) !== JSON.stringify(originalStageMap.value)
})

// Загружаем stage-map при монтировании
watch(() => props.recipeId, async (recipeId) => {
  if (recipeId) {
    await loadStageMap()
  }
}, { immediate: true })

async function loadStageMap() {
  try {
    const response = await api.get(`/recipes/${props.recipeId}/stage-map`)
    if (response.data?.status === 'ok') {
      stageMap.value = response.data.data.stage_map || []
      originalStageMap.value = JSON.parse(JSON.stringify(stageMap.value))
      
      // Если нет stage-map, генерируем автоматически
      if (stageMap.value.length === 0 && props.phases.length > 0) {
        stageMap.value = props.phases.map(phase => ({
          phase_index: phase.phase_index,
          stage: getStageForPhase(phase.name, phase.phase_index, props.phases.length) as GrowStage,
        }))
        originalStageMap.value = JSON.parse(JSON.stringify(stageMap.value))
      }
    }
  } catch (error) {
    console.error('Failed to load stage map:', error)
  }
}

function getStageForPhaseIndex(phaseIndex: number): GrowStage {
  const mapping = stageMap.value.find(m => m.phase_index === phaseIndex)
  if (mapping) {
    return mapping.stage
  }
  
  // Автоматическое определение
  const phase = props.phases.find(p => p.phase_index === phaseIndex)
  if (phase) {
    return getStageForPhase(phase.name, phaseIndex, props.phases.length) as GrowStage
  }
  
  return 'veg'
}

function updateStageMapping(phaseIndex: number, stage: string) {
  const index = stageMap.value.findIndex(m => m.phase_index === phaseIndex)
  if (index >= 0) {
    stageMap.value[index].stage = stage as GrowStage
  } else {
    stageMap.value.push({
      phase_index: phaseIndex,
      stage: stage as GrowStage,
    })
  }
}

function resetChanges() {
  stageMap.value = JSON.parse(JSON.stringify(originalStageMap.value))
}

async function saveChanges() {
  saving.value = true
  try {
    const response = await api.put(`/recipes/${props.recipeId}/stage-map`, {
      stage_map: stageMap.value,
    })
    
    if (response.data?.status === 'ok') {
      originalStageMap.value = JSON.parse(JSON.stringify(stageMap.value))
      showToast('Маппинг стадий сохранен', 'success')
    }
  } catch (error) {
    console.error('Failed to save stage map:', error)
    showToast('Ошибка при сохранении', 'error')
  } finally {
    saving.value = false
  }
}

defineExpose({
  getStageMap: () => stageMap.value,
})
</script>
