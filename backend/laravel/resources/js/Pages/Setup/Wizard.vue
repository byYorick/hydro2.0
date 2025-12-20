<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Мастер настройки системы</h1>
    
    <Card>
      <div class="space-y-6">
        <!-- Шаг 1: Выбор/Создание теплицы -->
        <div class="border-l-4 border-[color:var(--accent-green)] pl-4">
          <div class="flex items-center justify-between mb-2">
            <h2 class="text-base font-semibold">Шаг 1: Выбрать или создать теплицу</h2>
            <Badge v-if="step1Complete" variant="success">Готово</Badge>
          </div>
          <div v-if="!step1Complete" class="space-y-3">
            <!-- Переключатель режима -->
            <div class="flex gap-2 mb-2">
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

            <!-- Выбор существующей теплицы -->
            <div v-if="greenhouseMode === 'select'" class="space-y-3">
              <div v-if="loading.greenhouses" class="text-sm text-[color:var(--text-dim)]">Загрузка...</div>
              <div v-else-if="availableGreenhouses.length === 0" class="text-sm text-[color:var(--text-dim)]">
                Нет доступных теплиц. Создайте новую.
              </div>
              <select
                v-else
                v-model="selectedGreenhouseId"
                class="input-select w-full"
              >
                <option :value="null">Выберите теплицу</option>
                <option
                  v-for="gh in availableGreenhouses"
                  :key="gh.id"
                  :value="gh.id"
                >
                  {{ gh.name }} ({{ gh.uid }})
                </option>
              </select>
              <Button
                size="sm"
                @click="selectGreenhouse"
                :disabled="!selectedGreenhouseId || loading.step1"
              >
                {{ loading.step1 ? 'Загрузка...' : 'Выбрать' }}
              </Button>
            </div>

            <!-- Создание новой теплицы -->
            <div v-else class="space-y-3">
              <div>
                <input
                  v-model="greenhouseForm.name"
                  type="text"
                  placeholder="Название теплицы"
                  class="input-field w-full"
                />
                <div class="text-xs text-[color:var(--text-dim)] mt-1">
                  UID будет сгенерирован автоматически: <span class="text-[color:var(--text-muted)]">{{ generatedUid }}</span>
                </div>
              </div>
              <Button size="sm" @click="createGreenhouse" :disabled="loading.step1 || !greenhouseForm.name.trim()">
                {{ loading.step1 ? 'Создание...' : 'Создать теплицу' }}
              </Button>
            </div>
          </div>
          <div v-else class="text-sm text-[color:var(--text-muted)]">
            Теплица: <span class="font-semibold">{{ createdGreenhouse?.name }}</span>
          </div>
        </div>

        <!-- Шаг 2: Создание рецепта -->
        <div class="border-l-4 pl-4" :class="step1Complete ? 'border-[color:var(--accent-green)]' : 'border-[color:var(--border-muted)]'">
          <div class="flex items-center justify-between mb-2">
            <h2 class="text-base font-semibold">Шаг 2: Создать рецепт с фазами</h2>
            <Badge v-if="step2Complete" variant="success">Готово</Badge>
          </div>
          <div v-if="!step2Complete" class="space-y-3">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <input
                v-model="recipeForm.name"
                type="text"
                placeholder="Название рецепта"
                class="input-field"
              />
              <input
                v-model="recipeForm.description"
                type="text"
                placeholder="Описание"
                class="input-field"
              />
            </div>
            
            <div class="space-y-2">
              <div class="text-xs text-[color:var(--text-muted)]">Фазы рецепта:</div>
              <div
                v-for="(phase, index) in recipeForm.phases"
                :key="index"
                class="p-3 rounded border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)]"
              >
                <div class="grid grid-cols-1 md:grid-cols-4 gap-2 mb-2">
                  <input
                    v-model="phase.name"
                    type="text"
                    placeholder="Название фазы"
                    class="input-field h-8 text-xs"
                  />
                  <input
                    v-model.number="phase.duration_hours"
                    type="number"
                    placeholder="Часов"
                    class="input-field h-8 text-xs"
                  />
                  <input
                    v-model.number="phase.targets.ph"
                    type="number"
                    step="0.1"
                    placeholder="pH"
                    class="input-field h-8 text-xs"
                  />
                  <input
                    v-model.number="phase.targets.ec"
                    type="number"
                    step="0.1"
                    placeholder="EC"
                    class="input-field h-8 text-xs"
                  />
                </div>
                <div class="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <input
                    v-model.number="phase.targets.temp_air"
                    type="number"
                    placeholder="Температура"
                    class="input-field h-8 text-xs"
                  />
                  <input
                    v-model.number="phase.targets.humidity_air"
                    type="number"
                    placeholder="Влажность"
                    class="input-field h-8 text-xs"
                  />
                  <input
                    v-model.number="phase.targets.light_hours"
                    type="number"
                    placeholder="Свет (часов)"
                    class="input-field h-8 text-xs"
                  />
                </div>
              </div>
              <Button size="sm" variant="secondary" @click="addPhase">Добавить фазу</Button>
            </div>
            
            <Button
              size="sm"
              @click="createRecipe"
              :disabled="loading.step2 || !step1Complete"
            >
              {{ loading.step2 ? 'Создание...' : 'Создать рецепт' }}
            </Button>
          </div>
          <div v-else class="text-sm text-[color:var(--text-muted)]">
            Рецепт: <span class="font-semibold">{{ createdRecipe?.name }}</span>
            ({{ createdRecipe?.phases?.length || 0 }} фаз)
          </div>
        </div>

        <!-- Шаг 3: Выбор/Создание зоны -->
        <div class="border-l-4 pl-4" :class="step2Complete ? 'border-[color:var(--accent-green)]' : 'border-[color:var(--border-muted)]'">
          <div class="flex items-center justify-between mb-2">
            <h2 class="text-base font-semibold">Шаг 3: Выбрать или создать зону</h2>
            <Badge v-if="step3Complete" variant="success">Готово</Badge>
          </div>
          <div v-if="!step3Complete" class="space-y-3">
            <!-- Переключатель режима -->
            <div class="flex gap-2 mb-2">
              <Button
                size="sm"
                :variant="zoneMode === 'select' ? 'primary' : 'secondary'"
                @click="zoneMode = 'select'"
                :disabled="!step2Complete"
              >
                Выбрать существующую
              </Button>
              <Button
                size="sm"
                :variant="zoneMode === 'create' ? 'primary' : 'secondary'"
                @click="zoneMode = 'create'"
                :disabled="!step2Complete"
              >
                Создать новую
              </Button>
            </div>

            <!-- Выбор существующей зоны -->
            <div v-if="zoneMode === 'select'" class="space-y-3">
              <div v-if="loading.zones" class="text-sm text-[color:var(--text-dim)]">Загрузка...</div>
              <div v-else-if="availableZones.length === 0" class="text-sm text-[color:var(--text-dim)]">
                Нет доступных зон в этой теплице. Создайте новую.
              </div>
              <select
                v-else
                v-model="selectedZoneId"
                class="input-select w-full"
              >
                <option :value="null">Выберите зону</option>
                <option
                  v-for="zone in availableZones"
                  :key="zone.id"
                  :value="zone.id"
                >
                  {{ zone.name }} ({{ zone.status }})
                  <span v-if="zone.greenhouse"> — {{ zone.greenhouse.name }}</span>
                </option>
              </select>
              <Button
                size="sm"
                @click="selectZone"
                :disabled="!selectedZoneId || loading.step3 || !step2Complete"
              >
                {{ loading.step3 ? 'Загрузка...' : 'Выбрать' }}
              </Button>
            </div>

            <!-- Создание новой зоны -->
            <div v-else class="space-y-3">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <input
                  v-model="zoneForm.name"
                  type="text"
                  placeholder="Название зоны"
                  class="input-field"
                />
                <input
                  v-model="zoneForm.description"
                  type="text"
                  placeholder="Описание"
                  class="input-field"
                />
              </div>
              <Button
                size="sm"
                @click="createZone"
                :disabled="loading.step3 || !step2Complete"
              >
                {{ loading.step3 ? 'Создание...' : 'Создать зону' }}
              </Button>
            </div>
          </div>
          <div v-else class="text-sm text-[color:var(--text-muted)]">
            Зона: <span class="font-semibold">{{ createdZone?.name }}</span>
          </div>
        </div>

        <!-- Шаг 4: Привязка рецепта к зоне -->
        <div class="border-l-4 pl-4" :class="step3Complete ? 'border-[color:var(--accent-green)]' : 'border-[color:var(--border-muted)]'">
          <div class="flex items-center justify-between mb-2">
            <h2 class="text-base font-semibold">Шаг 4: Привязать рецепт к зоне</h2>
            <Badge v-if="step4Complete" variant="success">Готово</Badge>
          </div>
          <div v-if="!step4Complete">
            <Button
              size="sm"
              @click="attachRecipeToZone"
              :disabled="loading.step4 || !step3Complete"
            >
              {{ loading.step4 ? 'Привязка...' : 'Привязать рецепт к зоне' }}
            </Button>
          </div>
          <div v-else class="text-sm text-[color:var(--text-muted)]">
            Рецепт успешно привязан к зоне
          </div>
        </div>

        <!-- Шаг 5: Привязка узлов -->
        <div class="border-l-4 pl-4" :class="step4Complete ? 'border-[color:var(--accent-green)]' : 'border-[color:var(--border-muted)]'">
          <div class="flex items-center justify-between mb-2">
            <h2 class="text-base font-semibold">Шаг 5: Привязать узлы к зоне</h2>
            <Badge v-if="step5Complete" variant="success">Готово</Badge>
          </div>
          <div v-if="!step5Complete" class="space-y-3">
            <div v-if="availableNodes.length > 0" class="space-y-2 max-h-[200px] overflow-y-auto">
              <label
                v-for="node in availableNodes"
                :key="node.id"
                class="flex items-center gap-2 p-2 rounded border border-[color:var(--border-muted)] hover:border-[color:var(--border-strong)] cursor-pointer"
              >
                <input
                  type="checkbox"
                  :value="node.id"
                  v-model="selectedNodeIds"
                  class="rounded"
                />
                <div class="flex-1 text-sm">
                  {{ node.uid || node.name || `Node ${node.id}` }} — {{ node.type || 'unknown' }}
                </div>
              </label>
            </div>
            <div v-else class="text-sm text-[color:var(--text-dim)]">
              Нет доступных узлов для привязки. Узлы будут доступны после регистрации через MQTT.
            </div>
            <Button
              size="sm"
              @click="loadAvailableNodes"
              :disabled="loading.nodes"
            >
              {{ loading.nodes ? 'Загрузка...' : 'Обновить список узлов' }}
            </Button>
            <Button
              size="sm"
              @click="attachNodesToZone"
              :disabled="loading.step5 || selectedNodeIds.length === 0 || !step4Complete"
            >
              {{ loading.step5 ? 'Привязка...' : `Привязать узлы (${selectedNodeIds.length})` }}
            </Button>
          </div>
          <div v-else class="text-sm text-[color:var(--text-muted)]">
            Привязано узлов: {{ attachedNodesCount }}
          </div>
        </div>

        <!-- Завершение -->
        <div v-if="step5Complete" class="pt-4 border-t border-[color:var(--border-muted)]">
          <div class="text-center space-y-3">
            <div class="text-lg font-semibold text-[color:var(--accent-green)]">Система настроена!</div>
            <div class="text-sm text-[color:var(--text-muted)]">
              Зона создана, рецепт привязан, узлы настроены. Система готова к работе.
            </div>
            <div class="flex justify-center gap-2">
              <Link :href="`/zones/${createdZone?.id}`">
                <Button size="sm">Открыть зону</Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </Card>
  </AppLayout>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { Link } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import Badge from '@/Components/Badge.vue'
