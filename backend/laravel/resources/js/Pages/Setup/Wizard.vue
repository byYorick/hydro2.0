<template>
  <AppLayout>
    <div class="space-y-5">
      <section class="ui-hero p-6">
        <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">
          Мастер настройки системы
        </h1>
        <p class="mt-2 text-sm text-[color:var(--text-muted)]">
          Пошаговая настройка теплицы, зоны, культуры и единого профиля автоматики.
        </p>

        <div class="mt-4 h-2 overflow-hidden rounded-full bg-[color:var(--border-muted)]">
          <div
            class="h-full bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] transition-all duration-500"
            :style="{ width: `${progressPercent}%` }"
          ></div>
        </div>

        <div class="mt-3 text-xs text-[color:var(--text-dim)]">
          Прогресс: {{ progressPercent }}% ({{ completedSteps }}/{{ stepItems.length }})
        </div>
      </section>

      <section
        v-if="!canConfigure"
        class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-4 text-sm text-[color:var(--badge-warning-text)]"
      >
        Режим только для просмотра. Полная настройка доступна агроному или администратору.
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4">
        <h2 class="mb-3 text-sm font-semibold text-[color:var(--text-primary)]">
          Сценарий запуска
        </h2>
        <ul class="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
          <li
            v-for="step in stepItems"
            :key="step.id"
            class="rounded-lg border px-3 py-2 text-xs"
            :class="step.done
              ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
              : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--text-muted)]'"
          >
            <div class="font-semibold">{{ step.title }}</div>
            <div class="mt-1">{{ step.hint }}</div>
          </li>
        </ul>

        <div class="mt-4 text-xs text-[color:var(--text-muted)]">
          <span
            v-for="item in launchChecklist"
            :key="item.id"
            class="mr-3 inline-flex items-center"
          >
            <span class="mr-1">{{ item.done ? '✓' : '•' }}</span>{{ item.label }}
          </span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            1. Теплица
          </h3>
          <Badge :variant="stepGreenhouseDone && stepGreenhouseClimateDone ? 'success' : 'neutral'">
            {{ stepGreenhouseDone && stepGreenhouseClimateDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div
          v-if="greenhouseMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedGreenhouseId"
            class="input-select"
            :disabled="!canConfigure || loading.greenhouses"
            @change="selectGreenhouse"
          >
            <option :value="null">Выберите теплицу</option>
            <option
              v-for="greenhouse in availableGreenhouses"
              :key="greenhouse.id"
              :value="greenhouse.id"
            >
              {{ greenhouse.name }} ({{ greenhouse.uid }})
            </option>
          </select>
          <Button
            size="sm"
            variant="secondary"
            data-test="toggle-greenhouse-create"
            :disabled="!canConfigure"
            @click="greenhouseMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-else
          class="grid gap-3 md:grid-cols-3"
        >
          <input
            v-model="greenhouseForm.name"
            type="text"
            placeholder="Название теплицы"
            class="input-field"
            :disabled="!canConfigure"
          />
          <input
            :value="generatedGreenhouseUid"
            type="text"
            class="input-field"
            placeholder="UID (автогенерация)"
            disabled
          />
          <select
            v-model.number="greenhouseForm.greenhouse_type_id"
            class="input-select"
            :disabled="!canConfigure"
          >
            <option :value="null">Выберите тип теплицы</option>
            <option
              v-for="greenhouseType in availableGreenhouseTypes"
              :key="greenhouseType.id"
              :value="greenhouseType.id"
            >
              {{ greenhouseType.name }}
            </option>
          </select>
          <textarea
            v-model="greenhouseForm.description"
            class="input-field md:col-span-2"
            rows="2"
            placeholder="Описание"
            :disabled="!canConfigure"
          ></textarea>
          <div class="flex gap-2">
            <Button
              size="sm"
              :disabled="!canConfigure || !greenhouseForm.name.trim() || loading.stepGreenhouse"
              @click="createGreenhouse"
            >
              {{ loading.stepGreenhouse ? 'Создание...' : 'Создать теплицу' }}
            </Button>
            <Button
              v-if="availableGreenhouses.length > 0"
              size="sm"
              variant="secondary"
              :disabled="loading.stepGreenhouse"
              @click="greenhouseMode = 'select'"
            >
              Отмена
            </Button>
          </div>
        </div>

        <div
          v-if="selectedGreenhouse"
          class="text-sm text-[color:var(--text-muted)]"
        >
          Выбрано:
          <span class="font-semibold text-[color:var(--text-primary)]">
            {{ selectedGreenhouse.name }}
          </span>
        </div>

        <GreenhouseClimateConfiguration
          v-if="selectedGreenhouse"
          :enabled="greenhouseClimateEnabled"
          :climate-form="automationClimateForm"
          :bindings="greenhouseClimateBindings"
          :available-nodes="greenhouseClimateNodes"
          :can-configure="canConfigure"
          :applying="loading.stepGreenhouseClimate"
          :show-apply-button="true"
          apply-label="Сохранить климат теплицы"
          @update:enabled="greenhouseClimateEnabled = $event"
          @apply="applyGreenhouseClimate"
        />

        <div
          v-if="selectedGreenhouse"
          class="text-xs text-[color:var(--text-muted)]"
        >
          <span v-if="greenhouseClimateAppliedAt">Последнее сохранение климата: {{ formatDateTime(greenhouseClimateAppliedAt) }}</span>
          <span v-else>Климат теплицы ещё не сохранён</span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            2. Зона
          </h3>
          <Badge :variant="stepZoneDone ? 'success' : 'neutral'">
            {{ stepZoneDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div
          v-if="zoneMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedZoneId"
            class="input-select"
            :disabled="!canConfigure || loading.zones || !stepGreenhouseDone"
            @change="selectZone"
          >
            <option :value="null">Выберите зону</option>
            <option
              v-for="zone in availableZones"
              :key="zone.id"
              :value="zone.id"
            >
              {{ zone.name }}
            </option>
          </select>
          <Button
            size="sm"
            variant="secondary"
            data-test="toggle-zone-create"
            :disabled="!canConfigure || !stepGreenhouseDone"
            @click="zoneMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-else
          class="grid gap-3 md:grid-cols-4"
        >
          <input
            v-model="zoneForm.name"
            type="text"
            placeholder="Название зоны"
            class="input-field"
            :disabled="!canConfigure || !stepGreenhouseDone"
          />
          <input
            v-model="zoneForm.description"
            type="text"
            placeholder="Описание зоны"
            class="input-field"
            :disabled="!canConfigure || !stepGreenhouseDone"
          />
          <input
            :value="generatedZoneUid"
            type="text"
            class="input-field"
            placeholder="UID (автогенерация)"
            disabled
          />
          <div class="flex gap-2">
            <Button
              size="sm"
              :disabled="!canConfigure || !stepGreenhouseDone || !zoneForm.name.trim() || loading.stepZone"
              @click="createZone"
            >
              {{ loading.stepZone ? 'Создание...' : 'Создать зону' }}
            </Button>
            <Button
              v-if="availableZones.length > 0"
              size="sm"
              variant="secondary"
              :disabled="loading.stepZone"
              @click="zoneMode = 'select'"
            >
              Отмена
            </Button>
          </div>
        </div>

        <div
          v-if="selectedZone"
          class="text-sm text-[color:var(--text-muted)]"
        >
          Выбрано:
          <span class="font-semibold text-[color:var(--text-primary)]">
            {{ selectedZone.name }}
          </span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            3. Культура и рецепт
          </h3>
          <Badge :variant="stepPlantDone && stepRecipeDone ? 'success' : 'neutral'">
            {{ stepPlantDone && stepRecipeDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="grid gap-3 md:grid-cols-[1fr_auto]">
          <select
            v-model.number="selectedPlantId"
            class="input-select"
            :disabled="!canConfigure || loading.plants"
            @change="selectPlant"
          >
            <option :value="null">Выберите растение</option>
            <option
              v-for="plant in availablePlants"
              :key="plant.id"
              :value="plant.id"
            >
              {{ plant.name }}
            </option>
          </select>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canConfigure"
            @click="openPlantCreateWizard"
          >
            Создать
          </Button>
        </div>

        <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
          <div class="mb-1 text-xs text-[color:var(--text-muted)]">
            Рецепт по выбранной культуре
          </div>
          <div
            v-if="loading.stepRecipe"
            class="text-sm text-[color:var(--text-muted)]"
          >
            Подбираем и привязываем рецепт...
          </div>
          <div
            v-else-if="selectedRecipe"
            class="text-sm text-[color:var(--text-primary)]"
          >
            Используется рецепт: <span class="font-semibold">{{ selectedRecipe.name }}</span>
          </div>
          <div
            v-else
            class="text-sm text-[color:var(--badge-warning-text)]"
          >
            Выберите или создайте культуру, чтобы автоматически назначить рецепт.
          </div>
        </div>
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            4. Автоматизация и устройства зоны
          </h3>
          <Badge :variant="stepZoneAutomationDone ? 'success' : 'neutral'">
            {{ stepZoneAutomationDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div
          v-if="!stepZoneDone"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          Сначала создайте или выберите зону на шаге 2.
        </div>

        <template v-else>
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]">
            Климат теплицы вынесен в шаг 1. Здесь настройки сохраняются по секциям, но применяются в общий профиль зоны: устройства, водный контур, полив, коррекция, свет и климат зоны.
          </div>

          <ZoneAutomationProfileSections
            :water-form="automationWaterForm"
            :lighting-form="automationLightingForm"
            :zone-climate-form="zoneClimateForm"
            :can-configure="canConfigure"
            :show-node-bindings="true"
            :show-bind-buttons="true"
            :show-refresh-buttons="true"
            :bind-disabled="loading.stepDevices"
            :binding-in-progress="loading.stepDevices"
            :refresh-disabled="loading.nodes || loading.stepDevices"
            :refreshing-nodes="loading.nodes"
            :available-nodes="availableNodes"
            :assignments="deviceAssignments"
            :show-correction-calibration-stack="Boolean(selectedZone?.id && sensorCalibrationSettings)"
            :zone-id="selectedZone?.id ?? null"
            :sensor-calibration-settings="sensorCalibrationSettings"
            :show-section-save-buttons="true"
            :save-disabled="loading.stepDevices || loading.stepAutomation"
            :saving-section="savingAutomationSection"
            @bind-devices="attachZoneDevicesOnly"
            @refresh-nodes="refreshAvailableNodes"
            @save-section="saveAutomationSection"
          />

          <div
            v-if="!loading.nodes && availableNodes.length === 0"
            class="rounded-lg border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-xs text-[color:var(--badge-warning-text)]"
          >
            Нет доступных узлов. Убедитесь, что устройства зарегистрированы в системе и не привязаны к другим зонам.
          </div>

          <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-muted)]">
            <span>Ожидается нод: {{ zoneAutomationExpectedNodeIds.length }}</span>
            <span v-if="zoneAutomationAssignmentsReady && !zoneAutomationNodesReady" class="text-[color:var(--badge-warning-text)]">
              Привязка нод ещё не подтверждена
            </span>
            <span v-else-if="stepZoneAutomationDone" class="text-[color:var(--badge-success-text)]">
              Профиль зоны и bindings сохранены
            </span>
            <span v-else>
              Сохраните обязательные устройства и хотя бы одну секцию профиля.
            </span>
            <Button
              size="sm"
              variant="secondary"
              :disabled="!canConfigure || loading.nodes"
              @click="refreshAvailableNodes"
            >
              {{ loading.nodes ? 'Обновление...' : 'Обновить ноды' }}
            </Button>
          </div>

          <div class="text-xs text-[color:var(--text-muted)]">
            <span v-if="automationAppliedAt">Последнее применение: {{ formatDateTime(automationAppliedAt) }}</span>
            <span v-else>Профиль зоны ещё не применён</span>
          </div>
        </template>
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            5. Запуск
          </h3>
          <Badge :variant="canLaunch ? 'success' : 'warning'">
            {{ canLaunch ? 'Можно запускать' : 'Есть незавершённые шаги' }}
          </Badge>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :disabled="!canLaunch || loading.stepLaunch"
            @click="openCycleWizard"
          >
            {{ loading.stepLaunch ? 'Открытие...' : 'Открыть мастер запуска цикла' }}
          </Button>

          <Link
            v-if="selectedZone"
            :href="`/zones/${selectedZone.id}`"
            class="text-xs text-[color:var(--accent-cyan)]"
          >
            Перейти к зоне
          </Link>
        </div>

        <div class="text-xs text-[color:var(--text-muted)]">
          Топология воды: {{ waterTopologyLabel }}
        </div>

        <div
          v-if="selectedZoneHasActiveCycle && launchBlockedReason"
          class="text-xs text-[color:var(--badge-warning-text)]"
        >
          {{ launchBlockedReason }}
        </div>
      </section>
    </div>

    <PlantCreateModal
      :show="showPlantCreateWizard"
      @close="handlePlantCreateClose"
      @created="handlePlantCreated"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import GreenhouseClimateConfiguration from '@/Components/GreenhouseClimateConfiguration.vue'
import PlantCreateModal from '@/Components/PlantCreateModal.vue'
import ZoneAutomationProfileSections from '@/Components/ZoneAutomationProfileSections.vue'
import { useSetupWizard } from '@/composables/useSetupWizard'
import type { SensorCalibrationSettings } from '@/types/SystemSettings'
import type { ZoneAutomationSectionSaveKey } from '@/Components/ZoneAutomationProfileSections.vue'

const page = usePage<{ sensorCalibrationSettings?: SensorCalibrationSettings | null }>()

const {
  canConfigure,
  loading,
  greenhouseMode,
  zoneMode,
  plantMode,
  availableGreenhouses,
  availableGreenhouseTypes,
  availableZones,
  availablePlants,
  availableNodes,
  greenhouseClimateNodes,
  selectedGreenhouseId,
  selectedZoneId,
  selectedPlantId,
  selectedGreenhouse,
  selectedZone,
  selectedRecipe,
  greenhouseForm,
  zoneForm,
  greenhouseClimateEnabled,
  greenhouseClimateBindings,
  greenhouseClimateAppliedAt,
  automationClimateForm,
  automationWaterForm,
  automationLightingForm,
  zoneClimateForm,
  deviceAssignments,
  automationAppliedAt,
  stepGreenhouseDone,
  stepGreenhouseClimateDone,
  stepZoneDone,
  stepPlantDone,
  stepRecipeDone,
  stepZoneAutomationDone,
  zoneAutomationAssignmentsReady,
  zoneAutomationNodesReady,
  zoneAutomationExpectedNodeIds,
  selectedZoneHasActiveCycle,
  launchBlockedReason,
  completedSteps,
  progressPercent,
  canLaunch,
  launchChecklist,
  stepItems,
  waterTopologyLabel,
  generatedGreenhouseUid,
  generatedZoneUid,
  attachZoneDevicesOnly,
  createGreenhouse,
  selectGreenhouse,
  createZone,
  selectZone,
  selectPlant,
  refreshAvailableNodes,
  applyGreenhouseClimate,
  saveZoneAutomationAndDevices,
  applyAutomation,
  openCycleWizard,
  formatDateTime,
} = useSetupWizard()

const showPlantCreateWizard = ref(false)
const sensorCalibrationSettings = computed(() => page.props.sensorCalibrationSettings ?? null)
const savingAutomationSection = ref<ZoneAutomationSectionSaveKey | null>(null)

async function saveAutomationSection(section: ZoneAutomationSectionSaveKey): Promise<void> {
  if (!canConfigure.value || !selectedZone.value?.id) {
    return
  }

  savingAutomationSection.value = section
  try {
    if (section === 'required_devices') {
      await attachZoneDevicesOnly(['irrigation', 'ph_correction', 'ec_correction'])
      return
    }

    if (section === 'lighting') {
      await saveZoneAutomationAndDevices()
      return
    }

    if (section === 'zone_climate') {
      await saveZoneAutomationAndDevices()
      return
    }

    await applyAutomation()
  } finally {
    savingAutomationSection.value = null
  }
}

function handlePlantCreated(plant: { id?: number; name?: string } | null): void {
  showPlantCreateWizard.value = false

  if (!plant?.id) {
    plantMode.value = 'select'
    return
  }

  const exists = availablePlants.value.some((item) => item.id === plant.id)
  if (!exists) {
    availablePlants.value = [
      ...availablePlants.value,
      { id: plant.id, name: plant.name ?? `Plant #${plant.id}` },
    ]
  }

  selectedPlantId.value = plant.id
  plantMode.value = 'select'
  selectPlant()
}

function openPlantCreateWizard(): void {
  if (!canConfigure.value) {
    return
  }

  plantMode.value = 'create'
  showPlantCreateWizard.value = true
}

function handlePlantCreateClose(): void {
  showPlantCreateWizard.value = false
  plantMode.value = 'select'
}
</script>
