<template>
  <AppLayout>
    <div class="space-y-5">
      <section class="ui-hero p-6">
        <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">
          Мастер настройки системы
        </h1>
        <p class="mt-2 text-sm text-[color:var(--text-muted)]">
          Пошаговая настройка теплицы, зоны, культуры, автоматики зоны и калибровки.
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
        <ul class="grid gap-2 md:grid-cols-2 xl:grid-cols-7">
          <li
            v-for="step in stepItems"
            :key="step.id"
            class="rounded-lg border px-3 py-2 text-xs"
            :class="step.done
              ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)] text-[color:var(--badge-success-text)]'
              : 'border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] text-[color:var(--text-muted)]'"
          >
            <div class="font-semibold">
              {{ step.title }}
            </div>
            <div class="mt-1">
              {{ step.hint }}
            </div>
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
            data-testid="setup-wizard-greenhouse-select"
            class="input-select"
            :disabled="!canConfigure || loading.greenhouses"
            @change="selectGreenhouse"
          >
            <option :value="null">
              Выберите теплицу
            </option>
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
            <option :value="null">
              Выберите тип теплицы
            </option>
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
          v-model:enabled="greenhouseClimateEnabled"
          v-model:climate-form="automationClimateForm"
          v-model:bindings="greenhouseClimateBindings"
          :available-nodes="greenhouseClimateNodes"
          :can-configure="canConfigure"
          :applying="loading.stepGreenhouseClimate"
          :show-apply-button="true"
          apply-label="Сохранить климат теплицы"
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
            data-testid="setup-wizard-zone-select"
            class="input-select"
            :disabled="!canConfigure || loading.zones || !stepGreenhouseDone"
            @change="selectZone"
          >
            <option :value="null">
              Выберите зону
            </option>
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
            data-testid="setup-wizard-plant-select"
            class="input-select"
            :disabled="!canConfigure || loading.plants"
            @change="selectPlant"
          >
            <option :value="null">
              Выберите растение
            </option>
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
            4. Автоматика зоны
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
            Автоматика зоны собрана в три блока. `Водный контур` включает обязательные ноды и water runtime, `Климат зоны` и `Освещение` включаются switch-ом и раскрывают привязку нод вместе с логикой подсистемы.
          </div>

          <ZoneAutomationProfileSections
            v-model:water-form="automationWaterForm"
            v-model:lighting-form="automationLightingForm"
            v-model:zone-climate-form="zoneClimateForm"
            v-model:assignments="deviceAssignments"
            :layout-mode="'zone_blocks'"
            :can-configure="canConfigure"
            :show-node-bindings="true"
            :show-bind-buttons="true"
            :show-refresh-buttons="true"
            :bind-disabled="loading.stepDevices"
            :binding-in-progress="loading.stepDevices"
            :refresh-disabled="loading.nodes || loading.stepDevices"
            :refreshing-nodes="loading.nodes"
            :available-nodes="availableNodes"
            :show-section-save-buttons="true"
            :save-disabled="loading.stepDevices || loading.stepAutomation"
            :saving-section="savingAutomationSection"
            :show-required-devices-section="false"
            @bind-devices="attachZoneDevicesOnly"
            @refresh-nodes="refreshAvailableNodes"
            @save-section="saveZoneAutomationBlock"
          />

          <div
            v-if="!loading.nodes && availableNodes.length === 0"
            class="rounded-lg border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-xs text-[color:var(--badge-warning-text)]"
          >
            Нет доступных узлов. Убедитесь, что устройства зарегистрированы в системе и не привязаны к другим зонам.
          </div>

          <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-muted)]">
            <span>Ожидается нод: {{ zoneAutomationExpectedNodeIds.length }}</span>
            <span
              v-if="zoneAutomationAssignmentsReady && !zoneAutomationNodesReady"
              class="text-[color:var(--badge-warning-text)]"
            >
              Привязка нод ещё не подтверждена
            </span>
            <span
              v-else-if="stepZoneDevicesDone"
              class="text-[color:var(--badge-success-text)]"
            >
              Привязка нод подтверждена
            </span>
            <span v-else>
              Сохраните `Водный контур`, затем при необходимости сохраните блоки климата зоны и освещения.
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
            <span v-if="automationAppliedAt">Последнее применение профиля: {{ formatDateTime(automationAppliedAt) }}</span>
            <span v-else>Профиль автоматики зоны ещё не применён</span>
          </div>
        </template>
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            5. Калибровка
          </h3>
          <Badge :variant="stepZoneCalibrationReady ? 'success' : 'neutral'">
            {{ stepZoneCalibrationReady ? 'Доступно' : 'Ожидает автоматику' }}
          </Badge>
        </div>

        <div
          v-if="!stepZoneDone"
          class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]"
        >
          Сначала создайте или выберите зону на шаге 2.
        </div>

        <template v-else-if="!stepZoneAutomationDone">
          <div class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-xs text-[color:var(--badge-warning-text)]">
            Сначала сохраните автоматику зоны на шаге 4. После этого шаг 5 проходится последовательно: sensor calibration, pump calibration и process calibration. Финальная readiness-проверка и запуск объединены в шаге 6.
          </div>
        </template>

        <template v-else-if="selectedZone?.id">
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]">
            Отдельный рабочий шаг для последовательной настройки calibration-контура зоны: сенсоры, дозирование и process calibration. Runtime bounds насосов и PID/autotune доступны только в расширенных настройках, а финальная readiness вынесена в шаг запуска.
          </div>

          <ZoneCorrectionCalibrationStack
            :zone-id="selectedZone.id"
            :sensor-calibration-settings="sensorCalibrationSettings"
            :phase-targets="selectedRecipePhaseTargets"
            :show-runtime-readiness="false"
            :save-success-seq="pumpCalibrationSaveSeq"
            :run-success-seq="pumpCalibrationRunSeq"
            @open-pump-calibration="openPumpCalibrationModal"
            @pid-config-saved="handleZonePidConfigSaved"
            @authority-updated="handleZoneCorrectionCalibrationUpdated"
          />
        </template>
      </section>

      <section class="surface-card surface-card--elevated rounded-2xl border border-[color:var(--border-muted)] p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            6. Проверка и запуск
          </h3>
          <Badge :variant="canLaunch ? 'success' : 'warning'">
            {{ canLaunch ? 'Можно запускать' : 'Есть незавершённые шаги' }}
          </Badge>
        </div>

        <template v-if="!stepZoneDone">
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]">
            Сначала создайте или выберите зону на шаге 2.
          </div>
        </template>

        <template v-else-if="selectedZone?.id">
          <div class="rounded-xl border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)]">
            Финальный шаг: сначала проверьте correction runtime readiness, затем запускайте цикл. Если есть блокеры, используйте ссылки карточки, чтобы вернуться к нужной настройке.
          </div>

          <CorrectionRuntimeReadinessCard
            :zone-id="selectedZone.id"
            :refresh-token="wizardReadinessRefreshToken"
            @focus-process-calibration="focusProcessCalibration"
            @open-pump-calibration="openPumpCalibrationModal"
            @focus-pid-config="focusPidConfig"
          />
        </template>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            data-testid="setup-wizard-open-cycle"
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
          v-if="selectedZone && !zoneLaunchReady && zoneLaunchReadinessErrors.length > 0"
          class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-3 text-xs text-[color:var(--badge-warning-text)]"
        >
          <div class="font-medium">
            До запуска нужно закрыть обязательные пункты:
          </div>
          <ul class="mt-2 list-disc list-inside space-y-1">
            <li
              v-for="item in zoneLaunchReadinessErrors"
              :key="item"
            >
              {{ item }}
            </li>
          </ul>
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

    <PumpCalibrationModal
      v-if="showPumpCalibrationModal"
      :show="showPumpCalibrationModal"
      :zone-id="selectedZone?.id ?? null"
      :devices="pumpCalibrationDevices"
      :loading-run="pumpCalibrationLoadingRun"
      :loading-save="pumpCalibrationLoadingSave"
      :save-success-seq="pumpCalibrationSaveSeq"
      :run-success-seq="pumpCalibrationRunSeq"
      :last-run-token="pumpCalibrationLastRunToken"
      @close="closePumpCalibrationModal"
      @start="startPumpCalibration"
      @save="savePumpCalibration"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import CorrectionRuntimeReadinessCard from '@/Components/CorrectionRuntimeReadinessCard.vue'
