<template>
  <!-- eslint-disable vue/singleline-html-element-content-newline -->
  <AppLayout>
    <div class="space-y-5">
      <section class="ui-hero p-6">
        <h1 class="text-2xl font-semibold text-[color:var(--text-primary)]">
          Мастер настройки системы
        </h1>
        <p class="text-sm text-[color:var(--text-muted)] mt-2">
          Пошаговая настройка теплицы, зоны, растения, рецепта, устройств и автоматики.
        </p>

        <div class="mt-4 h-2 rounded-full bg-[color:var(--border-muted)] overflow-hidden">
          <div
            class="h-full bg-[linear-gradient(90deg,var(--accent-cyan),var(--accent-green))] transition-all duration-500"
            :style="{ width: `${progressPercent}%` }"
          ></div>
        </div>

        <div class="mt-3 text-xs text-[color:var(--text-dim)]">
          Прогресс: {{ progressPercent }}% ({{ completedSteps }}/7)
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

        <div class="flex gap-2">
          <Button
            size="sm"
            :variant="greenhouseMode === 'select' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="greenhouseMode = 'select'"
          >
            Выбрать
          </Button>
          <Button
            size="sm"
            :variant="greenhouseMode === 'create' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="greenhouseMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-if="greenhouseMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedGreenhouseId"
            class="input-select"
            :disabled="!canConfigure || loading.greenhouses"
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
            :disabled="!canConfigure || !selectedGreenhouseId || loading.stepGreenhouse"
            @click="selectGreenhouse"
          >
            {{ loading.stepGreenhouse ? 'Выбор...' : 'Применить' }}
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
            v-model="greenhouseForm.type"
            type="text"
            placeholder="Тип (indoor / tunnel)"
            class="input-field"
            :disabled="!canConfigure"
          />
          <input
            :value="generatedGreenhouseUid"
            type="text"
            class="input-field"
            disabled
          />
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

        <div class="flex gap-2">
          <Button
            size="sm"
            :variant="zoneMode === 'select' ? 'primary' : 'secondary'"
            :disabled="!canConfigure || !stepGreenhouseDone"
            @click="zoneMode = 'select'"
          >
            Выбрать
          </Button>
          <Button
            size="sm"
            :variant="zoneMode === 'create' ? 'primary' : 'secondary'"
            :disabled="!canConfigure || !stepGreenhouseDone"
            @click="zoneMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-if="zoneMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedZoneId"
            class="input-select"
            :disabled="!canConfigure || loading.zones || !stepGreenhouseDone"
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
            :disabled="!canConfigure || !selectedZoneId || loading.stepZone"
            @click="selectZone"
          >
            {{ loading.stepZone ? 'Выбор...' : 'Применить' }}
          </Button>
        </div>

        <div
          v-else
          class="grid gap-3 md:grid-cols-[1fr_1fr_auto]"
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
            3. Растение
          </h3>
          <Badge :variant="stepPlantDone ? 'success' : 'neutral'">
            {{ stepPlantDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="flex gap-2">
          <Button
            size="sm"
            :variant="plantMode === 'select' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="plantMode = 'select'"
          >
            Выбрать
          </Button>
          <Button
            size="sm"
            :variant="plantMode === 'create' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="plantMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-if="plantMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedPlantId"
            class="input-select"
            :disabled="!canConfigure || loading.plants"
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
            :disabled="!canConfigure || !selectedPlantId || loading.stepPlant"
            @click="selectPlant"
          >
            Применить
          </Button>
        </div>

        <div
          v-else
          class="grid gap-3 md:grid-cols-4"
        >
          <input
            v-model="plantForm.name"
            type="text"
            placeholder="Название растения"
            class="input-field"
            :disabled="!canConfigure"
          />
          <input
            v-model="plantForm.species"
            type="text"
            placeholder="Вид"
            class="input-field"
            :disabled="!canConfigure"
          />
          <input
            v-model="plantForm.variety"
            type="text"
            placeholder="Сорт"
            class="input-field"
            :disabled="!canConfigure"
          />
          <Button
            size="sm"
            :disabled="!canConfigure || !plantForm.name.trim() || loading.stepPlant"
            @click="createPlant"
          >
            {{ loading.stepPlant ? 'Создание...' : 'Создать растение' }}
          </Button>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            4. Рецепт
          </h3>
          <Badge :variant="stepRecipeDone ? 'success' : 'neutral'">
            {{ stepRecipeDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="flex gap-2">
          <Button
            size="sm"
            :variant="recipeMode === 'select' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="recipeMode = 'select'"
          >
            Выбрать
          </Button>
          <Button
            size="sm"
            :variant="recipeMode === 'create' ? 'primary' : 'secondary'"
            :disabled="!canConfigure"
            @click="recipeMode = 'create'"
          >
            Создать
          </Button>
        </div>

        <div
          v-if="recipeMode === 'select'"
          class="grid gap-3 md:grid-cols-[1fr_auto]"
        >
          <select
            v-model.number="selectedRecipeId"
            class="input-select"
            :disabled="!canConfigure || loading.recipes"
          >
            <option :value="null">Выберите рецепт</option>
            <option
              v-for="recipe in availableRecipes"
              :key="recipe.id"
              :value="recipe.id"
            >
              {{ recipe.name }}
            </option>
          </select>
          <Button
            size="sm"
            :disabled="!canConfigure || !selectedRecipeId || loading.stepRecipe"
            @click="selectRecipe"
          >
            Применить
          </Button>
        </div>

        <div
          v-else
          class="space-y-3"
        >
          <div class="grid gap-3 md:grid-cols-2">
            <input
              v-model="recipeForm.name"
              type="text"
              placeholder="Название рецепта"
              class="input-field"
              :disabled="!canConfigure"
            />
            <input
              v-model="recipeForm.description"
              type="text"
              placeholder="Описание рецепта"
              class="input-field"
              :disabled="!canConfigure"
            />
          </div>

          <div class="space-y-3">
            <div
              v-for="phase in recipeForm.phases"
              :key="phase.phase_index"
              class="rounded-xl border border-[color:var(--border-muted)] p-3 bg-[color:var(--bg-surface-strong)]"
            >
              <div class="text-xs text-[color:var(--text-muted)] mb-2">
                Фаза {{ phase.phase_index + 1 }}
              </div>
              <div class="grid gap-2 md:grid-cols-4">
                <input
                  v-model="phase.name"
                  type="text"
                  class="input-field"
                  placeholder="Имя фазы"
                  :disabled="!canConfigure"
                />
                <input
                  v-model.number="phase.duration_hours"
                  type="number"
                  min="1"
                  class="input-field"
                  placeholder="Часы"
                  :disabled="!canConfigure"
                />
                <input
                  v-model.number="phase.targets.ph"
                  type="number"
                  step="0.1"
                  class="input-field"
                  placeholder="pH"
                  :disabled="!canConfigure"
                />
                <input
                  v-model.number="phase.targets.ec"
                  type="number"
                  step="0.1"
                  class="input-field"
                  placeholder="EC"
                  :disabled="!canConfigure"
                />
              </div>
            </div>
          </div>

          <div class="flex gap-2">
            <Button
              size="sm"
              variant="secondary"
              :disabled="!canConfigure"
              @click="addRecipePhase"
            >
              Добавить фазу
            </Button>
            <Button
              size="sm"
              :disabled="!canConfigure || !recipeForm.name.trim() || loading.stepRecipe"
              @click="createRecipe"
            >
              {{ loading.stepRecipe ? 'Создание...' : 'Создать рецепт' }}
            </Button>
          </div>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            5. Устройства
          </h3>
          <Badge :variant="stepDevicesDone ? 'success' : 'neutral'">
            {{ stepDevicesDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          <label
            v-for="node in availableNodes"
            :key="node.id"
            class="rounded-lg border border-[color:var(--border-muted)] p-2 text-sm"
          >
            <input
              v-model="selectedNodeIds"
              type="checkbox"
              :value="node.id"
              class="mr-2"
              :disabled="!canConfigure || !stepZoneDone"
            />
            {{ node.name || node.uid || `Node #${node.id}` }}
          </label>
        </div>

        <div class="flex flex-wrap items-center gap-2 text-xs text-[color:var(--text-muted)]">
          <span>Привязано: {{ attachedNodesCount }}</span>
          <Button
            size="sm"
            :disabled="!canConfigure || !stepZoneDone || selectedNodeIds.length === 0 || loading.stepDevices"
            @click="attachNodesToZone"
          >
            {{ loading.stepDevices ? 'Привязка...' : 'Привязать выбранные узлы' }}
          </Button>
        </div>
      </section>

      <section class="surface-card surface-card--elevated border border-[color:var(--border-muted)] rounded-2xl p-4 space-y-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-base font-semibold text-[color:var(--text-primary)]">
            6. Логика автоматики
          </h3>
          <Badge :variant="stepAutomationDone ? 'success' : 'neutral'">
            {{ stepAutomationDone ? 'Готово' : 'Не настроено' }}
          </Badge>
        </div>

        <div class="grid gap-3 md:grid-cols-3">
          <label class="text-xs text-[color:var(--text-muted)]">
            Система
            <select
              v-model="automationForm.systemType"
              class="input-select mt-1"
              :disabled="!canConfigure"
            >
              <option value="drip">drip</option>
              <option value="substrate_trays">substrate_trays</option>
              <option value="nft">nft</option>
            </select>
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            pH
            <input
              v-model.number="automationForm.targetPh"
              type="number"
              step="0.1"
              class="input-field mt-1"
              :disabled="!canConfigure"
            />
          </label>
          <label class="text-xs text-[color:var(--text-muted)]">
            EC
            <input
              v-model.number="automationForm.targetEc"
              type="number"
              step="0.1"
              class="input-field mt-1"
              :disabled="!canConfigure"
            />
          </label>
        </div>

        <div class="text-xs text-[color:var(--text-muted)]">
          Топология воды: {{ waterTopologyLabel }}
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
            7. Запуск и контроль
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
      </section>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { useSetupWizard } from '@/composables/useSetupWizard'

const {
  canConfigure,
  loading,
  greenhouseMode,
  zoneMode,
  plantMode,
  recipeMode,
  availableGreenhouses,
  availableZones,
  availablePlants,
  availableRecipes,
  availableNodes,
  selectedGreenhouseId,
  selectedZoneId,
  selectedPlantId,
  selectedRecipeId,
  selectedGreenhouse,
  selectedZone,
  selectedNodeIds,
  attachedNodesCount,
  greenhouseForm,
  zoneForm,
  plantForm,
  recipeForm,
  automationForm,
  automationAppliedAt,
  stepGreenhouseDone,
  stepZoneDone,
  stepPlantDone,
  stepRecipeDone,
  stepDevicesDone,
  stepAutomationDone,
  completedSteps,
  progressPercent,
  canLaunch,
  launchChecklist,
  stepItems,
  waterTopologyLabel,
  generatedGreenhouseUid,
  addRecipePhase,
  createGreenhouse,
  selectGreenhouse,
  createZone,
  selectZone,
  createPlant,
  selectPlant,
  createRecipe,
  selectRecipe,
  attachNodesToZone,
  applyAutomation,
  openCycleWizard,
  formatDateTime,
} = useSetupWizard()
</script>
