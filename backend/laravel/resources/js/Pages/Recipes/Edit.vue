<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Редактировать рецепт</h1>
    <Card>
      <form class="space-y-3" @submit.prevent="onSave">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-neutral-400 mb-1">Название</label>
            <input v-model="form.name" class="h-9 w-full rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
          </div>
          <div>
            <label class="block text-xs text-neutral-400 mb-1">Описание</label>
            <input v-model="form.description" class="h-9 w-full rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
          </div>
        </div>

        <div>
          <div class="text-sm font-semibold mb-2">Фазы</div>
          <div v-for="(p, i) in sortedPhases" :key="p.id || i" class="rounded-lg border border-neutral-800 p-3 mb-2">
            <div class="grid grid-cols-1 md:grid-cols-6 gap-2">
              <input v-model.number="p.phase_index" type="number" min="0" placeholder="Индекс" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
              <input v-model="p.name" placeholder="Имя фазы" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
              <input v-model.number="p.duration_hours" type="number" min="1" placeholder="часов" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
              <input v-model.number="p.targets.ph.min" type="number" step="0.1" placeholder="pH min" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
              <input v-model.number="p.targets.ph.max" type="number" step="0.1" placeholder="pH max" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
              <div class="md:col-span-2 grid grid-cols-2 gap-2">
                <input v-model.number="p.targets.ec.min" type="number" step="0.1" placeholder="EC min" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
                <input v-model.number="p.targets.ec.max" type="number" step="0.1" placeholder="EC max" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
              </div>
            </div>
          </div>
          <Button size="sm" variant="secondary" type="button" @click="onAddPhase">Добавить фазу</Button>
        </div>

        <div class="flex justify-end gap-2">
          <Link href="/recipes">
            <Button size="sm" variant="secondary" type="button">Отмена</Button>
          </Link>
          <Button size="sm" type="submit" :disabled="saving">{{ saving ? 'Сохранение...' : 'Сохранить' }}</Button>
        </div>
      </form>
    </Card>
  </AppLayout>
</template>

<script setup>
import { reactive, computed, ref } from 'vue'
import { Link, usePage, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import axios from 'axios'

const page = usePage()
const recipe = page.props.recipe || {}

const saving = ref(false)

const form = reactive({
  name: recipe.name || '',
  description: recipe.description || '',
  phases: (recipe.phases || []).map(p => ({
    id: p.id,
    phase_index: p.phase_index || 0,
    name: p.name || '',
    duration_hours: p.duration_hours || 24,
    targets: {
      ph: { min: p.targets?.ph?.min || 5.6, max: p.targets?.ph?.max || 6.0 },
      ec: { min: p.targets?.ec?.min || 1.2, max: p.targets?.ec?.max || 1.6 },
    },
  })),
})

const sortedPhases = computed(() => {
  return [...form.phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
})

const onAddPhase = () => {
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
    },
  })
}

const onSave = async () => {
  saving.value = true
  try {
    await axios.patch(`/api/recipes/${recipe.id}`, {
      name: form.name,
      description: form.description,
    })
    // Обновить фазы отдельно через API (нужно будет добавить эндпоинт)
    router.visit(`/recipes/${recipe.id}`)
  } catch (err) {
    console.error('Failed to save recipe:', err)
  } finally {
    saving.value = false
  }
}
</script>