import GreenhouseClimateConfiguration from '@/Components/GreenhouseClimateConfiguration.vue'
import PlantCreateModal from '@/Components/PlantCreateModal.vue'
import PumpCalibrationModal from '@/Components/PumpCalibrationModal.vue'
import ZoneCorrectionCalibrationStack from '@/Components/ZoneCorrectionCalibrationStack.vue'
import ZoneAutomationProfileSections from '@/Components/ZoneAutomationProfileSections.vue'
import { useAutomationConfig } from '@/composables/useAutomationConfig'
import { usePumpCalibrationActions } from '@/composables/usePumpCalibrationActions'
import { resolveRecipePhasePidTargets } from '@/composables/recipePhasePidTargets'
import { useSetupWizard } from '@/composables/useSetupWizard'
import { useSensorCalibrationSettings } from '@/composables/useSensorCalibrationSettings'
import { useToast } from '@/composables/useToast'
import { payloadFromZoneLogicDocument, resolveZoneLogicProfileEntry } from '@/composables/zoneLogicProfileDocument'
import { applyAutomationFromRecipe, type LightingFormState, type WaterFormState, type ZoneClimateFormState } from '@/composables/zoneAutomationFormLogic'
import type { PumpCalibrationRunPayload, PumpCalibrationSavePayload } from '@/types/Calibration'
import type { Device, DeviceChannel } from '@/types/Device'
import type { ZoneAutomationSectionSaveKey } from '@/composables/zoneAutomationTypes'