import { useApi } from '@/composables/useApi'
import { useToast } from '@/composables/useToast'
import { TOAST_TIMEOUT } from '@/constants/timeouts'
import { extractData } from '@/utils/apiHelpers'
import { logger } from '@/utils/logger'
import { generateUid } from '@/utils/transliterate'
import { router } from '@inertiajs/vue3'

const { showToast } = useToast()
const { api } = useApi(showToast)

interface Greenhouse {
  id: number
  uid: string
  name: string
}

interface Recipe {
  id: number
  name: string
  phases?: Array<{
    id: number
    phase_index: number
    name: string
    duration_hours: number
    targets: any
  }>
}

interface Zone {
  id: number
  name: string
  status?: string
  greenhouse?: {
    id: number
    name: string
  }
}

interface Node {
  id: number
  uid: string
  name?: string
  type?: string
}

const greenhouseForm = reactive({
  name: '',
  timezone: 'Europe/Moscow',
  type: 'indoor',
  description: ''
})

const recipeForm = reactive({
  name: 'Lettuce NFT Recipe',
  description: 'Standard NFT recipe for lettuce',
  phases: [
    {
      phase_index: 0,
      name: 'Seedling',
      duration_hours: 168,
      targets: {
        ph: 5.8,
        ec: 1.2,
        temp_air: 22,
        humidity_air: 65,
        light_hours: 18,
        irrigation_interval_sec: 900,
        irrigation_duration_sec: 10
      }
    },
    {
      phase_index: 1,
      name: 'Vegetative',
      duration_hours: 336,
      targets: {
        ph: 5.8,
        ec: 1.4,
        temp_air: 23,
        humidity_air: 60,
        light_hours: 16,
        irrigation_interval_sec: 720,
        irrigation_duration_sec: 12
      }
    }
  ]
})

