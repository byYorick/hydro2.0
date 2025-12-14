<template>
  <AppLayout>
    <div class="max-w-4xl mx-auto">
      <div class="mb-6">
        <h1 class="text-2xl font-bold mb-2">Мастер запуска цикла выращивания</h1>
        <p class="text-sm text-neutral-400">Пошаговая настройка цикла от посадки до сбора</p>
      </div>

      <!-- Прогресс шагов -->
      <div class="mb-6">
        <div class="flex items-center justify-between">
          <div
            v-for="(step, index) in steps"
            :key="index"
            class="flex items-center flex-1"
          >
            <div class="flex items-center">
              <div
                :class="[
                  'w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold',
                  currentStep > index
                    ? 'bg-sky-600 text-white'
                    : currentStep === index
                    ? 'bg-sky-500 text-white ring-2 ring-sky-400'
                    : 'bg-neutral-800 text-neutral-400'
                ]"
              >
                <span v-if="currentStep > index">✓</span>
                <span v-else>{{ index + 1 }}</span>
              </div>
              <span
                :class="[
                  'ml-2 text-xs',
                  currentStep >= index ? 'text-neutral-200' : 'text-neutral-500'
                ]"
              >
                {{ step.title }}
              </span>
            </div>
            <div
              v-if="index < steps.length - 1"
              :class="[
                'flex-1 h-0.5 mx-2',
                currentStep > index ? 'bg-sky-600' : 'bg-neutral-800'
              ]"
            />
          </div>
        </div>
      </div>

      <Card>
        <!-- Шаг 1: Теплица и Зона -->
        <div v-if="currentStep === 0" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Теплица и Зона</h2>
            
            <!-- Выбор теплицы -->
            <div class="mb-6">
              <label class="block text-sm font-medium mb-2">Теплица</label>
              <div class="flex gap-2 mb-3">
                <Button
                  size="sm"
                  :variant="greenhouseMode === 'select' ? 'primary' : 'secondary'"
                  @click="greenhouseMode = 'select'"
                >
                  Выбрать существующую
                </Button>
                <Button
                  size="sm"
                  :variant="greenhouseMode === 'create' ? 'primary' : 'secondary'"
                  @click="greenhouseMode = 'create'"
                >
                  Создать новую
                </Button>
              </div>

              <div v-if="greenhouseMode === 'select'" class="space-y-3">
                <select
                  v-model="selectedGreenhouseId"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                  @change="loadZonesForGreenhouse"
                >
                  <option :value="null">Выберите теплицу</option>
                  <option
                    v-for="gh in wizardData.greenhouses"
                    :key="gh.id"
                    :value="gh.id"
                  >
                    {{ gh.name }} ({{ gh.uid }})
                  </option>
                </select>
              </div>

              <div v-else class="space-y-3">
                <input
                  v-model="newGreenhouse.name"
                  type="text"
                  placeholder="Название теплицы"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                />
                <Button size="sm" @click="createGreenhouse" :disabled="!newGreenhouse.name.trim() || loading.createGreenhouse">
                  {{ loading.createGreenhouse ? 'Создание...' : 'Создать' }}
                </Button>
              </div>
            </div>

            <!-- Выбор зоны -->
            <div v-if="selectedGreenhouseId || createdGreenhouseId">
              <label class="block text-sm font-medium mb-2">Зона</label>
              <div class="flex gap-2 mb-3">
                <Button
                  size="sm"
                  :variant="zoneMode === 'select' ? 'primary' : 'secondary'"
                  @click="zoneMode = 'select'"
                >
                  Выбрать существующую
                </Button>
                <Button
                  size="sm"
                  :variant="zoneMode === 'create' ? 'primary' : 'secondary'"
                  @click="zoneMode = 'create'"
                >
                  Создать новую
                </Button>
              </div>

              <div v-if="zoneMode === 'select'" class="space-y-3">
                <select
                  v-model="selectedZoneId"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                  @change="loadZoneData"
                >
                  <option :value="null">Выберите зону</option>
                  <option
                    v-for="zone in availableZones"
                    :key="zone.id"
                    :value="zone.id"
                  >
                    {{ zone.name }} ({{ zone.uid }})
                  </option>
                </select>
              </div>

              <div v-else class="space-y-3">
                <input
                  v-model="newZone.name"
                  type="text"
                  placeholder="Название зоны"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                />
                <Button size="sm" @click="createZone" :disabled="!newZone.name.trim() || loading.createZone">
                  {{ loading.createZone ? 'Создание...' : 'Создать' }}
                </Button>
              </div>
            </div>
          </div>

          <div class="flex justify-end">
            <Button
              @click="nextStep"
              :disabled="!selectedZoneId && !createdZoneId"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 2: Инфраструктура зоны -->
        <div v-if="currentStep === 1" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Схема оборудования</h2>
            <p class="text-sm text-neutral-400 mb-4">
              Укажите, какое оборудование установлено в зоне
            </p>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div
                v-for="asset in infrastructureAssets"
                :key="asset.type"
                class="p-3 rounded border"
                :class="
                  asset.required
                    ? selectedInfrastructure.includes(asset.type)
                      ? 'border-sky-600 bg-sky-900/20'
                      : 'border-red-600 bg-red-900/10'
                    : selectedInfrastructure.includes(asset.type)
                    ? 'border-sky-500 bg-sky-900/10'
                    : 'border-neutral-700 bg-neutral-900'
                "
              >
                <label class="flex items-center cursor-pointer">
                  <input
                    v-model="selectedInfrastructure"
                    type="checkbox"
                    :value="asset.type"
                    class="mr-2"
                  />
                  <div class="flex-1">
                    <div class="text-sm font-medium">{{ asset.label }}</div>
                    <div v-if="asset.required" class="text-xs text-red-400 mt-1">Обязательно</div>
                  </div>
                </label>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="nextStep"
              :disabled="!hasRequiredInfrastructure"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 3: Привязка каналов -->
        <div v-if="currentStep === 2" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Привязка каналов</h2>
            <p class="text-sm text-neutral-400 mb-4">
              Выберите ноды и назначьте роли каналам
            </p>

            <div v-if="zoneData" class="space-y-4">
              <div
                v-for="node in zoneData.nodes"
                :key="node.id"
                class="p-4 rounded border border-neutral-700 bg-neutral-900"
              >
                <div class="flex items-center justify-between mb-3">
                  <div>
                    <div class="font-medium">{{ node.name }} ({{ node.uid }})</div>
                    <div class="text-xs text-neutral-400">{{ node.type }}</div>
                  </div>
                  <Badge
                    :variant="node.is_online ? 'success' : 'danger'"
                    size="sm"
                  >
                    {{ node.is_online ? 'Online' : 'Offline' }}
                  </Badge>
                </div>

                <div v-if="node.channels.length > 0" class="space-y-2">
                  <div
                    v-for="channel in node.channels"
                    :key="channel.id"
                    class="flex items-center gap-2"
                  >
                    <div class="flex-1 text-sm">{{ channel.channel }} ({{ channel.metric }})</div>
                    <select
                      v-model="channelBindings[channel.id]"
                      class="h-8 rounded-md border px-2 text-xs border-neutral-700 bg-neutral-800"
                    >
                      <option :value="null">Не назначено</option>
                      <option
                        v-for="role in availableRoles"
                        :key="role.value"
                        :value="role.value"
                      >
                        {{ role.label }}
                      </option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button @click="nextStep">Далее</Button>
          </div>
        </div>

        <!-- Шаг 4: Растение -->
        <div v-if="currentStep === 3" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Растение</h2>

            <div class="mb-4">
              <label class="block text-sm font-medium mb-2">Выберите растение</label>
              <div class="flex gap-2 mb-3">
                <Button
                  size="sm"
                  :variant="plantMode === 'select' ? 'primary' : 'secondary'"
                  @click="plantMode = 'select'"
                >
                  Из каталога
                </Button>
                <Button
                  size="sm"
                  :variant="plantMode === 'create' ? 'primary' : 'secondary'"
                  @click="plantMode = 'create'"
                >
                  Создать новое
                </Button>
              </div>

              <div v-if="plantMode === 'select'">
                <select
                  v-model="selectedPlantId"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                  @change="onPlantSelected"
                >
                  <option :value="null">Выберите растение</option>
                  <option
                    v-for="plant in wizardData.plants"
                    :key="plant.id"
                    :value="plant.id"
                  >
                    {{ plant.name }} {{ plant.variety ? `(${plant.variety})` : '' }}
                  </option>
                </select>
              </div>
            </div>

            <!-- Партия -->
            <div v-if="selectedPlantId" class="space-y-4">
              <h3 class="text-sm font-semibold">Партия</h3>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="block text-xs text-neutral-400 mb-1">Количество</label>
                  <input
                    v-model.number="batch.quantity"
                    type="number"
                    placeholder="Количество растений"
                    class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                  />
                </div>
                <div>
                  <label class="block text-xs text-neutral-400 mb-1">Плотность (шт/м²)</label>
                  <input
                    v-model.number="batch.density"
                    type="number"
                    step="0.1"
                    placeholder="Плотность"
                    class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                  />
                </div>
                <div>
                  <label class="block text-xs text-neutral-400 mb-1">Субстрат</label>
                  <input
                    v-model="batch.substrate"
                    type="text"
                    placeholder="Тип субстрата"
                    class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                  />
                </div>
                <div>
                  <label class="block text-xs text-neutral-400 mb-1">Система</label>
                  <input
                    v-model="batch.system"
                    type="text"
                    placeholder="Система выращивания"
                    class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                  />
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="nextStep"
              :disabled="!selectedPlantId"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 5: Рецепт -->
        <div v-if="currentStep === 4" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Рецепт выращивания</h2>

            <div class="mb-4">
              <label class="block text-sm font-medium mb-2">Выберите рецепт</label>
              <select
                v-model="selectedRecipeId"
                class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                @change="onRecipeSelected"
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
            </div>

            <!-- Маппинг фаз (по умолчанию авто) -->
            <div v-if="selectedRecipeId && selectedRecipe" class="mt-4">
              <h3 class="text-sm font-semibold mb-2">Фазы рецепта</h3>
              <div class="space-y-2">
                <div
                  v-for="(phase, index) in selectedRecipe.phases"
                  :key="phase.id"
                  :data-testid="`cycle-phase-${index}`"
                  class="p-2 rounded border border-neutral-700 bg-neutral-900 text-sm"
                >
                  <div class="flex justify-between">
                    <span>{{ phase.name }}</span>
                    <span class="text-neutral-400">{{ phase.duration_hours }}ч</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="nextStep"
              :disabled="!selectedRecipeId"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 6: Старт -->
        <div v-if="currentStep === 5" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Старт цикла</h2>

            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium mb-2">Дата посадки</label>
                <input
                  v-model="plantingDate"
                  type="datetime-local"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                />
              </div>

              <div>
                <label class="block text-sm font-medium mb-2">Дата старта автоматики</label>
                <input
                  v-model="automationStartDate"
                  type="datetime-local"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                />
                <p class="text-xs text-neutral-400 mt-1">
                  Может совпадать с датой посадки или быть позже
                </p>
              </div>

              <div>
                <label class="block text-sm font-medium mb-2">Прогноз сбора</label>
                <input
                  v-model="estimatedHarvestDate"
                  type="datetime-local"
                  class="h-9 w-full rounded-md border px-2 text-sm border-neutral-700 bg-neutral-900"
                />
                <p class="text-xs text-neutral-400 mt-1">
                  Автоматически рассчитано на основе длительности фаз рецепта
                </p>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="nextStep"
              :disabled="!plantingDate || !automationStartDate"
            >
              Далее
            </Button>
          </div>
        </div>

        <!-- Шаг 7: Подтверждение -->
        <div v-if="currentStep === 6" class="space-y-6">
          <div>
            <h2 class="text-lg font-semibold mb-4">Проверка готовности</h2>

            <div v-if="zoneReadiness" class="space-y-4">
              <!-- Проверки готовности -->
              <div class="space-y-2">
                <div
                  v-for="check in readinessChecks"
                  :key="check.key"
                  class="flex items-center gap-2"
                >
                  <span
                    :class="[
                      'text-lg',
                      check.passed ? 'text-green-400' : 'text-red-400'
                    ]"
                  >
                    {{ check.passed ? '✓' : '✗' }}
                  </span>
                  <span class="text-sm">{{ check.label }}</span>
                </div>
              </div>

              <!-- Сводка -->
              <div class="p-4 rounded border border-neutral-700 bg-neutral-900">
                <h3 class="text-sm font-semibold mb-2">Сводка</h3>
                <div class="space-y-1 text-sm">
                  <div>Зона: {{ selectedZone?.name }}</div>
                  <div>Растение: {{ selectedPlant?.name }}</div>
                  <div>Рецепт: {{ selectedRecipe?.name }}</div>
                  <div>Посадка: {{ formatDate(plantingDate) }}</div>
                  <div>Старт автоматики: {{ formatDate(automationStartDate) }}</div>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-between">
            <Button variant="secondary" @click="prevStep">Назад</Button>
            <Button
              @click="createGrowCycle"
              :disabled="!zoneReadiness?.ready || loading.createCycle"
            >
              {{ loading.createCycle ? 'Создание...' : 'Запустить цикл' }}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { logger } from '@/utils/logger'

