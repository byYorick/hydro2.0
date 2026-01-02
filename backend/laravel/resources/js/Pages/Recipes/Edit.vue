<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">{{ recipe.id ? 'Редактировать рецепт' : 'Создать рецепт' }}</h1>
    <Card>
      <form class="space-y-3" @submit.prevent="onSave">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label for="recipe-name" class="block text-xs text-[color:var(--text-muted)] mb-1">Название</label>
            <input id="recipe-name" name="name" v-model="form.name" data-testid="recipe-name-input" class="input-field" :class="(form.errors as any).name ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
            <div v-if="(form.errors as any).name" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ (form.errors as any).name }}</div>
          </div>
          <div>
            <label for="recipe-description" class="block text-xs text-[color:var(--text-muted)] mb-1">Описание</label>
            <input id="recipe-description" name="description" v-model="form.description" data-testid="recipe-description-input" class="input-field" :class="(form.errors as any).description ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
            <div v-if="(form.errors as any).description" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ (form.errors as any).description }}</div>
          </div>
          <div>
            <label for="recipe-plant" class="block text-xs text-[color:var(--text-muted)] mb-1">Культура</label>
            <select
              id="recipe-plant"
              name="plant_id"
              v-model.number="form.plant_id"
              class="input-field"
              :disabled="plantsLoading"
              :class="(form.errors as any).plant_id ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''"
            >
              <option :value="null" disabled>Выберите культуру</option>
              <option v-for="plant in plants" :key="plant.id" :value="plant.id">
                {{ plant.name }}
              </option>
            </select>
            <div v-if="(form.errors as any).plant_id" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ (form.errors as any).plant_id }}</div>
            <div v-else-if="!plantsLoading && plants.length === 0" class="text-xs text-[color:var(--text-dim)] mt-1">
              Нет доступных культур — добавьте культуру в справочнике.
            </div>
          </div>
        </div>

        <div>
          <div class="text-sm font-semibold mb-2">Фазы</div>
          <div v-for="(p, i) in sortedPhases" :key="p.id || i" :data-testid="`phase-item-${i}`" class="rounded-lg border border-[color:var(--border-muted)] p-3 mb-2">
            <div class="grid grid-cols-1 md:grid-cols-6 gap-2">
              <div>
                <label :for="`phase-${i}-index`" class="sr-only">Индекс фазы</label>
                <input :id="`phase-${i}-index`" :name="`phases[${i}][phase_index]`" v-model.number="p.phase_index" type="number" min="0" placeholder="Индекс" :data-testid="`phase-index-input-${i}`" class="input-field" :class="form.errors[`phases.${i}.phase_index`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
                <div v-if="form.errors[`phases.${i}.phase_index`]" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ form.errors[`phases.${i}.phase_index`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-name`" class="sr-only">Имя фазы</label>
                <input :id="`phase-${i}-name`" :name="`phases[${i}][name]`" v-model="p.name" placeholder="Имя фазы" :data-testid="`phase-name-input-${i}`" class="input-field" :class="form.errors[`phases.${i}.name`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
                <div v-if="form.errors[`phases.${i}.name`]" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ form.errors[`phases.${i}.name`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-duration`" class="sr-only">Длительность (часов)</label>
                <input :id="`phase-${i}-duration`" :name="`phases[${i}][duration_hours]`" v-model.number="p.duration_hours" type="number" min="1" placeholder="часов" :data-testid="`phase-duration-input-${i}`" class="input-field" :class="form.errors[`phases.${i}.duration_hours`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
                <div v-if="form.errors[`phases.${i}.duration_hours`]" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ form.errors[`phases.${i}.duration_hours`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-ph-min`" class="sr-only">pH минимум</label>
                <input :id="`phase-${i}-ph-min`" :name="`phases[${i}][targets][ph][min]`" v-model.number="p.targets.ph.min" type="number" step="0.1" placeholder="pH min" class="input-field" :class="form.errors[`phases.${i}.targets.ph.min`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
                <div v-if="form.errors[`phases.${i}.targets.ph.min`]" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ form.errors[`phases.${i}.targets.ph.min`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-ph-max`" class="sr-only">pH максимум</label>
                <input :id="`phase-${i}-ph-max`" :name="`phases[${i}][targets][ph][max]`" v-model.number="p.targets.ph.max" type="number" step="0.1" placeholder="pH max" class="input-field" :class="form.errors[`phases.${i}.targets.ph.max`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
                <div v-if="form.errors[`phases.${i}.targets.ph.max`]" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ form.errors[`phases.${i}.targets.ph.max`] }}</div>
              </div>
              <div class="md:col-span-2 grid grid-cols-2 gap-2">
                <div>
                  <label :for="`phase-${i}-ec-min`" class="sr-only">EC минимум</label>
                  <input :id="`phase-${i}-ec-min`" :name="`phases[${i}][targets][ec][min]`" v-model.number="p.targets.ec.min" type="number" step="0.1" placeholder="EC min" class="input-field" :class="form.errors[`phases.${i}.targets.ec.min`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
                  <div v-if="form.errors[`phases.${i}.targets.ec.min`]" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ form.errors[`phases.${i}.targets.ec.min`] }}</div>
                </div>
                <div>
                  <label :for="`phase-${i}-ec-max`" class="sr-only">EC максимум</label>
                  <input :id="`phase-${i}-ec-max`" :name="`phases[${i}][targets][ec][max]`" v-model.number="p.targets.ec.max" type="number" step="0.1" placeholder="EC max" class="input-field" :class="form.errors[`phases.${i}.targets.ec.max`] ? 'border-[color:var(--accent-red)] bg-[color:var(--badge-danger-bg)]' : ''" />
                  <div v-if="form.errors[`phases.${i}.targets.ec.max`]" class="text-xs text-[color:var(--badge-danger-text)] mt-1">{{ form.errors[`phases.${i}.targets.ec.max`] }}</div>
                </div>
              </div>
              <div class="md:col-span-6 grid grid-cols-3 gap-2 mt-2">
                <input :id="`phase-${i}-temp-air`" :name="`phases[${i}][targets][temp_air]`" v-model.number="p.targets.temp_air" type="number" step="0.1" placeholder="Температура" class="input-field" />
                <input :id="`phase-${i}-humidity-air`" :name="`phases[${i}][targets][humidity_air]`" v-model.number="p.targets.humidity_air" type="number" step="0.1" placeholder="Влажность" class="input-field" />
                <input :id="`phase-${i}-light-hours`" :name="`phases[${i}][targets][light_hours]`" v-model.number="p.targets.light_hours" type="number" placeholder="Свет (часов)" class="input-field" />
              </div>
              <div class="md:col-span-6 grid grid-cols-2 gap-2 mt-2">
                <input :id="`phase-${i}-irrigation-interval`" :name="`phases[${i}][targets][irrigation_interval_sec]`" v-model.number="p.targets.irrigation_interval_sec" type="number" placeholder="Интервал полива (сек)" class="input-field" />
                <input :id="`phase-${i}-irrigation-duration`" :name="`phases[${i}][targets][irrigation_duration_sec]`" v-model.number="p.targets.irrigation_duration_sec" type="number" placeholder="Длительность полива (сек)" class="input-field" />
              </div>
            </div>
          </div>
          <Button size="sm" variant="secondary" type="button" @click="onAddPhase" data-testid="add-phase-button">Добавить фазу</Button>
        </div>

        <div class="flex justify-end gap-2">
          <Link href="/recipes">
            <Button size="sm" variant="secondary" type="button" data-testid="cancel-button">Отмена</Button>
          </Link>
          <Button size="sm" type="submit" :disabled="form.processing" data-testid="save-recipe-button">{{ form.processing ? 'Сохранение...' : 'Сохранить' }}</Button>
        </div>
      </form>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Link, usePage, router, useForm } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import type { Recipe, RecipePhase } from '@/types'