const { showToast } = useToast()
const automationConfig = useAutomationConfig(showToast)
const sensorCalibrationSettings = useSensorCalibrationSettings()

const {
  canConfigure,
  loading,
  greenhouseMode,
  zoneMode,
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
  stepZoneDevicesDone,
  stepZoneAutomationDone,
  stepZoneCalibrationReady,
  zoneAutomationAssignmentsReady,
  zoneAutomationNodesReady,
  zoneAutomationExpectedNodeIds,
  selectedZoneHasActiveCycle,
  zoneLaunchReadinessErrors,
  zoneLaunchReady,
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
  refreshZoneLaunchReadiness,
  applyGreenhouseClimate,
  saveZoneDeviceBindingsSection,
  applyAutomation,
  openCycleWizard,
  formatDateTime,
} = useSetupWizard()

const showPlantCreateWizard = ref(false)
const showPumpCalibrationModal = ref(false)
const zoneCorrectionAuthoritySeq = ref(0)
const savingAutomationSection = ref<ZoneAutomationSectionSaveKey | null>(null)
const committedWaterForm = ref<WaterFormState>(cloneWaterForm(automationWaterForm))
const committedLightingForm = ref<LightingFormState>(cloneLightingForm(automationLightingForm))
const committedZoneClimateForm = ref<ZoneClimateFormState>(cloneZoneClimateForm(zoneClimateForm))
const pumpCalibrationActions = usePumpCalibrationActions({
  getZoneId: () => selectedZone.value?.id ?? null,
  showToast,
  runSuccessMessage: 'Запуск калибровки отправлен. После завершения введите фактический объём и сохраните.',
  saveSuccessMessage: 'Калибровка насоса сохранена.',
  onSaveSuccess: async () => {
    await refreshAvailableNodes()
    if (selectedZone.value?.id) {
      await refreshZoneLaunchReadiness(selectedZone.value.id)
    }
  },
})
const pumpCalibrationLoadingRun = pumpCalibrationActions.loadingRun
const pumpCalibrationLoadingSave = pumpCalibrationActions.loadingSave
const pumpCalibrationSaveSeq = pumpCalibrationActions.saveSeq
const pumpCalibrationRunSeq = pumpCalibrationActions.runSeq
const pumpCalibrationLastRunToken = pumpCalibrationActions.lastRunToken
const wizardReadinessRefreshToken = computed(
  () => `${pumpCalibrationSaveSeq.value}:${pumpCalibrationRunSeq.value}:${zoneCorrectionAuthoritySeq.value}`
)
const selectedRecipePhaseTargets = computed(() => {
  const phases = Array.isArray(selectedRecipe.value?.phases) ? [...selectedRecipe.value.phases] : []
  const firstPhase = phases.sort((left, right) => (left.phase_index ?? 0) - (right.phase_index ?? 0))[0] ?? null

  return resolveRecipePhasePidTargets(firstPhase)
})