const { showToast } = useToast()
const { api } = useApi(showToast)

const steps = [
  { title: 'Теплица/Зона' },
  { title: 'Инфраструктура' },
  { title: 'Каналы' },
  { title: 'Растение' },
  { title: 'Рецепт' },
  { title: 'Старт' },
  { title: 'Подтверждение' },
]

const currentStep = ref(0)
const greenhouseMode = ref<'select' | 'create'>('select')
const zoneMode = ref<'select' | 'create'>('select')
const plantMode = ref<'select' | 'create'>('select')

const wizardData = reactive({
  greenhouses: [] as any[],
  zones: [] as any[],
  plants: [] as any[],
  recipes: [] as any[],
})

const selectedGreenhouseId = ref<number | null>(null)
const createdGreenhouseId = ref<number | null>(null)
const availableZones = ref<any[]>([])
const selectedZoneId = ref<number | null>(null)
const createdZoneId = ref<number | null>(null)
const zoneData = ref<any>(null)
const zoneReadiness = ref<any>(null)

const newGreenhouse = reactive({ name: '' })
const newZone = reactive({ name: '' })

const selectedInfrastructure = ref<string[]>([])
const infrastructureAssets = [
  { type: 'main_pump', label: 'Помпа', required: true, icon: '💧' },
  { type: 'tank_clean', label: 'Бак чистой воды', required: true, icon: '🪣' },
  { type: 'tank_nutrient', label: 'Бак раствора', required: true, icon: '🧪' },
  { type: 'drain', label: 'Дренаж', required: true, icon: '🚰' },
  { type: 'light', label: 'Свет', required: false, icon: '💡' },
  { type: 'vent', label: 'Вентиляция', required: false, icon: '🌬️' },
  { type: 'heater', label: 'Отопление', required: false, icon: '🔥' },
  { type: 'mist', label: 'Туман', required: false, icon: '🌫️' },
]

