<template>
  <!-- eslint-disable vue/singleline-html-element-content-newline -->
  <AppLayout>
    <div class="space-y-5">
      <section class="ui-hero p-6">
        <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">
          Мастер настройки системы
        </h1>
        <p class="text-sm text-[color:var(--text-muted)] mt-2">
          Пошаговая настройка теплицы, зоны, культуры, устройств и автоматики.
        </p>

        <div class="mt-4 h-2 rounded-full bg-[color:var(--border-muted)] overflow-hidden">
          <div
            class="h-full bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] transition-all duration-500"
            :style="{ width: `${progressPercent}%` }"
          ></div>
        </div>

        <div class="mt-3 text-xs text-[color:var(--text-dim)]">
          Прогресс: {{ progressPercent }}% ({{ completedSteps }}/6)
        </div>
      </section>

      <section
        v-if="!canConfigure"
        class="rounded-xl border border-[color:var(--badge-warning-border)] bg-[color:var(--badge-warning-bg)] p-4 text-sm text-[color:var(--badge-warning-text)]"
      >
        Режим только для просмотра. Полная настройка доступна агроному или администратору.
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4">
        <h2 class="text-sm font-semibold text-[color:var(--text-primary)] mb-3">
          Сценарий запуска
        </h2>
        <ul class="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
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
            class="inline-flex items-center mr-3"
          >
            <span class="mr-1">{{ item.done ? '✓' : '•' }}</span>{{ item.label }}
          </span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            1. Теплица
          </h3>
          <Badge :variant="stepGreenhouseDone ? 'success' : 'neutral'">
            {{ stepGreenhouseDone ? 'Готово' : 'Не настроено' }}
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
          <Button
            size="sm"
            :disabled="!canConfigure || !greenhouseForm.name.trim() || loading.stepGreenhouse"
            @click="createGreenhouse"
          >
            {{ loading.stepGreenhouse ? 'Создание...' : 'Создать теплицу' }}
          </Button>
        </div>

        <div
          v-if="selectedGreenhouse"
          class="text-sm text-[color:var(--text-muted)]"
        >
          Выбрано: <span class="font-semibold text-[color:var(--text-primary)]">{{ selectedGreenhouse.name }}</span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
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
          v-if="zoneMode === 'create'"
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
            disabled
          />
          <Button
            size="sm"
            :disabled="!canConfigure || !stepGreenhouseDone || !zoneForm.name.trim() || loading.stepZone"
            @click="createZone"
          >
            {{ loading.stepZone ? 'Создание...' : 'Создать зону' }}
          </Button>
        </div>

        <div
          v-if="selectedZone"
          class="text-sm text-[color:var(--text-muted)]"
        >
          Выбрано: <span class="font-semibold text-[color:var(--text-primary)]">{{ selectedZone.name }}</span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            3. Культура и рецепт
          </h3>
          <Badge :variant="stepPlantDone ? 'success' : 'neutral'">
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
          <div class="text-xs text-[color:var(--text-muted)] mb-1">
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

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            4. Устройства
          </h3>
          <Badge :variant="stepDevicesDone ? 'success' : 'neutral'">
            {{ stepDevicesDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div class="space-y-1 min-w-0">
            <label class="block text-xs text-[color:var(--text-muted)]">Полив (обязательно)</label>
            <div class="flex items-stretch gap-2">
              <select
                v-model.number="deviceAssignments.irrigation"
                class="input-select min-w-0 flex-1"
                :disabled="!canConfigure || !stepZoneDone || irrigationNodes.length === 0"
              >
                <option :value="null">Выберите узел полива</option>
                <option v-for="node in irrigationNodes" :key="`irrigation-${node.id}`" :value="node.id">
                  {{ node.name || node.uid || `Node #${node.id}` }}
                </option>
              </select>
              <Button
                size="sm"
                variant="secondary"
                class="shrink-0 whitespace-nowrap"
                :disabled="!canAttachRole('irrigation')"
                @click="attachNodeByRole('irrigation')"
              >
                {{ attachButtonLabel('irrigation') }}
              </Button>
            </div>
          </div>
          <div class="space-y-1 min-w-0">
            <label class="block text-xs text-[color:var(--text-muted)]">Коррекция pH (обязательно)</label>
            <div class="flex items-stretch gap-2">
              <select
                v-model.number="deviceAssignments.ph_correction"
                class="input-select min-w-0 flex-1"
                :disabled="!canConfigure || !stepZoneDone || phCorrectionNodes.length === 0"
              >
                <option :value="null">Выберите узел коррекции pH</option>
                <option v-for="node in phCorrectionNodes" :key="`ph-correction-${node.id}`" :value="node.id">
                  {{ node.name || node.uid || `Node #${node.id}` }}
                </option>
              </select>
              <Button
                size="sm"
                variant="secondary"
                class="shrink-0 whitespace-nowrap"
                :disabled="!canAttachRole('ph_correction')"
                @click="attachNodeByRole('ph_correction')"
              >
                {{ attachButtonLabel('ph_correction') }}
              </Button>
            </div>
          </div>
          <div class="space-y-1 min-w-0">
            <label class="block text-xs text-[color:var(--text-muted)]">Коррекция EC (обязательно)</label>
            <div class="flex items-stretch gap-2">
              <select
                v-model.number="deviceAssignments.ec_correction"
                class="input-select min-w-0 flex-1"
                :disabled="!canConfigure || !stepZoneDone || ecCorrectionNodes.length === 0"
              >
                <option :value="null">Выберите узел коррекции EC</option>
                <option v-for="node in ecCorrectionNodes" :key="`ec-correction-${node.id}`" :value="node.id">
                  {{ node.name || node.uid || `Node #${node.id}` }}
                </option>
              </select>
              <Button
                size="sm"
                variant="secondary"
                class="shrink-0 whitespace-nowrap"
                :disabled="!canAttachRole('ec_correction')"
                @click="attachNodeByRole('ec_correction')"
              >
                {{ attachButtonLabel('ec_correction') }}
              </Button>
            </div>
          </div>
          <div class="space-y-1 min-w-0">
            <label class="block text-xs text-[color:var(--text-muted)]">Накопительный узел (обязательно)</label>
            <div class="flex items-stretch gap-2">
              <select
                v-model.number="deviceAssignments.accumulation"
                class="input-select min-w-0 flex-1"
                :disabled="!canConfigure || !stepZoneDone || accumulationNodes.length === 0"
              >
                <option :value="null">Выберите накопительный узел</option>
                <option v-for="node in accumulationNodes" :key="`accumulation-${node.id}`" :value="node.id">
                  {{ node.name || node.uid || `Node #${node.id}` }}
                </option>
              </select>
              <Button
                size="sm"
                variant="secondary"
                class="shrink-0 whitespace-nowrap"
                :disabled="!canAttachRole('accumulation')"
                @click="attachNodeByRole('accumulation')"
              >
                {{ attachButtonLabel('accumulation') }}
              </Button>
            </div>
          </div>
          <div class="space-y-1 min-w-0">
            <label class="block text-xs text-[color:var(--text-muted)]">Климат (опционально)</label>
            <div class="flex items-stretch gap-2">
              <select
                v-model.number="deviceAssignments.climate"
                class="input-select min-w-0 flex-1"
                :disabled="!canConfigure || !stepZoneDone || climateNodes.length === 0"
              >
                <option :value="null">Не выбирать</option>
                <option v-for="node in climateNodes" :key="`climate-${node.id}`" :value="node.id">
                  {{ node.name || node.uid || `Node #${node.id}` }}
                </option>
              </select>
              <Button
                size="sm"
                variant="secondary"
                class="shrink-0 whitespace-nowrap"
                :disabled="!canAttachRole('climate')"
                @click="attachNodeByRole('climate')"
              >
                {{ attachButtonLabel('climate') }}
              </Button>
            </div>
          </div>
          <div class="space-y-1 min-w-0">
            <label class="block text-xs text-[color:var(--text-muted)]">Свет (опционально)</label>
            <div class="flex items-stretch gap-2">
              <select
                v-model.number="deviceAssignments.light"
                class="input-select min-w-0 flex-1"
                :disabled="!canConfigure || !stepZoneDone || lightNodes.length === 0"
              >
                <option :value="null">Не выбирать</option>
                <option v-for="node in lightNodes" :key="`light-${node.id}`" :value="node.id">
                  {{ node.name || node.uid || `Node #${node.id}` }}
                </option>
              </select>
              <Button
                size="sm"
                variant="secondary"
                class="shrink-0 whitespace-nowrap"
                :disabled="!canAttachRole('light')"
                @click="attachNodeByRole('light')"
              >
                {{ attachButtonLabel('light') }}
              </Button>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-muted)]">
          <span>Привязано: {{ attachedNodesCount }} (минимум 4 обязательных)</span>
          <span v-if="missingRequiredDevices.length > 0" class="text-[color:var(--badge-warning-text)]">
            Не выбрано: {{ missingRequiredDevices.join(', ') }}
          </span>
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canConfigure || loading.nodes"
            @click="refreshAvailableNodes"
          >
            {{ loading.nodes ? 'Обновление...' : 'Обновить' }}
          </Button>
          <Button
            size="sm"
            :disabled="!canAttachRequiredNodes"
            @click="attachConfiguredNodes"
          >
            {{ loading.stepDevices ? 'Привязка...' : 'Привязать ноды зоны' }}
          </Button>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            5. Логика автоматики
          </h3>
          <Badge :variant="stepAutomationDone ? 'success' : 'neutral'">
            {{ stepAutomationDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="grid gap-3 md:grid-cols-3">
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs text-[color:var(--text-muted)]">Система</div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ automationSystemLabel }}</div>
          </div>
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs text-[color:var(--text-muted)]">pH target</div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ automationWaterForm.targetPh.toFixed(2) }}</div>
          </div>
          <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3">
            <div class="text-xs text-[color:var(--text-muted)]">EC target</div>
            <div class="mt-1 text-sm font-semibold text-[color:var(--text-primary)]">{{ automationWaterForm.targetEc.toFixed(2) }}</div>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <label class="flex items-center gap-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-sm text-[color:var(--text-primary)]">
            <input
              v-model="automationClimateForm.enabled"
              type="checkbox"
              :disabled="!canConfigure"
            />
            Управлять климатом
          </label>
          <label class="flex items-center gap-2 rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-sm text-[color:var(--text-primary)]">
            <input
              v-model="automationLightingForm.enabled"
              type="checkbox"
              :disabled="!canConfigure"
            />
            Управлять освещением
          </label>
        </div>

        <div class="text-xs text-[color:var(--text-muted)]">
          Топология воды: {{ waterTopologyLabel }}
        </div>
        <div class="rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-surface-strong)] p-3 text-xs text-[color:var(--text-muted)] space-y-2">
          <div class="font-semibold text-[color:var(--text-primary)]">Конфигуратор логики:</div>
          <div>1. Кнопка "Открыть конфигуратор" запускает тот же мастер логики, что и на вкладке автоматизации зоны.</div>
          <div>2. Настраиваются интервалы и поведение: полив, климат, досветка, диагностика, смена раствора.</div>
          <div>3. Параметры накопления воды и подготовки рабочего раствора сохраняются в profile `setup`.</div>
          <div>4. По "Применить логику автоматики" профиль сохраняется в БД и отправляется `GROWTH_CYCLE_CONFIG` (`profile_mode=setup`).</div>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            :disabled="!canConfigure || loading.stepAutomation"
            @click="openAutomationConfigurator"
          >
            Открыть конфигуратор
          </Button>
          <span class="text-xs text-[color:var(--text-muted)]">
            Климат: {{ automationClimateForm.intervalMinutes }} мин · Полив: {{ automationWaterForm.intervalMinutes }} мин / {{ automationWaterForm.durationSeconds }} сек · Диагностика: {{ automationWaterForm.diagnosticsIntervalMinutes }} мин
          </span>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            :disabled="!canConfigure || !stepZoneDone || loading.stepAutomation"
            @click="applyAutomation"
          >
            {{ loading.stepAutomation ? 'Отправка...' : 'Применить логику автоматики' }}
          </Button>
          <span class="text-xs text-[color:var(--text-muted)]">
            <span v-if="automationAppliedAt">Последнее применение: {{ formatDateTime(automationAppliedAt) }}</span>
            <span v-else>Ещё не применено</span>
          </span>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            6. Запуск и контроль
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
        <div
          v-if="selectedZoneHasActiveCycle && launchBlockedReason"
          class="text-xs text-[color:var(--badge-warning-text)]"
        >
          {{ launchBlockedReason }}
        </div>
      </section>
    </div>

    <ZoneAutomationEditWizard
      :open="showAutomationConfigurator"
      :climate-form="automationClimateForm"
      :water-form="automationWaterForm"
      :lighting-form="automationLightingForm"
      :is-applying="loading.stepAutomation"
      :is-system-type-locked="false"
      @close="showAutomationConfigurator = false"
      @apply="onApplyAutomationConfigurator"
    />

    <PlantCreateModal
      :show="showPlantCreateWizard"
      @close="handlePlantCreateClose"
      @created="handlePlantCreated"
    />
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import PlantCreateModal from '@/Components/PlantCreateModal.vue'
import ZoneAutomationEditWizard from '@/Pages/Zones/Tabs/ZoneAutomationEditWizard.vue'
import { useSetupWizard } from '@/composables/useSetupWizard'
import type { Node, SetupWizardDeviceAssignments } from '@/composables/setupWizardTypes'
import type {
  ClimateFormState,
  LightingFormState,
  WaterFormState,
} from '@/composables/zoneAutomationTypes'

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
  selectedGreenhouseId,
  selectedZoneId,
  selectedPlantId,
  selectedGreenhouse,
  selectedZone,
  selectedRecipe,
  selectedNodeIds,
  attachedNodesCount,
  greenhouseForm,
  zoneForm,
  automationClimateForm,
  automationWaterForm,
  automationLightingForm,
  automationAppliedAt,
  stepGreenhouseDone,
  stepZoneDone,
  stepPlantDone,
  stepRecipeDone,
  stepDevicesDone,
  stepAutomationDone,
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
  createGreenhouse,
  selectGreenhouse,
  createZone,
  selectZone,
  selectPlant,
  attachNodesToZone,
  isNodeAttachedToCurrentZone,
  refreshAvailableNodes,
  applyAutomation,
  openCycleWizard,
  formatDateTime,
} = useSetupWizard()

const showPlantCreateWizard = ref<boolean>(false)
const showAutomationConfigurator = ref<boolean>(false)
type DeviceRole = 'irrigation' | 'ph_correction' | 'ec_correction' | 'accumulation' | 'climate' | 'light'
const attachingRole = ref<DeviceRole | null>(null)

const deviceAssignments = reactive<SetupWizardDeviceAssignments>({
  irrigation: null,
  ph_correction: null,
  ec_correction: null,
  accumulation: null,
  climate: null,
  light: null,
})

function resetDeviceAssignments(): void {
  deviceAssignments.irrigation = null
  deviceAssignments.ph_correction = null
  deviceAssignments.ec_correction = null
  deviceAssignments.accumulation = null
  deviceAssignments.climate = null
  deviceAssignments.light = null
}

function nodeChannels(node: Node): string[] {
  const channels = Array.isArray(node.channels) ? node.channels : []
  return channels
    .map((item) => String(item?.channel ?? '').toLowerCase())
    .filter((item) => item.length > 0)
}

function nodeType(node: Node): string {
  return String(node.type ?? '').toLowerCase()
}

function hasAnyChannel(node: Node, candidates: string[]): boolean {
  const set = new Set(nodeChannels(node))
  return candidates.some((candidate) => set.has(candidate))
}

function matchesRole(node: Node, role: DeviceRole): boolean {
  const type = nodeType(node)

  if (role === 'irrigation') {
    return type === 'irrig' || hasAnyChannel(node, ['pump_irrigation', 'valve_irrigation', 'main_pump'])
  }

  if (role === 'ph_correction') {
    return type === 'ph' || hasAnyChannel(node, ['ph_sensor', 'pump_acid', 'pump_base'])
  }

  if (role === 'ec_correction') {
    return type === 'ec' || hasAnyChannel(node, ['ec_sensor', 'pump_a', 'pump_b', 'pump_c', 'pump_d'])
  }

  if (role === 'accumulation') {
    return type === 'water_sensor' || type === 'recirculation' || hasAnyChannel(node, ['water_level', 'pump_in', 'drain', 'drain_main'])
  }

  if (role === 'climate') {
    return type === 'climate' || hasAnyChannel(node, ['temp_air', 'air_temp_c', 'air_rh', 'humidity_air', 'co2_ppm', 'fan_air', 'heater_air', 'vent_drive'])
  }

  return type === 'light' || hasAnyChannel(node, ['white_light', 'uv_light', 'light_main', 'light_level', 'lux_main'])
}

function nodesByRole(role: DeviceRole): Node[] {
  return availableNodes.value.filter((node) => matchesRole(node, role))
}

const irrigationNodes = computed<Node[]>(() => nodesByRole('irrigation'))
const phCorrectionNodes = computed<Node[]>(() => nodesByRole('ph_correction'))
const ecCorrectionNodes = computed<Node[]>(() => nodesByRole('ec_correction'))
const accumulationNodes = computed<Node[]>(() => nodesByRole('accumulation'))
const climateNodes = computed<Node[]>(() => nodesByRole('climate'))
const lightNodes = computed<Node[]>(() => nodesByRole('light'))

function shouldResetRoleAssignment(nodeId: number | null, availableIds: Set<number>): boolean {
  if (typeof nodeId !== 'number') {
    return false
  }

  if (availableIds.has(nodeId)) {
    return false
  }

  return !isNodeAttachedToCurrentZone(nodeId)
}

watch(
  () => selectedZone.value?.id ?? null,
  (currentZoneId, previousZoneId) => {
    if (currentZoneId === previousZoneId) {
      return
    }

    resetDeviceAssignments()
    attachingRole.value = null
  }
)

watch(
  availableNodes,
  (nodes) => {
    const ids = new Set(nodes.map((node) => node.id))
    if (shouldResetRoleAssignment(deviceAssignments.irrigation, ids)) deviceAssignments.irrigation = null
    if (shouldResetRoleAssignment(deviceAssignments.ph_correction, ids)) deviceAssignments.ph_correction = null
    if (shouldResetRoleAssignment(deviceAssignments.ec_correction, ids)) deviceAssignments.ec_correction = null
    if (shouldResetRoleAssignment(deviceAssignments.accumulation, ids)) deviceAssignments.accumulation = null
    if (shouldResetRoleAssignment(deviceAssignments.climate, ids)) deviceAssignments.climate = null
    if (shouldResetRoleAssignment(deviceAssignments.light, ids)) deviceAssignments.light = null
  },
  { immediate: true }
)

const selectedNodeIdsByRoles = computed<number[]>(() => {
  const ids = new Set<number>()
  const values = [
    deviceAssignments.irrigation,
    deviceAssignments.ph_correction,
    deviceAssignments.ec_correction,
    deviceAssignments.accumulation,
    deviceAssignments.climate,
    deviceAssignments.light,
  ]
  values.forEach((id) => {
    if (typeof id === 'number') {
      ids.add(id)
    }
  })
  return Array.from(ids)
})

const missingRequiredDevices = computed<string[]>(() => {
  const missing: string[] = []
  if (!deviceAssignments.irrigation) missing.push('полив')
  if (!deviceAssignments.ph_correction) missing.push('коррекция pH')
  if (!deviceAssignments.ec_correction) missing.push('коррекция EC')
  if (!deviceAssignments.accumulation) missing.push('накопительный узел')
  return missing
})

const canAttachRequiredNodes = computed<boolean>(() => {
  return canConfigure.value
    && stepZoneDone.value
    && missingRequiredDevices.value.length === 0
    && !loading.stepDevices
})

const automationSystemLabel = computed<string>(() => {
  if (automationWaterForm.systemType === 'drip') {
    return 'Капельный полив (drip)'
  }
  if (automationWaterForm.systemType === 'substrate_trays') {
    return 'Лотки/субстрат (substrate trays)'
  }
  if (automationWaterForm.systemType === 'nft') {
    return 'NFT (рециркуляция)'
  }

  return automationWaterForm.systemType
})

interface AutomationConfiguratorApplyPayload {
  climateForm: ClimateFormState
  waterForm: WaterFormState
  lightingForm: LightingFormState
}

function openAutomationConfigurator(): void {
  if (!canConfigure.value) {
    return
  }
  showAutomationConfigurator.value = true
}

function onApplyAutomationConfigurator(payload: AutomationConfiguratorApplyPayload): void {
  Object.assign(automationClimateForm, payload.climateForm)
  Object.assign(automationWaterForm, payload.waterForm)
  Object.assign(automationLightingForm, payload.lightingForm)
  showAutomationConfigurator.value = false
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

async function attachConfiguredNodes(): Promise<void> {
  if (!canAttachRequiredNodes.value) {
    return
  }

  selectedNodeIds.value = selectedNodeIdsByRoles.value
  await attachNodesToZone({ ...deviceAssignments })
}

function canAttachRole(role: DeviceRole): boolean {
  const nodeId = deviceAssignments[role]
  return canConfigure.value
    && stepZoneDone.value
    && typeof nodeId === 'number'
    && !isNodeAttachedToCurrentZone(nodeId)
    && !loading.stepDevices
}

function attachButtonLabel(role: DeviceRole): string {
  const nodeId = deviceAssignments[role]
  if (typeof nodeId === 'number' && isNodeAttachedToCurrentZone(nodeId)) {
    return 'Привязано'
  }

  if (loading.stepDevices && attachingRole.value === role) {
    return 'Привязка...'
  }

  return 'Привязать'
}

async function attachNodeByRole(role: DeviceRole): Promise<void> {
  if (!canAttachRole(role)) {
    return
  }

  const nodeId = deviceAssignments[role]
  if (typeof nodeId !== 'number') {
    return
  }

  attachingRole.value = role
  try {
    selectedNodeIds.value = [nodeId]
    const assignmentsPayload = missingRequiredDevices.value.length === 0
      ? { ...deviceAssignments }
      : null
    await attachNodesToZone(assignmentsPayload)
  } finally {
    attachingRole.value = null
  }
}
</script>