watch(
  () => [selectedZone.value?.id ?? null, wizardReadinessRefreshToken.value] as const,
  async ([zoneId]) => {
    if (!zoneId) {
      return
    }

    await refreshZoneLaunchReadiness(zoneId)
  },
  { immediate: true }
)

const pumpCalibrationDevices = computed<Device[]>(() => {
  const zoneId = selectedZone.value?.id ?? null
  if (!zoneId) {
    return []
  }

  return availableNodes.value
    .filter((node) => node.zone_id === zoneId || node.pending_zone_id === zoneId)
    .map((node) => {
      const channels = Array.isArray(node.channels)
        ? node.channels.map((channel): DeviceChannel => {
          const raw = channel as Record<string, unknown>
          const channelId = typeof raw.id === 'number'
            ? raw.id
            : (typeof raw.node_channel_id === 'number' ? raw.node_channel_id : undefined)

          return {
            id: channelId,
            node_channel_id: channelId,
            node_id: node.id,
            channel: String(channel.channel ?? ''),
            type: String(channel.type ?? ''),
            metric: channel.metric ?? null,
            unit: channel.unit ?? null,
            binding_role: typeof channel.binding_role === 'string' ? channel.binding_role : null,
            config: raw.config && typeof raw.config === 'object' && !Array.isArray(raw.config)
              ? raw.config as Record<string, unknown>
              : undefined,
            pump_calibration: raw.pump_calibration && typeof raw.pump_calibration === 'object' && !Array.isArray(raw.pump_calibration)
              ? raw.pump_calibration as DeviceChannel['pump_calibration']
              : null,
            actuator_type: typeof raw.actuator_type === 'string' ? raw.actuator_type : null,
            pump_component: typeof raw.pump_component === 'string' ? raw.pump_component : null,
            description: typeof raw.description === 'string' ? raw.description : null,
          }
        })
        : []

      return {
        id: node.id,
        uid: node.uid ?? `node-${node.id}`,
        name: node.name,
        type: (typeof node.type === 'string' ? node.type : 'unknown') as Device['type'],
        status: 'unknown',
        lifecycle_state: (node.lifecycle_state ?? undefined) as Device['lifecycle_state'],
        zone_id: node.zone_id ?? undefined,
        pending_zone_id: node.pending_zone_id ?? null,
        channels,
      }
    })
})

function openPumpCalibrationModal(): void {
  if (!selectedZone.value?.id) {
    showToast('Сначала выберите зону.', 'warning')
    return
  }

  showPumpCalibrationModal.value = true
}

function closePumpCalibrationModal(): void {
  showPumpCalibrationModal.value = false
}

