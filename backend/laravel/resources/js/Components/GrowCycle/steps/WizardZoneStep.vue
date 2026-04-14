<template>
  <div class="space-y-4">
    <div v-if="zoneId">
      <div class="p-4 rounded-lg bg-[color:var(--badge-success-bg)] border border-[color:var(--badge-success-border)]">
        <div class="text-sm font-medium text-[color:var(--badge-success-text)]">
          Зона выбрана: {{ zoneName || `Зона #${zoneId}` }}
        </div>
      </div>
    </div>
    <div v-else>
      <label class="block text-sm font-medium mb-2">Выберите зону</label>
      <select
        v-model="selectedZoneId"
        class="input-select w-full"
        @change="$emit('zone-selected')"
      >
        <option :value="null">
          Выберите зону
        </option>
        <option
          v-for="zone in availableZones"
          :key="zone.id"
          :value="zone.id"
        >
          {{ zone.name }} ({{ zone.greenhouse?.name || "" }})
        </option>
      </select>
    </div>
  </div>
</template>

<script setup lang="ts">
interface ZoneOption {
  id: number;
  name: string;
  greenhouse?: { name?: string } | null;
}

interface Props {
  zoneId?: number | null;
  zoneName?: string;
  availableZones: ZoneOption[];
}

defineProps<Props>();

defineEmits<{
  'zone-selected': [];
}>();

const selectedZoneId = defineModel<number | null>('selectedZoneId', { required: true });
</script>