const { showToast } = useToast()
const { api } = useApi(showToast)

interface RecipePhaseForm {
  id?: number
  phase_index: number
  name: string
  duration_hours: number
  targets: {
    ph: { min: number; max: number }
    ec: { min: number; max: number }
    temp_air?: number
    humidity_air?: number
    light_hours?: number
    irrigation_interval_sec?: number
    irrigation_duration_sec?: number
  }
}

interface RecipeFormData {
  name: string
  description: string
  plant_id: number | null
  phases: RecipePhaseForm[]
}

interface PageProps {
  recipe?: Recipe
  [key: string]: any
}

const page = usePage<PageProps>()
const recipe = (page.props.recipe || {}) as Partial<Recipe>

interface PlantOption {
  id: number
  name: string
}

const plants = ref<PlantOption[]>([])
const plantsLoading = ref(false)
const initialPlantId = recipe.plants?.[0]?.id ?? null

const form = useForm<RecipeFormData>({
  name: recipe.name || '',
  description: recipe.description || '',
  plant_id: initialPlantId,
  phases: (recipe.phases || []).length > 0 ? (recipe.phases || []).map((p: RecipePhase & Record<string, any>) => {
    const phMin = typeof p.ph_min === 'number' ? p.ph_min : (typeof p.targets?.ph?.min === 'number' ? p.targets.ph.min : 5.8)
    const phMax = typeof p.ph_max === 'number' ? p.ph_max : (typeof p.targets?.ph?.max === 'number' ? p.targets.ph.max : 6.0)
    const ecMin = typeof p.ec_min === 'number' ? p.ec_min : (typeof p.targets?.ec?.min === 'number' ? p.targets.ec.min : 1.2)
    const ecMax = typeof p.ec_max === 'number' ? p.ec_max : (typeof p.targets?.ec?.max === 'number' ? p.targets.ec.max : 1.6)

    return {
      id: p.id,
      phase_index: p.phase_index || 0,
      name: p.name || '',
      duration_hours: p.duration_hours || 24,
      targets: {
        ph: { min: phMin, max: phMax },
        ec: { min: ecMin, max: ecMax },
        temp_air: p.temp_air_target ?? p.targets?.temp_air ?? null,
        humidity_air: p.humidity_target ?? p.targets?.humidity_air ?? null,
        light_hours: p.lighting_photoperiod_hours ?? p.targets?.light_hours ?? null,
        irrigation_interval_sec: p.irrigation_interval_sec ?? p.targets?.irrigation_interval_sec ?? null,
        irrigation_duration_sec: p.irrigation_duration_sec ?? p.targets?.irrigation_duration_sec ?? null,
      },
    }
  }) : [{
    phase_index: 0,
    name: '',
    duration_hours: 24,
    targets: {
      ph: { min: 5.6, max: 6.0 },
      ec: { min: 1.2, max: 1.6 },
      temp_air: null,
      humidity_air: null,
      light_hours: null,
      irrigation_interval_sec: null,
      irrigation_duration_sec: null,
    },
  }],
})

