<template>
  <Card>
    <div class="space-y-4">
      <div>
        <h3 class="text-sm font-semibold mb-2">Схема оборудования зоны</h3>
        <p class="text-xs text-[color:var(--text-muted)] mb-4">
          Укажите, какое оборудование установлено в зоне. Обязательное оборудование отмечено красным.
        </p>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div
          v-for="asset in assetTypes"
          :key="asset.type"
          class="p-3 rounded border cursor-pointer transition"
          :class="
            isSelected(asset.type)
              ? asset.required
                ? 'border-[color:var(--accent-green)] bg-[color:var(--badge-success-bg)]'
                : 'border-[color:var(--accent-cyan)] bg-[color:var(--badge-info-bg)]'
              : asset.required
              ? 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]'
              : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface)] hover:border-[color:var(--border-strong)]'
          "
          @click="toggleAsset(asset.type)"
        >
          <div class="flex items-center justify-between">
            <div class="flex-1">
              <div class="text-sm font-medium">{{ asset.icon }} {{ asset.label }}</div>
              <div v-if="asset.required" class="text-xs text-[color:var(--accent-red)] mt-1">Обязательно</div>
            </div>
            <div
              v-if="isSelected(asset.type)"
              class="text-[color:var(--accent-cyan)] text-lg"
            >
              ✓
            </div>
          </div>
        </div>
      </div>

      <div v-if="selectedAssets.length > 0" class="mt-4 p-3 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-surface)]">
        <div class="text-xs text-[color:var(--text-muted)] mb-2">Выбранное оборудование:</div>
        <div class="flex flex-wrap gap-2">
          <Badge
            v-for="assetType in selectedAssets"
            :key="assetType"
            variant="info"
            size="sm"
          >
            {{ getAssetLabel(assetType) }}
          </Badge>
        </div>
      </div>

      <div v-if="missingRequired.length > 0" class="mt-4 p-3 rounded border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]">
        <div class="text-xs text-[color:var(--badge-danger-text)] mb-2">Отсутствует обязательное оборудование:</div>
        <div class="flex flex-wrap gap-2">
          <Badge
            v-for="assetType in missingRequired"
            :key="assetType"
            variant="danger"
            size="sm"
          >
            {{ getAssetLabel(assetType) }}
          </Badge>
        </div>
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'

interface AssetType {
  type: string
  label: string
  icon: string
  required: boolean
}

const assetTypes: AssetType[] = [
  { type: 'PUMP', label: 'Помпа', icon: '💧', required: true },
  { type: 'TANK_CLEAN', label: 'Бак чистой воды', icon: '🪣', required: true },
  { type: 'TANK_NUTRIENT', label: 'Бак раствора', icon: '🧪', required: true },
  { type: 'DRAIN', label: 'Дренаж', icon: '🚰', required: true },
  { type: 'LIGHT', label: 'Свет', icon: '💡', required: false },
  { type: 'VENT', label: 'Вентиляция', icon: '🌬️', required: false },
  { type: 'HEATER', label: 'Отопление', icon: '🔥', required: false },
  { type: 'MISTER', label: 'Туман', icon: '🌫️', required: false },
]

interface Props {
  modelValue?: string[]
  zoneId?: number
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  zoneId: undefined,
})

const emit = defineEmits<{
  'update:modelValue': [value: string[]]
}>()

const selectedAssets = ref<string[]>(props.modelValue || [])

watch(() => props.modelValue, (newValue) => {
  selectedAssets.value = newValue || []
}, { immediate: true })

const missingRequired = computed(() => {
  const required = assetTypes.filter(a => a.required).map(a => a.type)
  return required.filter(type => !selectedAssets.value.includes(type))
})

function isSelected(assetType: string): boolean {
  return selectedAssets.value.includes(assetType)
}

function toggleAsset(assetType: string) {
  if (selectedAssets.value.includes(assetType)) {
    selectedAssets.value = selectedAssets.value.filter(t => t !== assetType)
  } else {
    selectedAssets.value = [...selectedAssets.value, assetType]
  }
  emit('update:modelValue', selectedAssets.value)
}

function getAssetLabel(assetType: string): string {
  return assetTypes.find(a => a.type === assetType)?.label || assetType
}

defineExpose({
  getSelectedAssets: () => selectedAssets.value,
  getMissingRequired: () => missingRequired.value,
})
</script>
