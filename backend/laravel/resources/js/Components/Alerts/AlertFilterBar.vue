<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Фильтр</span>
        <div class="inline-flex items-center rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-1 backdrop-blur gap-1">
          <button
            v-for="status in statusOptions"
            :key="status.value"
            type="button"
            class="h-9 px-3 rounded-full border text-xs font-semibold transition-colors"
            :class="modelValue === status.value
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-transparent text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="$emit('update:modelValue', status.value)"
          >
            {{ status.label }}
          </button>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <input
          :value="query"
          class="input-field h-9 w-full sm:w-72"
          placeholder="Поиск по коду, сообщению, details..."
          @input="$emit('update:query', ($event.target as HTMLInputElement).value)"
        />
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: 'ALL' | 'ACTIVE' | 'RESOLVED'
  query: string
}>()

defineEmits<{
  'update:modelValue': ['ALL' | 'ACTIVE' | 'RESOLVED']
  'update:query': [string]
}>()

const statusOptions: Array<{ value: 'ALL' | 'ACTIVE' | 'RESOLVED', label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ACTIVE', label: 'Активные' },
  { value: 'RESOLVED', label: 'Решённые' },
]
</script>