const loadPlants = async (): Promise<void> => {
  try {
    plantsLoading.value = true
    const response = await api.get('/plants')
    const data = response.data?.data || []
    plants.value = Array.isArray(data)
      ? data.map((plant: any) => ({ id: plant.id, name: plant.name }))
      : []

    if (!form.plant_id && recipe.id) {
      const recipeResponse = await api.get(`/recipes/${recipe.id}`)
      const recipeData = recipeResponse.data?.data || {}
      const apiPlantId = recipeData.plants?.[0]?.id ?? null
      if (apiPlantId) {
        form.plant_id = apiPlantId
      }
    }

    if (!form.plant_id && plants.value.length === 1) {
      form.plant_id = plants.value[0].id
    }
  } catch (error) {
    logger.error('Failed to load plants:', error)
    showToast('Не удалось загрузить список культур', 'error', TOAST_TIMEOUT.NORMAL)
  } finally {
    plantsLoading.value = false
  }
}

onMounted(() => {
  loadPlants()
})

const sortedPhases = computed<RecipePhaseForm[]>(() => {
  return [...form.phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
})

const onAddPhase = (): void => {
  const maxIndex = form.phases.length > 0 
    ? Math.max(...form.phases.map(p => p.phase_index || 0))
    : -1
  form.phases.push({
    phase_index: maxIndex + 1,
    name: '',
    duration_hours: 24,
    targets: {
      ph: { min: 5.6, max: 6.0 },
      ec: { min: 1.2, max: 1.6 },
      temp_air: null,
      humidity_air: null,
      light_hours: null,
      irrigation_interval_sec: null,
      irrigation_duration_sec: null,
    },
  })
}

const onSave = async (): Promise<void> => {
  if (!form.plant_id) {
    showToast('Выберите культуру для рецепта', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  try {
    form.processing = true
    if (recipe.id) {
      await api.patch(`/recipes/${recipe.id}`, {
        name: form.name,
        description: form.description,
        plant_id: form.plant_id,
      })

      let draftRevisionId = (recipe as any).draft_revision_id as number | undefined
      const hasDraft = !!draftRevisionId

      if (!draftRevisionId) {
        const revisionResponse = await api.post<{ data?: { id: number } } | { id: number }>(
          `/recipes/${recipe.id}/revisions`,
          { description: 'Auto draft' }
        )
        const revision = (revisionResponse.data as { data?: { id: number } })?.data || (revisionResponse.data as { id: number })
        draftRevisionId = revision?.id
      }

      if (!draftRevisionId) {
        throw new Error('Draft revision ID not found')
      }

      const existingPhaseIds = hasDraft
        ? (recipe.phases || []).map((p: any) => p.id).filter((id: number | undefined) => !!id)
        : []
      const currentPhaseIds = form.phases.map(p => p.id).filter((id): id is number => !!id)

      for (const phase of form.phases) {
        const phMin = phase.targets.ph.min
        const phMax = phase.targets.ph.max
        const ecMin = phase.targets.ec.min
        const ecMax = phase.targets.ec.max
        const phTarget = (phMin + phMax) / 2
        const ecTarget = (ecMin + ecMax) / 2

        const payload = {
          phase_index: phase.phase_index,
          name: phase.name,
          duration_hours: phase.duration_hours,
          ph_target: phTarget,
          ph_min: phMin,
          ph_max: phMax,
          ec_target: ecTarget,
          ec_min: ecMin,
          ec_max: ecMax,
          temp_air_target: phase.targets.temp_air || null,
          humidity_target: phase.targets.humidity_air || null,
          lighting_photoperiod_hours: phase.targets.light_hours || null,
          irrigation_interval_sec: phase.targets.irrigation_interval_sec || null,
          irrigation_duration_sec: phase.targets.irrigation_duration_sec || null,
        }

        if (hasDraft && phase.id) {
          await api.patch(`/recipe-revision-phases/${phase.id}`, payload)
        } else {
          await api.post(`/recipe-revisions/${draftRevisionId}/phases`, payload)
        }
      }

      if (hasDraft) {
        const removedIds = existingPhaseIds.filter(id => !currentPhaseIds.includes(id))
        for (const removedId of removedIds) {
          await api.delete(`/recipe-revision-phases/${removedId}`)
        }
      }

      await api.post(`/recipe-revisions/${draftRevisionId}/publish`)
      showToast('Рецепт успешно обновлен', 'success', TOAST_TIMEOUT.NORMAL)
      router.visit(`/recipes/${recipe.id}`)
    } else {
      // Создание нового рецепта - сначала создаем рецепт, потом фазы
      const recipeResponse = await api.post<{ data?: { id: number } }>(
        '/recipes',
        {
          name: form.name,
          description: form.description,
          plant_id: form.plant_id,
        }
      )
      
      const recipeId = (recipeResponse.data as { data?: { id: number } })?.data?.id
      
      if (!recipeId) {
        throw new Error('Recipe ID not found in response')
      }

      const revisionResponse = await api.post<{ data?: { id: number } } | { id: number }>(
        `/recipes/${recipeId}/revisions`,
        { description: 'Initial revision' }
      )
      const revision = (revisionResponse.data as { data?: { id: number } })?.data || (revisionResponse.data as { id: number })
      const revisionId = revision?.id

      if (!revisionId) {
        throw new Error('Recipe revision ID not found in response')
      }

      for (const phase of form.phases) {
        const phMin = phase.targets.ph.min
        const phMax = phase.targets.ph.max
        const ecMin = phase.targets.ec.min
        const ecMax = phase.targets.ec.max
        const phTarget = (phMin + phMax) / 2
        const ecTarget = (ecMin + ecMax) / 2

        await api.post(`/recipe-revisions/${revisionId}/phases`, {
          phase_index: phase.phase_index,
          name: phase.name,
          duration_hours: phase.duration_hours,
          ph_target: phTarget,
          ph_min: phMin,
          ph_max: phMax,
          ec_target: ecTarget,
          ec_min: ecMin,
          ec_max: ecMax,
          temp_air_target: phase.targets.temp_air || null,
          humidity_target: phase.targets.humidity_air || null,
          lighting_photoperiod_hours: phase.targets.light_hours || null,
          irrigation_interval_sec: phase.targets.irrigation_interval_sec || null,
          irrigation_duration_sec: phase.targets.irrigation_duration_sec || null,
        })
      }

      await api.post(`/recipe-revisions/${revisionId}/publish`)

      showToast('Рецепт успешно создан', 'success', TOAST_TIMEOUT.NORMAL)
      router.visit(`/recipes/${recipeId}`)
    }
  } catch (error) {
    logger.error('Failed to save recipe:', error)
  } finally {
    form.processing = false
  }
}
</script>