function focusProcessCalibration(): void {
  if (typeof document === 'undefined') {
    return
  }

  const target = document.getElementById('zone-process-calibration-panel-shared')
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function focusPidConfig(): void {
  if (typeof document === 'undefined') {
    return
  }

  const target = document.getElementById('zone-pid-config-panel-shared')
  const details = target?.closest('details')
  if (details instanceof HTMLDetailsElement) {
    details.open = true
  }
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }

  return value as Record<string, unknown>
}

function cloneWaterForm(source: WaterFormState): WaterFormState {
  return { ...source }
}

function cloneLightingForm(source: LightingFormState): LightingFormState {
  return { ...source }
}

function cloneZoneClimateForm(source: ZoneClimateFormState): ZoneClimateFormState {
  return { ...source }
}

function syncCommittedAutomationStateFromCurrentForms(): void {
  committedWaterForm.value = cloneWaterForm(automationWaterForm)
  committedLightingForm.value = cloneLightingForm(automationLightingForm)
  committedZoneClimateForm.value = cloneZoneClimateForm(zoneClimateForm)
}

function applySubsystemsToCurrentForms(subsystems: Record<string, unknown>, updatedAt: string | null): void {
  applyAutomationFromRecipe(
    { extensions: { subsystems } },
    {
      climateForm: automationClimateForm,
      waterForm: automationWaterForm,
      lightingForm: automationLightingForm,
      zoneClimateForm,
    }
  )
  zoneClimateForm.enabled = Boolean(asRecord(subsystems.zone_climate)?.enabled ?? false)
  automationAppliedAt.value = updatedAt
}

function buildCommittedAutomationStateFromSubsystems(subsystems: Record<string, unknown>): void {
  const waterForm = cloneWaterForm(automationWaterForm)
  const lightingForm = cloneLightingForm(automationLightingForm)
  const zoneClimate = cloneZoneClimateForm(zoneClimateForm)

  applyAutomationFromRecipe(
    { extensions: { subsystems } },
    {
      climateForm: automationClimateForm,
      waterForm,
      lightingForm,
      zoneClimateForm: zoneClimate,
    }
  )
  zoneClimate.enabled = Boolean(asRecord(subsystems.zone_climate)?.enabled ?? false)

  committedWaterForm.value = waterForm
  committedLightingForm.value = lightingForm
  committedZoneClimateForm.value = zoneClimate
}

async function loadCommittedZoneAutomationProfile(zoneId: number | null): Promise<void> {
  syncCommittedAutomationStateFromCurrentForms()
  automationAppliedAt.value = null

  if (!zoneId) {
    return
  }

  try {
    const document = await automationConfig.getDocument<Record<string, unknown>>('zone', zoneId, 'zone.logic_profile')
    const profile = resolveZoneLogicProfileEntry(payloadFromZoneLogicDocument(document), 'setup')
    if (!profile) {
      return
    }

    applySubsystemsToCurrentForms(profile.subsystems, profile.updated_at)
    buildCommittedAutomationStateFromSubsystems(profile.subsystems)
  } catch {
    // Existing zones without saved automation profile are valid; keep current form state as committed baseline.
  }
}

function buildFormsForZoneAutomationBlock(
  section: ZoneAutomationSectionSaveKey
): { waterForm: WaterFormState; lightingForm: LightingFormState; zoneClimateForm: ZoneClimateFormState } {
  if (section === 'water_contour') {
    return {
      waterForm: cloneWaterForm(automationWaterForm),
      lightingForm: cloneLightingForm(committedLightingForm.value),
      zoneClimateForm: cloneZoneClimateForm(committedZoneClimateForm.value),
    }
  }

  if (section === 'lighting') {
    return {
      waterForm: cloneWaterForm(committedWaterForm.value),
      lightingForm: cloneLightingForm(automationLightingForm),
      zoneClimateForm: cloneZoneClimateForm(committedZoneClimateForm.value),
    }
  }

  return {
    waterForm: cloneWaterForm(committedWaterForm.value),
    lightingForm: cloneLightingForm(committedLightingForm.value),
    zoneClimateForm: cloneZoneClimateForm(zoneClimateForm),
  }
}