const channelBindings = reactive<Record<number, string | null>>({})
const availableRoles = [
  { value: 'main_pump', label: 'Основная помпа' },
  { value: 'drain', label: 'Дренаж' },
  { value: 'mist', label: 'Туман' },
  { value: 'light', label: 'Свет' },
  { value: 'vent', label: 'Вентиляция' },
  { value: 'heater', label: 'Отопление' },
]

const selectedPlantId = ref<number | null>(null)
const batch = reactive({
  quantity: null as number | null,
  density: null as number | null,
  substrate: '',
  system: '',
})

const selectedRecipeId = ref<number | null>(null)

const plantingDate = ref('')
const automationStartDate = ref('')
const estimatedHarvestDate = ref('')

const loading = reactive({
  wizardData: false,
  createGreenhouse: false,
  createZone: false,
  zoneData: false,
  createCycle: false,
})

// Computed
const hasRequiredInfrastructure = computed(() => {
  const required = infrastructureAssets.filter(a => a.required).map(a => a.type)
  return required.every(type => selectedInfrastructure.value.includes(type))
})

const selectedZone = computed(() => {
  if (selectedZoneId.value) {
    return wizardData.zones.find(z => z.id === selectedZoneId.value)
  }
  return null
})

const selectedPlant = computed(() => {
  if (selectedPlantId.value) {
    return wizardData.plants.find(p => p.id === selectedPlantId.value)
  }
  return null
})

