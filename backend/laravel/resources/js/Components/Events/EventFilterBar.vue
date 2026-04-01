<template>
  <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
    <div class="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)]">Тип</span>
        <div class="inline-flex items-center rounded-2xl border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]/70 p-1 backdrop-blur gap-1">
          <button
            v-for="kind in kindOptions"
            :key="kind.value"
            type="button"
            class="h-9 px-3 rounded-full border text-xs font-semibold transition-colors"
            :class="modelValue === kind.value
              ? 'border-[color:var(--accent-cyan)] text-[color:var(--accent-cyan)] bg-[color:var(--bg-elevated)]'
              : 'border-transparent text-[color:var(--text-dim)] hover:border-[color:var(--border-strong)]'"
            @click="$emit('update:modelValue', kind.value)"
          >
            {{ kind.label }}
          </button>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <input
          :value="query"
          class="input-field h-9 w-full sm:w-64"
          placeholder="Поиск по событию..."
          @input="$emit('update:query', ($event.target as HTMLInputElement).value)"
        />
        <Button
          size="sm"
          variant="secondary"
          @click="$emit('export')"
        >
          Экспорт CSV
        </Button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import Button from '@/Components/Button.vue'

type KindFilter = 'ALL' | 'ALERT' | 'WARNING' | 'INFO' | 'ACTION'

defineProps<{
  modelValue: KindFilter
  query: string
}>()

defineEmits<{
  'update:modelValue': [KindFilter]
  'update:query': [string]
  'export': []
}>()

const kindOptions: Array<{ value: KindFilter, label: string }> = [
  { value: 'ALL', label: 'Все' },
  { value: 'ALERT', label: 'Тревога' },
  { value: 'WARNING', label: 'Предупреждение' },
  { value: 'INFO', label: 'Инфо' },
  { value: 'ACTION', label: 'Действие' },
]
</script>