function commitSavedZoneAutomationForms(forms: {
  waterForm: WaterFormState
  lightingForm: LightingFormState
  zoneClimateForm: ZoneClimateFormState
}): void {
  committedWaterForm.value = cloneWaterForm(forms.waterForm)
  committedLightingForm.value = cloneLightingForm(forms.lightingForm)
  committedZoneClimateForm.value = cloneZoneClimateForm(forms.zoneClimateForm)
}

watch(
  () => selectedZone.value?.id ?? null,
  async (zoneId, previousZoneId) => {
    if (zoneId === previousZoneId) {
      return
    }

    await loadCommittedZoneAutomationProfile(zoneId)
  },
  { immediate: true }
)

async function startPumpCalibration(payload: PumpCalibrationRunPayload): Promise<void> {
  await pumpCalibrationActions.startPumpCalibration(payload)
}

async function savePumpCalibration(payload: PumpCalibrationSavePayload): Promise<void> {
  await pumpCalibrationActions.savePumpCalibration(payload)
}

async function saveZoneAutomationBlock(section: ZoneAutomationSectionSaveKey): Promise<void> {
  if (!canConfigure.value || !selectedZone.value?.id) {
    return
  }

  savingAutomationSection.value = section
  try {
    if (section === 'water_contour') {
      const bindingsSaved = await saveZoneDeviceBindingsSection(['irrigation', 'ph_correction', 'ec_correction', 'soil_moisture_sensor'])
      if (!bindingsSaved) {
        return
      }
      const formsForSave = buildFormsForZoneAutomationBlock(section)
      const applied = await applyAutomation(formsForSave)
      if (applied) {
        commitSavedZoneAutomationForms(formsForSave)
      }
      return
    }

    if (section === 'lighting') {
      const bindingsSaved = await saveZoneDeviceBindingsSection(['light'])
      if (!bindingsSaved) {
        return
      }
      const formsForSave = buildFormsForZoneAutomationBlock(section)
      const applied = await applyAutomation(formsForSave)
      if (applied) {
        commitSavedZoneAutomationForms(formsForSave)
      }
      return
    }

    if (section === 'zone_climate') {
      const bindingsSaved = await saveZoneDeviceBindingsSection(['co2_sensor', 'co2_actuator', 'root_vent_actuator'])
      if (!bindingsSaved) {
        return
      }
      const formsForSave = buildFormsForZoneAutomationBlock(section)
      const applied = await applyAutomation(formsForSave)
      if (applied) {
        commitSavedZoneAutomationForms(formsForSave)
      }
    }
  } finally {
    if (selectedZone.value?.id) {
      await refreshZoneLaunchReadiness(selectedZone.value.id)
    }
    savingAutomationSection.value = null
  }
}

async function handleZonePidConfigSaved(): Promise<void> {
  if (!selectedZone.value?.id) {
    return
  }

  zoneCorrectionAuthoritySeq.value += 1
  await refreshZoneLaunchReadiness(selectedZone.value.id)
}

watch(
  () => [pumpCalibrationSaveSeq.value, pumpCalibrationRunSeq.value],
  async () => {
    if (!selectedZone.value?.id) {
      return
    }

    await refreshZoneLaunchReadiness(selectedZone.value.id)
  }
)

async function handleZoneCorrectionCalibrationUpdated(): Promise<void> {
  if (!selectedZone.value?.id) {
    return
  }

  zoneCorrectionAuthoritySeq.value += 1
  await refreshZoneLaunchReadiness(selectedZone.value.id)
}

function handlePlantCreated(plant: { id?: number; name?: string } | null): void {
  showPlantCreateWizard.value = false

  if (!plant?.id) {
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
  selectPlant()
}

function openPlantCreateWizard(): void {
  if (!canConfigure.value) {
    return
  }

  showPlantCreateWizard.value = true
}

function handlePlantCreateClose(): void {
  showPlantCreateWizard.value = false
}
</script>
