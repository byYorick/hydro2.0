<template>
  <DataTable :headers="['Channel', 'Type', 'Last', 'Actions']" :rows="rows">
    <template #{"cell-3"}="{ value }">
      <div class="flex gap-2">
        <Button size="sm" variant="secondary" @click="$emit('test', value)">Test</Button>
      </div>
    </template>
  </DataTable>
</template>

<script setup>
import { computed } from 'vue'
import DataTable from '@/Components/DataTable.vue'
import Button from '@/Components/Button.vue'

const props = defineProps({
  channels: { type: Array, default: () => [] }, // [{channel,type,metric,unit}]
})

const rows = computed(() => props.channels.map(c => [
  c.channel || c.name || '-',
  c.type || '-',
  c.metric ? `${c.metric}${c.unit ? ` (${c.unit})` : ''}` : '-',
  c.channel || c.name || '-',
]))
</script>