const selectedRecipe = computed(() => {
  if (selectedRecipeId.value) {
    return wizardData.recipes.find(r => r.id === selectedRecipeId.value)
  }
  return null
})

const availableRecipes = computed(() => {
  if (selectedPlant.value?.recommended_recipes) {
    const recommendedIds = selectedPlant.value.recommended_recipes.map((r: any) => r.id || r)
    return wizardData.recipes.filter(r => recommendedIds.includes(r.id))
  }
  return wizardData.recipes
})

const readinessChecks = computed(() => {
  if (!zoneReadiness.value) return []
  return [
    { key: 'main_pump', label: 'Основная помпа', passed: zoneReadiness.value.checks?.main_pump },
    { key: 'drain', label: 'Дренаж', passed: zoneReadiness.value.checks?.drain },
    { key: 'online_nodes', label: 'Онлайн ноды', passed: zoneReadiness.value.checks?.online_nodes },
  ]
})

// Methods
onMounted(async () => {
  await loadWizardData()
  setDefaultDates()
})

function setDefaultDates() {
  const now = new Date()
  now.setMinutes(0, 0, 0)
  plantingDate.value = now.toISOString().slice(0, 16)
  automationStartDate.value = now.toISOString().slice(0, 16)
}

async function loadWizardData() {
  loading.wizardData = true
  try {
    const response = await api.get('/grow-cycle-wizard/data')
    if (response.data?.status === 'ok') {
      Object.assign(wizardData, response.data.data)
    }
  } catch (error) {
    logger.error('Failed to load wizard data:', error)
  } finally {
    loading.wizardData = false
  }
}

