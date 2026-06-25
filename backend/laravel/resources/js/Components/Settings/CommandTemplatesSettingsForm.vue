<template>
  <div
    class="space-y-4"
    data-testid="command-templates-settings-form"
  >
    <section
      v-for="field in fields"
      :key="field.path"
      class="settings-card"
    >
      <header class="settings-card__header">
        <div class="flex items-start gap-2">
          <h3 class="settings-card__title">
            {{ templateLabel(field) }}
          </h3>
          <SettingsFieldHelp
            :title="templateLabel(field)"
            :summary="field.description"
            :help="field.help"
            :test-id="`command-template-help-${field.path}`"
          />
        </div>
        <p
          v-if="field.description"
          class="settings-card__description"
        >
          {{ field.description }}
        </p>
      </header>

      <div class="settings-card__body space-y-2">
        <div
          v-if="!stepsFor(field.path).length"
          class="text-xs text-[color:var(--text-dim)] py-2"
        >
          Нет шагов. Добавьте relay-команду.
        </div>

        <div
          v-for="(step, index) in stepsFor(field.path)"
          :key="`${field.path}-${index}`"
          class="settings-field-card !p-3 md:grid md:grid-cols-[auto_1fr_auto_auto] md:gap-2 md:!transform-none"
          :data-testid="`command-template-step-${field.path}-${index}`"
        >
          <div class="flex items-center text-xs font-medium text-[color:var(--text-muted)] pt-2 md:pt-0 md:items-center md:h-full">
            #{{ index + 1 }}
          </div>

          <div class="space-y-1">
            <div class="flex items-center gap-1">
              <label
                class="block text-[10px] uppercase tracking-wide text-[color:var(--text-dim)]"
                :for="stepInputId(field.path, index, 'channel')"
              >
                Канал
              </label>
              <SettingsFieldHelp
                title="Канал relay-команды"
                summary="Имя ACTUATOR-канала на узле полива."
                help="Укажите channel из NodeConfig узла irrig/pump (например `pump_main`, `valve_irrigation`). Команда `set_relay` будет отправлена именно на этот канал. Имя должно совпадать с конфигурацией оборудования, иначе узел вернёт INVALID или NO_EFFECT."
                :test-id="`command-template-channel-help-${field.path}-${index}`"
              />
            </div>
            <input
              :id="stepInputId(field.path, index, 'channel')"
              v-model="step.channel"
              type="text"
              class="input-field w-full font-mono text-sm"
              placeholder="valve_irrigation"
              :data-testid="`command-template-channel-${field.path}-${index}`"
            />
          </div>

          <div class="space-y-1">
            <div class="flex items-center gap-1">
              <label
                class="block text-[10px] uppercase tracking-wide text-[color:var(--text-dim)]"
                :for="stepInputId(field.path, index, 'state')"
              >
                Состояние
              </label>
              <SettingsFieldHelp
                title="Состояние реле"
                summary="Вкл/выкл для команды set_relay."
                help="ON — реле замыкается (насос/клапан включается). OFF — реле размыкается. При остановке процесса обычно сначала выключают насос, затем клапаны — соблюдайте безопасный порядок шагов в шаблоне."
                :test-id="`command-template-state-help-${field.path}-${index}`"
              />
            </div>
            <select
              :id="stepInputId(field.path, index, 'state')"
              :value="step.params.state ? 'true' : 'false'"
              class="input-select w-full"
              :data-testid="`command-template-state-${field.path}-${index}`"
              @change="step.params.state = ($event.target as HTMLSelectElement).value === 'true'"
            >
              <option value="true">
                Включить (ON)
              </option>
              <option value="false">
                Выключить (OFF)
              </option>
            </select>
          </div>

          <div class="flex items-end gap-1">
            <Button
              size="sm"
              variant="secondary"
              type="button"
              :disabled="index === 0"
              :data-testid="`command-template-up-${field.path}-${index}`"
              @click="moveStep(field.path, index, -1)"
            >
              ↑
            </Button>
            <Button
              size="sm"
              variant="secondary"
              type="button"
              :disabled="index >= stepsFor(field.path).length - 1"
              :data-testid="`command-template-down-${field.path}-${index}`"
              @click="moveStep(field.path, index, 1)"
            >
              ↓
            </Button>
            <Button
              size="sm"
              variant="danger"
              type="button"
              :data-testid="`command-template-remove-${field.path}-${index}`"
              @click="removeStep(field.path, index)"
            >
              ✕
            </Button>
          </div>
        </div>

        <Button
          size="sm"
          variant="secondary"
          type="button"
          :data-testid="`command-template-add-${field.path}`"
          @click="addStep(field.path)"
        >
          Добавить шаг
        </Button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import Button from '@/Components/Button.vue'
