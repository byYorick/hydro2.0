<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-lg font-semibold">{{ recipe.name }}</div>
        <div class="text-xs text-neutral-400">
          {{ recipe.description || 'Без описания' }} · Фаз: {{ recipe.phases?.length || 0 }}
        </div>
      </div>
      <div class="flex gap-2">
        <Button size="sm" variant="secondary">Создать копию</Button>
        <Link :href="`/recipes/${recipe.id}/edit`">
          <Button size="sm">Редактировать</Button>
        </Link>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
      <Card class="xl:col-span-2">
        <div class="text-sm font-semibold mb-2">Фазы</div>
        <ul class="text-sm text-neutral-300 space-y-1">
          <li v-for="(p, i) in sortedPhases" :key="p.id || i">
            {{ p.phase_index + 1 }}. {{ p.name }} — 
            {{ formatDuration(p.duration_hours) }} — 
            <span v-if="p.targets?.ph">pH {{ p.targets.ph.min || '-' }}–{{ p.targets.ph.max || '-' }}</span>
            <span v-if="p.targets?.ec">, EC {{ p.targets.ec.min || '-' }}–{{ p.targets.ec.max || '-' }}</span>
          </li>
        </ul>
      </Card>
      <Card>
        <div class="text-sm font-semibold mb-2">Цели по умолчанию</div>
        <div class="text-sm text-neutral-300">Температура: 22–24°C</div>
        <div class="text-sm text-neutral-300">Влажность: 50–60%</div>
        <div class="text-sm text-neutral-300">Свет: 16ч</div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'

const page = usePage()
const recipe = computed(() => page.props.recipe || {})

const sortedPhases = computed(() => {
  const phases = recipe.value.phases || []
  return [...phases].sort((a, b) => (a.phase_index || 0) - (b.phase_index || 0))
})

function formatDuration(hours) {
  if (!hours) return '-'
  if (hours < 24) return `${hours} ч`
  const days = Math.floor(hours / 24)
  const remainder = hours % 24
  if (remainder === 0) return `${days} дн`
  return `${days} дн ${remainder} ч`
}
</script>

