<template>
  <div class="rounded-lg border border-[color:var(--border-muted)] p-2.5 space-y-1.5">
    <div>
      <div class="text-xs font-semibold text-[color:var(--text-primary)]">{{ label }}</div>
      <div v-if="description" class="text-[10px] text-[color:var(--text-muted)] leading-snug">{{ description }}</div>
    </div>
    <select
      :value="productId ?? ''"
      class="input-field"
      @input="onProductInput($event)"
    >
      <option value="">
        Продукт
      </option>
      <option
        v-for="product in products"
        :key="product.id"
        :value="product.id"
      >
        {{ product.manufacturer }} · {{ product.name }}
      </option>
    </select>
    <div>
      <input
        :value="ratio"
        type="number"
        step="0.01"
        class="input-field"
        placeholder="—"
        @input="onRatioInput($event)"
      />
      <div class="text-[9px] text-[color:var(--text-dim)] mt-0.5">Доля от EC, %</div>
    </div>
    <div>
      <input
        :value="dose"
        type="number"
        step="0.01"
        class="input-field"
        placeholder="—"
        @input="onDoseInput($event)"
      />
      <div class="text-[9px] text-[color:var(--text-dim)] mt-0.5">Доза, мл/л</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { NutrientProduct } from '@/types'

withDefaults(defineProps<{
  label: string
  description?: string
  products: NutrientProduct[]
}>(), {
  description: '',
})

const productId = defineModel<number | null>('productId')
const ratio = defineModel<number | null>('ratio')
const dose = defineModel<number | null>('dose')

function onProductInput(event: Event): void {
  const target = event.target as HTMLSelectElement
  productId.value = Number(target.value) || null
}

function onRatioInput(event: Event): void {
  const target = event.target as HTMLInputElement
  ratio.value = Number(target.value) || null
}

function onDoseInput(event: Event): void {
  const target = event.target as HTMLInputElement
  dose.value = Number(target.value) || null
}
</script>