async function loadZonesForGreenhouse() {
  if (!selectedGreenhouseId.value) return
  const greenhouse = wizardData.greenhouses.find(gh => gh.id === selectedGreenhouseId.value)
  if (greenhouse) {
    availableZones.value = greenhouse.zones || []
  }
}

async function loadZoneData() {
  if (!selectedZoneId.value) return
  loading.zoneData = true
  try {
    const response = await api.get(`/grow-cycle-wizard/zone/${selectedZoneId.value}`)
    if (response.data?.status === 'ok') {
      zoneData.value = response.data.data
      zoneReadiness.value = response.data.data.readiness
      
      // Инициализируем channelBindings
      if (zoneData.value.nodes) {
        zoneData.value.nodes.forEach((node: any) => {
          node.channels.forEach((channel: any) => {
            channelBindings[channel.id] = null
          })
        })
      }
    }
  } catch (error) {
    logger.error('Failed to load zone data:', error)
  } finally {
    loading.zoneData = false
  }
}

async function createGreenhouse() {
  if (!newGreenhouse.name.trim()) return
  loading.createGreenhouse = true
  try {
    const response = await api.post('/greenhouses', { name: newGreenhouse.name })
    if (response.data?.status === 'ok' || response.data?.id) {
      createdGreenhouseId.value = response.data.id || response.data.data?.id
      selectedGreenhouseId.value = createdGreenhouseId.value
      await loadWizardData()
      await loadZonesForGreenhouse()
      showToast('Теплица создана', 'success')
    }
  } catch (error) {
    logger.error('Failed to create greenhouse:', error)
  } finally {
    loading.createGreenhouse = false
  }
}