import SettingsFieldHelp from '@/Components/Settings/SettingsFieldHelp.vue'
import type { AutomationCommandTemplateStep, SystemSettingsField } from '@/types/SystemSettings'

const TEMPLATE_LABELS: Record<string, string> = {
  irrigation_start: 'Полив — запуск',
  irrigation_stop: 'Полив — остановка',
  clean_fill_start: 'Заполнение чистого бака — запуск',
  clean_fill_stop: 'Заполнение чистого бака — остановка',
  solution_fill_start: 'Заполнение раствора — запуск',
  solution_fill_stop: 'Заполнение раствора — остановка',
  prepare_recirculation_start: 'Подготовка рециркуляции — запуск',
  prepare_recirculation_stop: 'Подготовка рециркуляции — остановка',
  irrigation_recovery_start: 'Восстановление полива — запуск',
  irrigation_recovery_stop: 'Восстановление полива — остановка',
}

const props = defineProps<{
  fields: SystemSettingsField[]
  modelValue: Record<string, AutomationCommandTemplateStep[]>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, AutomationCommandTemplateStep[]>]
}>()

const draft = ref<Record<string, AutomationCommandTemplateStep[]>>(cloneDraft(props.modelValue))

watch(
  () => props.modelValue,
  (value) => {
    draft.value = cloneDraft(value)
  },
  { deep: true },
)

watch(
  draft,
  (value) => {
    const cloned = cloneDraft(value)
    if (JSON.stringify(cloned) === JSON.stringify(props.modelValue)) {
      return
    }
    emit('update:modelValue', cloned)
  },
  { deep: true },
)

function cloneDraft(value: Record<string, AutomationCommandTemplateStep[]>): Record<string, AutomationCommandTemplateStep[]> {
  return Object.fromEntries(
    Object.entries(value).map(([key, steps]) => [
      key,
      steps.map((step) => ({
        channel: step.channel,
        cmd: 'set_relay' as const,
        params: { state: Boolean(step.params.state) },
      })),
    ]),
  )
}

function stepsFor(path: string): AutomationCommandTemplateStep[] {
  return draft.value[path] ?? []
}

function templateLabel(field: SystemSettingsField): string {
  return TEMPLATE_LABELS[field.path] ?? field.label
}

function stepInputId(path: string, index: number, part: string): string {
  return `command-template-${path}-${index}-${part}`
}

function addStep(path: string): void {
  const steps = [...stepsFor(path)]
  steps.push({
    channel: '',
    cmd: 'set_relay',
    params: { state: true },
  })
  draft.value = { ...draft.value, [path]: steps }
}

function removeStep(path: string, index: number): void {
  const steps = [...stepsFor(path)]
  steps.splice(index, 1)
  draft.value = { ...draft.value, [path]: steps }
}

function moveStep(path: string, index: number, direction: -1 | 1): void {
  const steps = [...stepsFor(path)]
  const target = index + direction
  if (target < 0 || target >= steps.length) {
    return
  }
  const [item] = steps.splice(index, 1)
  steps.splice(target, 0, item)
  draft.value = { ...draft.value, [path]: steps }
}
</script>
