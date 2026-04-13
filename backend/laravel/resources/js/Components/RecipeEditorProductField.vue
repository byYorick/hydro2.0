<template>
  <div class="rounded-lg border border-[color:var(--border-muted)] p-2.5 flex flex-col gap-1.5">
    <div class="product-field__header">
      <div class="text-sm font-bold text-[color:var(--text-primary)]">{{ label }}</div>
      <div class="text-[12px] text-[color:var(--text-muted)] leading-snug product-field__desc">{{ description || ' ' }}</div>
    </div>

    <div class="flex gap-1">
      <select
        :value="productId ?? ''"
        class="input-field flex-1 min-w-0"
        @input="onProductInput($event)"
      >
        <option value="">Продукт</option>
        <option v-for="product in products" :key="product.id" :value="product.id">
          {{ product.manufacturer }} · {{ product.name }}
        </option>
      </select>
      <button
        type="button"
        class="pill-btn"
        title="Создать новый продукт"
        @click="modalOpen = true"
      >
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
      </button>
    </div>

    <div>
      <input
        :value="ratio"
        type="number"
        step="0.01"
        class="input-field"
        placeholder="—"
        @input="onRatioInput($event)"
      />
      <div class="text-[11px] text-[color:var(--text-muted)] mt-0.5">Доля от EC, %</div>
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
      <div class="text-[11px] text-[color:var(--text-muted)] mt-0.5">Доза, мл/л</div>
    </div>

    <NutrientProductCreateModal
      :open="modalOpen"
      :component="component"
      @close="modalOpen = false"
      @created="onCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { NutrientProduct } from '@/types'
import NutrientProductCreateModal from '@/Components/NutrientProductCreateModal.vue'

withDefaults(defineProps<{
  label: string
  description?: string
  component: NutrientProduct['component']
  products: NutrientProduct[]
}>(), {
  description: '',
})

const productId = defineModel<number | null>('productId')
const ratio = defineModel<number | null>('ratio')
const dose = defineModel<number | null>('dose')

const emit = defineEmits<{
  'product-created': [product: NutrientProduct]
}>()

const modalOpen = ref(false)

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

function onCreated(product: NutrientProduct): void {
  emit('product-created', product)
  productId.value = product.id
  modalOpen.value = false
}
</script>

<style scoped>
/* Шапка карточки: title + description жёстко фиксированы по высоте */
.product-field__header {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  height: 3.2rem;
  flex-shrink: 0;
}
.product-field__desc {
  height: 2rem;
  line-height: 1rem;
  font-size: 0.72rem;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  color: var(--text-muted);
}

.pill-btn {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.6rem;
  height: 2.6rem;
  border-radius: 0.85rem;
  background: color-mix(in srgb, var(--accent-green) 12%, transparent);
  color: var(--accent-green);
  border: 1px solid color-mix(in srgb, var(--accent-green) 25%, transparent);
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, transform 0.08s;
}
.pill-btn:hover {
  background: color-mix(in srgb, var(--accent-green) 20%, transparent);
  border-color: color-mix(in srgb, var(--accent-green) 45%, transparent);
}
.pill-btn:active {
  transform: scale(0.94);
}
</style>