async function createZone() {
  if (!newZone.name.trim() || !selectedGreenhouseId.value) return
  loading.createZone = true
  try {
    const response = await api.post('/zones', {
      name: newZone.name,
      greenhouse_id: selectedGreenhouseId.value,
    })
    if (response.data?.status === 'ok' || response.data?.id) {
      createdZoneId.value = response.data.id || response.data.data?.id
      selectedZoneId.value = createdZoneId.value
      await loadWizardData()
      await loadZoneData()
      showToast('Зона создана', 'success')
    }
  } catch (error) {
    logger.error('Failed to create zone:', error)
  } finally {
    loading.createZone = false
  }
}

function onPlantSelected() {
  if (selectedPlant.value?.recommended_recipes && selectedPlant.value.recommended_recipes.length > 0) {
    const firstRecommended = selectedPlant.value.recommended_recipes[0]
    selectedRecipeId.value = firstRecommended.id || firstRecommended
    onRecipeSelected()
  }
}

function onRecipeSelected() {
  if (selectedRecipe.value) {
    // Рассчитываем прогноз сбора
    const totalHours = selectedRecipe.value.phases.reduce((sum: number, phase: any) => sum + (phase.duration_hours || 0), 0)
    const planting = new Date(plantingDate.value)
    const harvest = new Date(planting.getTime() + totalHours * 60 * 60 * 1000)
    estimatedHarvestDate.value = harvest.toISOString().slice(0, 16)
  }
}

function nextStep() {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++
    
    // При переходе на шаг 2, загружаем данные зоны
    if (currentStep.value === 2 && selectedZoneId.value && !zoneData.value) {
      loadZoneData()
    }
    
    // При переходе на шаг 6, пересчитываем готовность
    if (currentStep.value === 6 && selectedZoneId.value) {
      loadZoneData()
    }
  }
}

function prevStep() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

async function createGrowCycle() {
  if (!selectedZoneId.value || !selectedPlantId.value || !selectedRecipeId.value) {
    showToast('Заполните все обязательные поля', 'error')
    return
  }

  // Формируем channel bindings
  const bindings = Object.entries(channelBindings)
    .filter(([_, role]) => role !== null)
    .map(([channelId, role]) => {
      // Находим канал и ноду
      let nodeId = null
      if (zoneData.value?.nodes) {
        for (const node of zoneData.value.nodes) {
          const channel = node.channels.find((c: any) => c.id === Number(channelId))
          if (channel) {
            nodeId = node.id
            break
          }
        }
      }
      return {
        node_id: nodeId,
        channel_id: Number(channelId),
        role: role,
      }
    })
    .filter(b => b.node_id !== null)

  loading.createCycle = true
  try {
    const response = await api.post('/grow-cycle-wizard/create', {
      zone_id: selectedZoneId.value,
      plant_id: selectedPlantId.value,
      recipe_id: selectedRecipeId.value,
      planting_date: new Date(plantingDate.value).toISOString(),
      automation_start_date: new Date(automationStartDate.value).toISOString(),
      batch: batch,
      channel_bindings: bindings,
    })

    if (response.data?.status === 'ok') {
      showToast('Цикл выращивания успешно создан!', 'success')
      router.visit(`/zones/${selectedZoneId.value}`)
    }
  } catch (error: any) {
    logger.error('Failed to create grow cycle:', error)
    showToast(error.response?.data?.message || 'Ошибка при создании цикла', 'error')
  } finally {
    loading.createCycle = false
  }
}

function formatDate(dateString: string) {
  if (!dateString) return ''
  const date = new Date(dateString)
  return date.toLocaleString('ru-RU')
}

// Watchers
watch(selectedZoneId, (newId) => {
  if (newId) {
    loadZoneData()
  }
})

watch(plantingDate, () => {
  if (selectedRecipe.value) {
    onRecipeSelected()
  }
})
</script>