const zoneForm = reactive({
  name: 'Zone A',
  description: 'Main cultivation zone',
  status: 'RUNNING'
})

const loading = reactive({
  step1: false,
  step2: false,
  step3: false,
  step4: false,
  step5: false,
  nodes: false,
  greenhouses: false,
  zones: false
})

const greenhouseMode = ref<'select' | 'create'>('select')
const zoneMode = ref<'select' | 'create'>('create')
const availableGreenhouses = ref<Greenhouse[]>([])
const availableZones = ref<Zone[]>([])
const selectedGreenhouseId = ref<number | null>(null)
const selectedZoneId = ref<number | null>(null)

const createdGreenhouse = ref<Greenhouse | null>(null)
const createdRecipe = ref<Recipe | null>(null)
const createdZone = ref<Zone | null>(null)
const availableNodes = ref<Node[]>([])
const selectedNodeIds = ref<number[]>([])
const attachedNodesCount = ref(0)

const step1Complete = computed(() => createdGreenhouse.value !== null)
const step2Complete = computed(() => createdRecipe.value !== null)
const step3Complete = computed(() => createdZone.value !== null)
const step4Complete = computed(() => createdZone.value !== null && createdRecipe.value !== null)
const step5Complete = computed(() => attachedNodesCount.value > 0)

