<template>
  <div class="space-y-4">
    <div>
      <label class="block text-sm font-medium mb-2">Выберите растение</label>
      <select
        v-model="selectedPlantId"
        class="input-select w-full"
      >
        <option :value="null">
          Выберите растение
        </option>
        <option
          v-for="plant in availablePlants"
          :key="plant.id"
          :value="plant.id"
        >
          {{ plant.name }} {{ plant.variety ? `(${plant.variety})` : "" }}
        </option>
      </select>
    </div>
  </div>
</template>

<script setup lang="ts">
interface PlantOption {
  id: number;
  name: string;
  variety?: string | null;
}

interface Props {
  availablePlants: PlantOption[];
}

defineProps<Props>();

const selectedPlantId = defineModel<number | null>('selectedPlantId', { required: true });
</script>
