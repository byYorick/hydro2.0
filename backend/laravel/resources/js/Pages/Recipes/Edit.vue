<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">{{ recipe.id ? 'Редактировать рецепт' : 'Создать рецепт' }}</h1>
    <Card>
      <form class="space-y-3" @submit.prevent="onSave">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label for="recipe-name" class="block text-xs text-neutral-400 mb-1">Название</label>
            <input id="recipe-name" name="name" v-model="form.name" data-testid="recipe-name-input" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors.name ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
            <div v-if="form.errors.name" class="text-xs text-red-400 mt-1">{{ form.errors.name }}</div>
          </div>
          <div>
            <label for="recipe-description" class="block text-xs text-neutral-400 mb-1">Описание</label>
            <input id="recipe-description" name="description" v-model="form.description" data-testid="recipe-description-input" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors.description ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
            <div v-if="form.errors.description" class="text-xs text-red-400 mt-1">{{ form.errors.description }}</div>
          </div>
        </div>

        <div>
          <div class="text-sm font-semibold mb-2">Фазы</div>
          <div v-for="(p, i) in sortedPhases" :key="p.id || i" class="rounded-lg border border-neutral-800 p-3 mb-2">
            <div class="grid grid-cols-1 md:grid-cols-6 gap-2">
              <div>
                <label :for="`phase-${i}-index`" class="sr-only">Индекс фазы</label>
                <input :id="`phase-${i}-index`" :name="`phases[${i}][phase_index]`" v-model.number="p.phase_index" type="number" min="0" placeholder="Индекс" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors[`phases.${i}.phase_index`] ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
                <div v-if="form.errors[`phases.${i}.phase_index`]" class="text-xs text-red-400 mt-1">{{ form.errors[`phases.${i}.phase_index`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-name`" class="sr-only">Имя фазы</label>
                <input :id="`phase-${i}-name`" :name="`phases[${i}][name]`" v-model="p.name" placeholder="Имя фазы" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors[`phases.${i}.name`] ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
                <div v-if="form.errors[`phases.${i}.name`]" class="text-xs text-red-400 mt-1">{{ form.errors[`phases.${i}.name`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-duration`" class="sr-only">Длительность (часов)</label>
                <input :id="`phase-${i}-duration`" :name="`phases[${i}][duration_hours]`" v-model.number="p.duration_hours" type="number" min="1" placeholder="часов" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors[`phases.${i}.duration_hours`] ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
                <div v-if="form.errors[`phases.${i}.duration_hours`]" class="text-xs text-red-400 mt-1">{{ form.errors[`phases.${i}.duration_hours`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-ph-min`" class="sr-only">pH минимум</label>
                <input :id="`phase-${i}-ph-min`" :name="`phases[${i}][targets][ph][min]`" v-model.number="p.targets.ph.min" type="number" step="0.1" placeholder="pH min" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors[`phases.${i}.targets.ph.min`] ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
                <div v-if="form.errors[`phases.${i}.targets.ph.min`]" class="text-xs text-red-400 mt-1">{{ form.errors[`phases.${i}.targets.ph.min`] }}</div>
              </div>
              <div>
                <label :for="`phase-${i}-ph-max`" class="sr-only">pH максимум</label>
                <input :id="`phase-${i}-ph-max`" :name="`phases[${i}][targets][ph][max]`" v-model.number="p.targets.ph.max" type="number" step="0.1" placeholder="pH max" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors[`phases.${i}.targets.ph.max`] ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
                <div v-if="form.errors[`phases.${i}.targets.ph.max`]" class="text-xs text-red-400 mt-1">{{ form.errors[`phases.${i}.targets.ph.max`] }}</div>
              </div>
              <div class="md:col-span-2 grid grid-cols-2 gap-2">
                <div>
                  <label :for="`phase-${i}-ec-min`" class="sr-only">EC минимум</label>
                  <input :id="`phase-${i}-ec-min`" :name="`phases[${i}][targets][ec][min]`" v-model.number="p.targets.ec.min" type="number" step="0.1" placeholder="EC min" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors[`phases.${i}.targets.ec.min`] ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
                  <div v-if="form.errors[`phases.${i}.targets.ec.min`]" class="text-xs text-red-400 mt-1">{{ form.errors[`phases.${i}.targets.ec.min`] }}</div>
                </div>
                <div>
                  <label :for="`phase-${i}-ec-max`" class="sr-only">EC максимум</label>
                  <input :id="`phase-${i}-ec-max`" :name="`phases[${i}][targets][ec][max]`" v-model.number="p.targets.ec.max" type="number" step="0.1" placeholder="EC max" class="h-9 w-full rounded-md border px-2 text-sm" :class="form.errors[`phases.${i}.targets.ec.max`] ? 'border-red-500 bg-red-900/20' : 'border-neutral-700 bg-neutral-900'" />
                  <div v-if="form.errors[`phases.${i}.targets.ec.max`]" class="text-xs text-red-400 mt-1">{{ form.errors[`phases.${i}.targets.ec.max`] }}</div>
                </div>
              </div>
              <div class="md:col-span-6 grid grid-cols-3 gap-2 mt-2">
                <input :id="`phase-${i}-temp-air`" :name="`phases[${i}][targets][temp_air]`" v-model.number="p.targets.temp_air" type="number" step="0.1" placeholder="Температура" class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900" />
                <input :id="`phase-${i}-humidity-air`" :name="`phases[${i}][targets][humidity_air]`" v-model.number="p.targets.humidity_air" type="number" step="0.1" placeholder="Влажность" class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900" />
                <input :id="`phase-${i}-light-hours`" :name="`phases[${i}][targets][light_hours]`" v-model.number="p.targets.light_hours" type="number" placeholder="Свет (часов)" class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900" />
              </div>
              <div class="md:col-span-6 grid grid-cols-2 gap-2 mt-2">
                <input :id="`phase-${i}-irrigation-interval`" :name="`phases[${i}][targets][irrigation_interval_sec]`" v-model.number="p.targets.irrigation_interval_sec" type="number" placeholder="Интервал полива (сек)" class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900" />
                <input :id="`phase-${i}-irrigation-duration`" :name="`phases[${i}][targets][irrigation_duration_sec]`" v-model.number="p.targets.irrigation_duration_sec" type="number" placeholder="Длительность полива (сек)" class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900" />
              </div>
            </div>
          </div>
          <Button size="sm" variant="secondary" type="button" @click="onAddPhase">Добавить фазу</Button>
        </div>

        <div class="flex justify-end gap-2">
          <Link href="/recipes">
            <Button size="sm" variant="secondary" type="button">Отмена</Button>
          </Link>
          <Button size="sm" type="submit" :disabled="form.processing">{{ form.processing ? 'Сохранение...' : 'Сохранить' }}</Button>
        </div>
      </form>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Link, usePage, router, useForm } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { logger } from '@/utils/logger'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
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
  phases: RecipePhaseForm[]
}

interface PageProps {
  recipe?: Recipe
}

const page = usePage<PageProps>()
const recipe = page.props.recipe || {}

const form = useForm<RecipeFormData>({
  name: recipe.name || '',
  description: recipe.description || '',
  phases: (recipe.phases || []).length > 0 ? (recipe.phases || []).map((p: RecipePhase) => ({
    id: p.id,
    phase_index: p.phase_index || 0,
    name: p.name || '',
    duration_hours: p.duration_hours || 24,
    targets: {
      ph: { 
        min: typeof p.targets?.ph === 'object' ? (p.targets.ph as any).min : (p.targets?.ph || 5.8),
        max: typeof p.targets?.ph === 'object' ? (p.targets.ph as any).max : (p.targets?.ph || 6.0)
      },
      ec: { 
        min: typeof p.targets?.ec === 'object' ? (p.targets.ec as any).min : (p.targets?.ec || 1.2),
        max: typeof p.targets?.ec === 'object' ? (p.targets.ec as any).max : (p.targets?.ec || 1.6)
      },
      temp_air: p.targets?.temp_air || null,
      humidity_air: p.targets?.humidity_air || null,
      light_hours: p.targets?.light_hours || null,
      irrigation_interval_sec: p.targets?.irrigation_interval_sec || null,
      irrigation_duration_sec: p.targets?.irrigation_duration_sec || null,
    },
  })) : [{
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
  try {
    if (recipe.id) {
      // Обновление существующего рецепта
      await form.patch(`/api/recipes/${recipe.id}`, {
        preserveScroll: true,
        onSuccess: () => {
          router.visit(`/recipes/${recipe.id}`)
        }
      })
    } else {
      // Создание нового рецепта - сначала создаем рецепт, потом фазы
      const recipeResponse = await api.post<{ data?: { id: number } }>(
        '/recipes',
        {
          name: form.name,
          description: form.description
        }
      )
      
      const recipeId = (recipeResponse.data as { data?: { id: number } })?.data?.id
      
      if (!recipeId) {
        throw new Error('Recipe ID not found in response')
      }
      
      // Создаем фазы
      for (const phase of form.phases) {
        await api.post(`/recipes/${recipeId}/phases`, {
          phase_index: phase.phase_index,
          name: phase.name,
          duration_hours: phase.duration_hours,
          targets: {
            ph: phase.targets.ph,
            ec: phase.targets.ec,
            temp_air: phase.targets.temp_air || null,
            humidity_air: phase.targets.humidity_air || null,
            light_hours: phase.targets.light_hours || null,
            irrigation_interval_sec: phase.targets.irrigation_interval_sec || null,
            irrigation_duration_sec: phase.targets.irrigation_duration_sec || null,
          }
        })
      }
      
      showToast('Рецепт успешно создан', 'success', TOAST_TIMEOUT.NORMAL)
      router.visit(`/recipes/${recipeId}`)
    }
  } catch (error) {
    logger.error('Failed to save recipe:', error)
  }
}
</script>