// Вычисляемый UID на основе названия
const generatedUid = computed(() => {
  if (!greenhouseForm.name || !greenhouseForm.name.trim()) {
    return 'gh-...'
  }
  return generateUid(greenhouseForm.name, 'gh-')
})

onMounted(() => {
  loadAvailableNodes()
  loadAvailableGreenhouses()
})

watch(() => createdGreenhouse.value?.id, (greenhouseId) => {
  if (greenhouseId) {
    loadAvailableZones(greenhouseId)
  }
})

async function loadAvailableGreenhouses(): Promise<void> {
  loading.greenhouses = true
  try {
    const response = await api.get<{ data?: Greenhouse[] } | Greenhouse[]>('/greenhouses')
    
    const data = extractData<Greenhouse[]>(response.data) || []
    if (Array.isArray(data)) {
      availableGreenhouses.value = data
    } else {
      availableGreenhouses.value = []
    }
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to load greenhouses:', error)
    availableGreenhouses.value = []
  } finally {
    loading.greenhouses = false
  }
}

async function loadAvailableZones(greenhouseId?: number) {
  if (!greenhouseId && !createdGreenhouse.value?.id) return
  
  loading.zones = true
  try {
    const ghId = greenhouseId || createdGreenhouse.value!.id
    const response = await api.get<{ data?: Zone[] } | Zone[]>(
      '/zones',
      { params: { greenhouse_id: ghId } }
    )
    
    const data = response.data?.data
    if (data?.data && Array.isArray(data.data)) {
      availableZones.value = data.data
    } else if (Array.isArray(data)) {
      availableZones.value = data
    } else {
      availableZones.value = []
    }
  } catch (error) {
    logger.error('Failed to load zones:', error)
    availableZones.value = []
  } finally {
    loading.zones = false
  }
}

