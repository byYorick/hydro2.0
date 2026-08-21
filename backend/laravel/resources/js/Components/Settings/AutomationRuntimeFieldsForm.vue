<template>
  <div
    class="space-y-3"
    data-testid="automation-runtime-fields-form"
  >
    <div class="flex flex-wrap items-center gap-2">
      <input
        v-model="search"
        type="search"
        class="input-field w-full sm:w-64"
        placeholder="Поиск параметра"
        aria-label="Поиск параметра"
        data-testid="automation-runtime-search"
      />
      <button
        v-if="advancedCount > 0"
        type="button"
        class="text-xs text-[color:var(--text-muted)] hover:text-[color:var(--accent-green)] transition-colors"
        data-testid="automation-runtime-advanced-toggle"
        @click="showAdvanced = !showAdvanced"
      >
        {{ showAdvanced ? 'Скрыть технические параметры' : `Показать технические параметры (${advancedCount})` }}
      </button>
      <span
        v-if="changedCount > 0"
        class="settings-row__changed"
        data-testid="automation-runtime-changed-count"
      >
        изменено: {{ changedCount }}
      </span>
    </div>

    <p
      v-if="visibleSections.length === 0"
      class="text-sm text-[color:var(--text-dim)]"
      data-testid="automation-runtime-empty"
    >
      Ничего не найдено. Измените запрос или покажите технические параметры.
    </p>

    <section
      v-for="section in visibleSections"
      :key="section.key"
      class="settings-group-card"
      :data-testid="`automation-runtime-section-${section.key}`"
    >
      <div class="settings-group-card__toggle cursor-default">
        <h3 class="text-sm font-semibold text-[color:var(--text-primary)]">
          {{ section.title }}
        </h3>
      </div>
      <div class="settings-group-card__body">
        <div class="settings-rows settings-rows--split">
          <SettingsFieldRow
            v-for="item in section.items"
            :key="item.key"
            :label="item.label"
            :description="item.description"
            :unit="item.unit"
            :field-id="fieldInputId(item.key)"
            :changed="item.source === 'override'"
            :stacked="!item.editable"
            :test-id="`settings-automation-field-${item.key}`"
          >
            <template v-if="item.editable">
              <label
                v-if="item.input_type === 'boolean'"
                class="inline-flex items-center gap-2 text-sm text-[color:var(--text-primary)]"
              >
                <input
                  :id="fieldInputId(item.key)"
                  :checked="Boolean(draft[item.key])"
                  type="checkbox"
                  class="accent-[color:var(--accent-green)]"
                  :data-testid="`settings-automation-engine-input-${item.key}`"
                  @change="draft[item.key] = ($event.target as HTMLInputElement).checked"
                />
                <span class="text-xs text-[color:var(--text-muted)]">
                  {{ draft[item.key] ? 'вкл' : 'выкл' }}
                </span>
              </label>
              <select
                v-else-if="item.input_type === 'select'"
                :id="fieldInputId(item.key)"
                v-model="draft[item.key]"
                class="input-select settings-control--select"
                :data-testid="`settings-automation-engine-input-${item.key}`"
              >
                <option
                  v-for="option in item.options || []"
                  :key="`${item.key}-option-${option}`"
                  :value="option"
                >
                  {{ item.option_labels?.[option] ?? option }}
                </option>
              </select>
              <input
                v-else-if="item.input_type === 'number'"
                :id="fieldInputId(item.key)"
                v-model="draft[item.key]"
                class="input-field settings-control--num text-right"
                type="number"
                :step="item.step || 1"
                :min="item.min"
                :max="item.max"
                :data-testid="`settings-automation-engine-input-${item.key}`"
              />
              <input
                v-else
                :id="fieldInputId(item.key)"
                v-model="draft[item.key]"
                class="input-field settings-control--text font-mono"
                type="text"
                :data-testid="`settings-automation-engine-input-${item.key}`"
              />
            </template>
            <template v-else>
              <span class="settings-row__readonly">{{ formatValue(item.value, item.unit) }}</span>
            </template>
          </SettingsFieldRow>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import SettingsFieldRow from '@/Components/Settings/SettingsFieldRow.vue'
import { isSameSettingsDraft, type SettingsDraftValue } from '@/utils/settingsDraft'
import type { AutomationRuntimeSettingItem, AutomationRuntimeSettingSection } from '@/types/SystemSettings'

type DraftValue = SettingsDraftValue

const props = defineProps<{
  sections: AutomationRuntimeSettingSection[]
  modelValue: Record<string, DraftValue>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, DraftValue>]
}>()

const search = ref('')
const showAdvanced = ref(false)
const draft = ref<Record<string, DraftValue>>({ ...props.modelValue })

watch(
  () => props.modelValue,
  (value) => {
    if (!isSameSettingsDraft(draft.value, value)) {
      draft.value = { ...value }
    }
  },
  { deep: true },
)

watch(
  draft,
  (value) => {
    if (!isSameSettingsDraft(value, props.modelValue)) {
      emit('update:modelValue', { ...value })
    }
  },
  { deep: true },
)

const allItems = computed<AutomationRuntimeSettingItem[]>(() =>
  props.sections.flatMap((section) => (Array.isArray(section.items) ? section.items : [])),
)

const advancedCount = computed(() => allItems.value.filter((item) => item.advanced === true).length)
const changedCount = computed(() => allItems.value.filter((item) => item.source === 'override').length)

const visibleSections = computed<AutomationRuntimeSettingSection[]>(() => {
  const query = search.value.trim().toLowerCase()

  return props.sections
    .map((section) => ({
      ...section,
      items: (Array.isArray(section.items) ? section.items : []).filter((item) => matches(item, query)),
    }))
    .filter((section) => section.items.length > 0)
})

function matches(item: AutomationRuntimeSettingItem, query: string): boolean {
  // Поиск игнорирует скрытие технических параметров: иначе найденное поле «пропадает».
  if (query !== '') {
    return [item.label, item.description, item.key].some(
      (candidate) => typeof candidate === 'string' && candidate.toLowerCase().includes(query),
    )
  }

  return showAdvanced.value || item.advanced !== true
}

function fieldInputId(key: string): string {
  return `automation-runtime-${key.replace(/[^a-zA-Z0-9_-]/g, '-')}`
}

function formatValue(value: unknown, unit?: string): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (typeof value === 'boolean') {
    return value ? 'да' : 'нет'
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? value.join(', ') : '—'
  }
  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return unit ? `${String(value)} ${unit}` : String(value)
}
</script>
