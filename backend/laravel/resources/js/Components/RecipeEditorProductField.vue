<template>
  <div class="rounded-lg border border-[color:var(--border-muted)] p-3 space-y-2">
    <div class="text-xs font-semibold text-[color:var(--text-primary)]">
      {{ label }}
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
    <input
      :value="ratio"
      type="number"
      step="0.01"
      class="input-field"
      placeholder="Ratio %"
      @input="onRatioInput($event)"
    />
    <input
      :value="dose"
      type="number"
      step="0.01"
      class="input-field"
      placeholder="Доза мл/л"
      @input="onDoseInput($event)"
    />
  </div>
</template>

<script setup lang="ts">
import type { NutrientProduct } from '@/types'

defineProps<{
  label: string
  products: NutrientProduct[]
}>()

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