async function selectGreenhouse(): Promise<void> {
  if (!selectedGreenhouseId.value) return
  
  loading.step1 = true
  try {
    const response = await api.get<{ data?: Greenhouse } | Greenhouse>(
      `/greenhouses/${selectedGreenhouseId.value}`
    )
    
    createdGreenhouse.value = extractData<Greenhouse>(response.data) || createdGreenhouse.value
    logger.info('Greenhouse selected:', createdGreenhouse.value)
    
    // Загружаем зоны для выбранной теплицы
    await loadAvailableZones(createdGreenhouse.value.id)
  } catch (error: any) {
    logger.error('Failed to select greenhouse:', error)
  } finally {
    loading.step1 = false
  }
}

async function selectZone() {
  if (!selectedZoneId.value) return
  
  loading.step3 = true
  try {
    const response = await api.get<{ data?: Zone } | Zone>(
      `/zones/${selectedZoneId.value}`
    )
    
    createdZone.value = extractData<Zone>(response.data) || createdZone.value
    logger.info('Zone selected:', createdZone.value)
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to select zone:', error)
  } finally {
    loading.step3 = false
  }
}

async function createGreenhouse(): Promise<void> {
  if (!greenhouseForm.name || !greenhouseForm.name.trim()) {
    showToast('Введите название теплицы', 'error', TOAST_TIMEOUT.NORMAL)
    return
  }

  loading.step1 = true
  try {
    // Генерируем UID автоматически на основе названия
    const uid = generateUid(greenhouseForm.name, 'gh-')
    
    const response = await api.post<{ data?: Greenhouse } | Greenhouse>(
      '/greenhouses',
      {
        ...greenhouseForm,
        uid: uid
      }
    )
    
    createdGreenhouse.value = extractData<Greenhouse>(response.data) || createdGreenhouse.value
    logger.info('Greenhouse created:', createdGreenhouse.value)
    showToast('Теплица успешно создана', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to create greenhouse:', error)
  } finally {
    loading.step1 = false
  }
}

function addPhase() {
  const maxIndex = recipeForm.phases.length > 0
    ? Math.max(...recipeForm.phases.map(p => p.phase_index))
    : -1
  recipeForm.phases.push({
    phase_index: maxIndex + 1,
    name: '',
    duration_hours: 24,
    targets: {
      ph: 6.0,
      ec: 1.5,
      temp_air: 23,
      humidity_air: 60,
      light_hours: 14,
      irrigation_interval_sec: 900,
      irrigation_duration_sec: 10
    }
  })
}

async function createRecipe(): Promise<void> {
  if (!createdGreenhouse.value) return
  
  loading.step2 = true
  try {
    // 1. Создать рецепт
    const recipeResponse = await api.post<{ data?: Recipe } | Recipe>(
      '/recipes',
      {
        name: recipeForm.name,
        description: recipeForm.description
      }
    )
    
    const recipe = (recipeResponse.data as { data?: Recipe })?.data || (recipeResponse.data as Recipe)
    const recipeId = recipe.id
    
    if (!recipeId) {
      throw new Error('Recipe ID not found in response')
    }
    
    // 2. Создать фазы
    for (const phase of recipeForm.phases) {
      await api.post(`/recipes/${recipeId}/phases`, {
        phase_index: phase.phase_index,
        name: phase.name,
        duration_hours: phase.duration_hours,
        targets: phase.targets
      })
    }
    
    // 3. Загрузить полный рецепт с фазами
    const fullRecipeResponse = await api.get<{ data?: Recipe } | Recipe>(
      `/recipes/${recipeId}`
    )
    
    createdRecipe.value = (fullRecipeResponse.data as { data?: Recipe })?.data || (fullRecipeResponse.data as Recipe)
    logger.info('Recipe created:', createdRecipe.value)
    showToast('Рецепт успешно создан', 'success', TOAST_TIMEOUT.NORMAL)
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to create recipe:', error)
  } finally {
    loading.step2 = false
  }
}

async function createZone(): Promise<void> {
  if (!createdGreenhouse.value) return
  
  loading.step3 = true
  try {
    const response = await api.post<{ data?: Zone } | Zone>(
      '/zones',
      {
      ...zoneForm,
      greenhouse_id: createdGreenhouse.value.id
    }, {
      headers: {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
    
    createdZone.value = response.data.data
    logger.info('Zone created:', createdZone.value)
    
    // Обновляем список зон
    await loadAvailableZones(createdGreenhouse.value.id)
  } catch (error: any) {
    logger.error('Failed to create zone:', error)
  } finally {
    loading.step3 = false
  }
}

async function attachRecipeToZone(): Promise<void> {
  if (!createdZone.value || !createdRecipe.value) return
  
  loading.step4 = true
  try {
    await api.post(
      `/zones/${createdZone.value.id}/attach-recipe`,
      {
        recipe_id: createdRecipe.value.id,
        start_at: new Date().toISOString()
      }
    )
    
    logger.info('Recipe attached to zone')
    showToast('Рецепт успешно привязан к зоне', 'success', TOAST_TIMEOUT.NORMAL)
    // Обновляем список узлов после привязки рецепта
    await loadAvailableNodes()
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to attach recipe:', error)
  } finally {
    loading.step4 = false
  }
}

async function loadAvailableNodes() {
  loading.nodes = true
  try {
    const response = await api.get<{ data?: Node[] } | Node[]>(
      '/nodes',
      { params: { unassigned: true } }
    )
    
    const data = extractData<Node[]>(response.data) || []
    // Обрабатываем pagination response
    if (Array.isArray(data)) {
      availableNodes.value = data
    } else {
      availableNodes.value = []
    }
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to load nodes:', error)
  } finally {
    loading.nodes = false
  }
}

async function attachNodesToZone(): Promise<void> {
  if (!createdZone.value || selectedNodeIds.value.length === 0) return
  
  loading.step5 = true
  try {
    const promises = selectedNodeIds.value.map(nodeId =>
      api.patch(`/nodes/${nodeId}`, {
        zone_id: createdZone.value!.id
      })
    )
    
    await Promise.all(promises)
    attachedNodesCount.value = selectedNodeIds.value.length
    logger.info(`Attached ${attachedNodesCount.value} nodes to zone`)
    showToast(`Успешно привязано узлов: ${attachedNodesCount.value}`, 'success', TOAST_TIMEOUT.NORMAL)
  } catch (error) {
    // Ошибка уже обработана в useApi через showToast
    logger.error('Failed to attach nodes:', error)
  } finally {
    loading.step5 = false
  }
}
</script>
