<template>
  <div class="space-y-5">
    <section class="p-4 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] space-y-4">
      <h3 class="text-sm font-semibold">
        Период цикла
      </h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label class="text-sm">
          <span class="block font-medium mb-2">Дата начала</span>
          <input
            v-model="startedAt"
            type="datetime-local"
            class="input-field w-full"
            :min="minStartDate"
            required
          />
        </label>
        <label class="text-sm">
          <span class="block font-medium mb-2">Ожидаемая дата сбора (опционально)</span>
          <input
            v-model="expectedHarvestAt"
            type="date"
            class="input-field w-full"
            :min="startedAt ? startedAt.slice(0, 10) : undefined"
          />
        </label>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
interface Props {
  minStartDate?: string;
}

defineProps<Props>();

const startedAt = defineModel<string>('startedAt', { required: true });
const expectedHarvestAt = defineModel<string>('expectedHarvestAt', { required: true });
</script>
