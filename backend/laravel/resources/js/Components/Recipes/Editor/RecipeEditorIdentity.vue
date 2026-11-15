<template>
  <div class="space-y-3">
    <div
      v-if="!hidePlantSelect"
      class="rounded-md border border-[color:var(--border-muted)] p-2.5 space-y-2"
    >
      <div class="text-[12px] font-bold uppercase tracking-[0.16em] text-[color:var(--text-muted)]">
        Культура
      </div>

      <div
        v-if="plantMode === 'select'"
        class="grid gap-2 md:grid-cols-[1fr_auto]"
      >
        <SelectField
          id="recipe-plant"
          v-model.number="form.plant_id"
          :disabled="plantsLoading"
        >
          <option :value="null">
            Выберите культуру
          </option>
          <option
            v-for="plant in plants"
            :key="plant.id"
            :value="plant.id"
          >
            {{ plant.name }}
          </option>
        </SelectField>
        <Button
          size="sm"
          variant="secondary"
          @click="plantMode = 'create'"
        >
          Создать
        </Button>
      </div>

      <div
        v-else
        class="space-y-2"
      >
        <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Название растения</label>
            <TextField
              v-model="newPlantName"
              placeholder="Томат Черри"
            />
          </div>
          <div>
            <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Вид (species)</label>
            <TextField
              v-model="newPlantSpecies"
              placeholder="Solanum lycopersicum"
            />
          </div>
          <div>
            <label class="block text-[12px] text-[color:var(--text-primary)] font-medium mb-1">Сорт (variety)</label>
            <TextField
              v-model="newPlantVariety"
              placeholder="Cherry"
            />
          </div>
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            :disabled="!newPlantName.trim() || creatingPlant"
            @click="createPlant"
          >
            {{ creatingPlant ? 'Создание...' : 'Создать растение' }}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            @click="plantMode = 'select'"
          >
            Отмена
          </Button>
        </div>
      </div>
    </div>
    <div
      v-else
      class="rounded-md border border-[color:var(--border-muted)] bg-[color:var(--bg-muted)] px-2.5 py-1.5 text-xs text-[color:var(--text-muted)]"
    >
      Культура: <span class="font-semibold text-[color:var(--text-primary)]">{{ lockedPlantLabel || 'Выбрана на предыдущем шаге' }}</span>
    </div>
    <div>
      <div class="text-[12px] text-[color:var(--text-primary)] font-medium mb-1">
        Название рецепта
      </div>
      <div
        class="text-xs font-semibold text-[color:var(--text-primary)]"
        data-testid="recipe-name-display"
      >
        {{ recipeName }}
      </div>
      <TextField
        id="recipe-description"
        v-model="recipeLabel"
        data-testid="recipe-name-input"
        class="mt-1"
        placeholder="Veg+Bloom, зима 2026..."
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import SelectField from '@/Components/SelectField.vue'
import TextField from '@/Components/TextField.vue'
import Button from '@/Components/Button.vue'
import { ref } from 'vue'
import type { PlantOption, RecipeEditorFormState } from '@/composables/recipeEditorShared'
import { useRecipeIdentity } from '@/composables/useRecipeIdentity'
import { api } from '@/services/api'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
const props = defineProps<{ plants: PlantOption[]; plantsLoading: boolean; hidePlantSelect: boolean; lockedPlantLabel: string | null }>()
const form = defineModel<RecipeEditorFormState>('form', { required: true })
const emit = defineEmits<{ 'plant-created': [plant: PlantOption] }>()
const { showToast } = useToast()
const plantMode = ref<'select' | 'create'>('select')
const newPlantName = ref('')
const newPlantSpecies = ref('')
const newPlantVariety = ref('')
const creatingPlant = ref(false)
const { recipeLabel, recipeName } = useRecipeIdentity(form, () => props.plants)


async function createPlant(): Promise<void> {
  const name = newPlantName.value.trim()
  if (!name) return
  creatingPlant.value = true
  try {
    const plant = await api.plants.create({
      name,
      species: newPlantSpecies.value.trim() || null,
      variety: newPlantVariety.value.trim() || null,
    })
    form.value.plant_id = plant.id
    emit('plant-created', { id: plant.id, name: plant.name })
    plantMode.value = 'select'
    newPlantName.value = ''
    newPlantSpecies.value = ''
    newPlantVariety.value = ''
    showToast(`Растение "${plant.name}" создано`, 'success', TOAST_TIMEOUT.NORMAL)
  } catch (err: unknown) {
    showToast('Ошибка создания растения', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    creatingPlant.value = false
  }
}


</script>
