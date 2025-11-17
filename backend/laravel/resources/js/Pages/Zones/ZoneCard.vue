<template>
  <div class="rounded-xl border border-neutral-800 bg-neutral-925 p-4">
    <div class="flex items-center justify-between">
      <div class="text-sm font-semibold">{{ zone.name }}</div>
      <Badge :variant="variant">{{ zone.status }}</Badge>
    </div>
    <div class="mt-2 text-xs text-neutral-300">
      <div v-if="zone.description">{{ zone.description }}</div>
      <div v-if="zone.greenhouse" class="mt-1">Теплица: {{ zone.greenhouse.name }}</div>
    </div>
    <div class="mt-3 flex gap-2">
      <Link :href="`/zones/${zone.id}`" class="inline-block">
        <Button size="sm" variant="secondary">Подробнее</Button>
      </Link>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Link } from '@inertiajs/vue3'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'

const props = defineProps({
  zone: { type: Object, required: true },
})

const variant = computed(() => {
  switch (props.zone.status) {
    case 'RUNNING': return 'success'
    case 'PAUSED': return 'neutral'
    case 'WARNING': return 'warning'
    case 'ALARM': return 'danger'
    default: return 'neutral'
  }
})
</script>

