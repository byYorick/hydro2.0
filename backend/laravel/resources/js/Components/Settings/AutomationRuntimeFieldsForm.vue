<template>
  <div
    class="space-y-3"
    data-testid="automation-runtime-fields-form"
  >
    <div class="flex flex-wrap items-center gap-2">
      <TextField
        v-model="search"
        type="search"
        class="w-full sm:w-64"
        placeholder="Поиск параметра"
        aria-label="Поиск параметра"
        data-testid="automation-runtime-search"
      />
      <button
        v-if="advancedCount > 0"
        type="button"
        class="text-xs text-[color:var(--text-muted)] hover:text-[color:var(--status-ok)] transition-colors"
        data-testid="automation-runtime-advanced-toggle"
        @click="showAdvanced = !showAdvanced"
      >
        {{ showAdvanced ? 'Скрыть технические параметры' : `Показать технические параметры (${advancedCount})` }}
      </button>
      <span
        class="text-xs text-[color:var(--text-muted)]"
        data-testid="automation-runtime-overrides-count"
      >Сохранённых настроек: {{ overrideCount }}</span>
    </div>

    <Tabs
      v-model="selectedSection"
      :tabs="sectionTabs"
      list-role="group"
      aria-label="Группы параметров AE3"
    />
    <div
      class="flex flex-wrap items-center gap-2"
      role="group"
      aria-label="Фильтр параметров"
    >
      <Button
        v-for="filter in filters"
        :key="filter.id"
        size="sm"
        :variant="filterMode === filter.id ? 'secondary' : 'ghost'"
        :aria-pressed="filterMode === filter.id"
        :data-testid="`automation-runtime-filter-${filter.id}`"
        @click="filterMode = filter.id"
      >
        {{ filter.label }}
      </Button>
      <span
        v-if="changedCount"
        class="settings-row__changed"
        data-testid="automation-runtime-changed-count"
        role="status"
      >Не сохранено: {{ changedCount }}</span>
    </div>

    <p
      v-if="visibleSections.length === 0"
      class="text-sm text-[color:var(--text-dim)]"
      data-testid="automation-runtime-empty"
    >
      Ничего не найдено. Измените поиск, группу или фильтр параметров.
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
            :changed="isDirty(item)"
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
                  :disabled="disabled"
                  type="checkbox"
                  class="accent-[color:var(--status-ok)]"
                  :data-testid="`settings-automation-engine-input-${item.key}`"
                  @change="draft[item.key] = ($event.target as HTMLInputElement).checked"
                />
                <span class="text-xs text-[color:var(--text-muted)]">
                  {{ draft[item.key] ? 'вкл' : 'выкл' }}
                </span>
              </label>
              <SelectField
                v-else-if="item.input_type === 'select'"
                :id="fieldInputId(item.key)"
                v-model="draft[item.key]"
                :disabled="disabled"
                :data-testid="`settings-automation-engine-input-${item.key}`"
                input-class="settings-control--select"
              >
                <option
                  v-for="option in item.options || []"
                  :key="`${item.key}-option-${option}`"
                  :value="option"
                >
                  {{ item.option_labels?.[option] ?? option }}
                </option>
              </SelectField>
              <TextField
                v-else-if="item.input_type === 'number'"
                :id="fieldInputId(item.key)"
                v-model="draft[item.key]"
                type="number"
                :disabled="disabled"
                :error="errors[item.key]"
                :step="item.step || 1"
                :min="item.min"
                :max="item.max"
                :data-testid="`settings-automation-engine-input-${item.key}`"
                input-class="settings-control--num text-right"
              />
              <TextField
                v-else
                :id="fieldInputId(item.key)"
                v-model="draft[item.key]"
                type="text"
                :disabled="disabled"
                :error="errors[item.key]"
                :data-testid="`settings-automation-engine-input-${item.key}`"
                input-class="settings-control--text font-mono"
              />
              <button
                v-if="isDirty(item)"
                type="button"
                class="mt-1 text-xs text-[color:var(--status-info)]"
                :disabled="disabled"
                :aria-label="`Отменить изменение: ${item.label}`"
                @click="draft[item.key] = item.value as DraftValue"
              >
                Отменить
              </button>
              <span
                v-else-if="item.source === 'override'"
                class="block text-xs text-[color:var(--text-muted)]"
              >Сохранённая настройка</span>
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
import SelectField from '@/Components/SelectField.vue'

import TextField from '@/Components/TextField.vue'

import { computed, ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import Tabs from '@/Components/Tabs.vue'
import SettingsFieldRow from '@/Components/Settings/SettingsFieldRow.vue'
import { isRuntimeFieldDirty } from '@/utils/automationRuntimeDraft'
import { isSameSettingsDraft, type SettingsDraftValue } from '@/utils/settingsDraft'
import type { AutomationRuntimeSettingItem, AutomationRuntimeSettingSection } from '@/types/SystemSettings'

type DraftValue = SettingsDraftValue

const props = withDefaults(defineProps<{
  sections: AutomationRuntimeSettingSection[]
  modelValue: Record<string, DraftValue>
  errors?: Record<string, string>
  disabled?: boolean
}>(), { errors: () => ({}), disabled: false })

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, DraftValue>]
}>()

const search = ref('')
const showAdvanced = ref(false)
const selectedSection = ref('all')
const filterMode = ref<'all' | 'changed' | 'overrides'>('all')
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
const overrideCount = computed(() => allItems.value.filter(item => item.source === 'override').length)
const changedCount = computed(() => allItems.value.filter(isDirty).length)
const filters = computed(() => [
  { id: 'all' as const, label: 'Все параметры' },
  { id: 'changed' as const, label: `Несохранённые (${changedCount.value})` },
  { id: 'overrides' as const, label: `Сохранённые (${overrideCount.value})` },
])
const sectionTabs = computed(() => [{ id: 'all', label: 'Все группы' }, ...props.sections.map(section => ({ id: section.key, label: section.title }))])

function isDirty(item: AutomationRuntimeSettingItem): boolean {
  return item.editable && isRuntimeFieldDirty(item, draft.value[item.key])
}

const visibleSections = computed<AutomationRuntimeSettingSection[]>(() => {
  const query = search.value.trim().toLowerCase()

  return props.sections
    .filter(section => query !== '' || selectedSection.value === 'all' || selectedSection.value === section.key)
    .map((section) => ({
      ...section,
      items: (Array.isArray(section.items) ? section.items : []).filter((item) => matches(item, query)),
    }))
    .filter((section) => section.items.length > 0)
})

function matches(item: AutomationRuntimeSettingItem, query: string): boolean {
  if (filterMode.value === 'changed' && !isDirty(item)) return false
  if (filterMode.value === 'overrides' && item.source !== 'override') return false
  // Поиск игнорирует скрытие технических параметров: иначе найденное поле «пропадает».
  if (query !== '') {
    return [item.label, item.description, item.key].some(
      (candidate) => typeof candidate === 'string' && candidate.toLowerCase().includes(query),
    )
  }

  return filterMode.value !== 'all' || showAdvanced.value || item.advanced !== true
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
