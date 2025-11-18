<template>
  <div>
    <div v-if="open" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-black/70" @click="close"></div>
      <div class="relative mx-auto mt-24 w-full max-w-xl rounded-xl border border-neutral-800 bg-neutral-925 p-3">
        <input 
          v-model="q" 
          ref="inputRef"
          placeholder="Команда или поиск..." 
          class="h-10 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 text-sm"
          @keydown.down.prevent="selectedIndex = Math.min(selectedIndex + 1, filteredResults.length - 1)"
          @keydown.up.prevent="selectedIndex = Math.max(selectedIndex - 1, 0)"
          @keydown.enter.prevent="run(filteredResults[selectedIndex])"
        />
        <div class="mt-2 max-h-72 overflow-y-auto">
          <div 
            v-for="(item, i) in filteredResults" 
            :key="`${item.type}-${item.id || i}`"
            class="px-3 py-2 text-sm hover:bg-neutral-850 cursor-pointer rounded-md flex items-center gap-2"
            :class="{ 'bg-neutral-850': i === selectedIndex }"
            @click="run(item)"
            @mouseenter="selectedIndex = i"
          >
            <span v-if="item.icon" class="text-neutral-400">{{ item.icon }}</span>
            <span v-html="highlightMatch(item.label, q)"></span>
            <span v-if="item.category" class="ml-auto text-xs text-neutral-500">{{ item.category }}</span>
          </div>
          <div v-if="loading" class="px-3 py-2 text-sm text-neutral-400">Загрузка...</div>
          <div v-if="!loading && filteredResults.length === 0 && q" class="px-3 py-2 text-sm text-neutral-400">
            Ничего не найдено
          </div>
        </div>
      </div>
    </div>
    
    <!-- Модальное окно подтверждения -->
    <ConfirmModal
      :open="confirmModal.open"
      :title="confirmModal.title"
      :message="confirmModal.message"
      @close="confirmModal.open = false"
      @confirm="confirmAction"
    />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, computed, watch, nextTick } from 'vue'
import { router } from '@inertiajs/vue3'
import { useApi } from '@/composables/useApi'
import { useCommands } from '@/composables/useCommands'
import ConfirmModal from '@/Components/ConfirmModal.vue'

const open = ref(false)
const q = ref('')
const selectedIndex = ref(0)
const inputRef = ref(null)
const loading = ref(false)

const { api } = useApi()
const { sendZoneCommand } = useCommands()

// Модальное окно подтверждения
const confirmModal = ref({
  open: false,
  title: '',
  message: '',
  action: null
})

// Статические команды навигации
const staticCommands = [
  { type: 'nav', label: 'Открыть Zones', icon: '📁', action: () => router.visit('/zones') },
  { type: 'nav', label: 'Открыть Devices', icon: '📱', action: () => router.visit('/devices') },
  { type: 'nav', label: 'Открыть Recipes', icon: '📋', action: () => router.visit('/recipes') },
  { type: 'nav', label: 'Открыть Alerts', icon: '⚠️', action: () => router.visit('/alerts') },
  { type: 'nav', label: 'Открыть Dashboard', icon: '📊', action: () => router.visit('/') },
]

// Результаты поиска
const searchResults = ref({
  zones: [],
  nodes: [],
  recipes: []
})

// Fuzzy search функция
function fuzzyMatch(text, query) {
  if (!query) return true
  const textLower = text.toLowerCase()
  const queryLower = query.toLowerCase()
  let textIndex = 0
  let queryIndex = 0
  
  while (textIndex < textLower.length && queryIndex < queryLower.length) {
    if (textLower[textIndex] === queryLower[queryIndex]) {
      queryIndex++
    }
    textIndex++
  }
  
  return queryIndex === queryLower.length
}

// Подсветка совпадений
function highlightMatch(text, query) {
  if (!query) return text
  const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  return text.replace(regex, '<mark class="bg-amber-500/30">$1</mark>')
}

// Поиск через API
async function searchAPI(query) {
  if (!query || query.length < 2) {
    searchResults.value = { zones: [], nodes: [], recipes: [] }
    return
  }

  loading.value = true
  try {
    const [zonesRes, nodesRes, recipesRes] = await Promise.allSettled([
      api.get('/api/zones', { params: { search: query } }),
      api.get('/api/nodes', { params: { search: query } }),
      api.get('/api/recipes', { params: { search: query } })
    ])

    searchResults.value = {
      zones: zonesRes.status === 'fulfilled' ? (zonesRes.value.data?.data || zonesRes.value.data || []) : [],
      nodes: nodesRes.status === 'fulfilled' ? (nodesRes.value.data?.data || nodesRes.value.data || []) : [],
      recipes: recipesRes.status === 'fulfilled' ? (recipesRes.value.data?.data || recipesRes.value.data || []) : []
    }
  } catch (err) {
    console.error('Search error:', err)
    searchResults.value = { zones: [], nodes: [], recipes: [] }
  } finally {
    loading.value = false
  }
}

// Debounce для поиска
let searchTimeout = null
watch(q, (newQuery) => {
  selectedIndex.value = 0
  if (searchTimeout) clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    searchAPI(newQuery)
  }, 300)
})

// Формируем результаты
const filteredResults = computed(() => {
  const query = q.value.toLowerCase()
  
  // Если запрос пустой, показываем только статические команды
  if (!query) {
    return staticCommands
  }

  const results = []
  
  // Фильтруем статические команды
  staticCommands.forEach(cmd => {
    if (fuzzyMatch(cmd.label, query)) {
      results.push(cmd)
    }
  })

  // Добавляем зоны с быстрыми действиями
  searchResults.value.zones.forEach(zone => {
    if (fuzzyMatch(zone.name, query)) {
      // Переход к зоне
      results.push({
        type: 'zone',
        id: zone.id,
        label: zone.name,
        icon: '🌱',
        category: 'Зона',
        action: () => router.visit(`/zones/${zone.id}`)
      })
      
      // Быстрые действия для зоны
      if (zone.status === 'PAUSED') {
        results.push({
          type: 'action',
          id: `zone-${zone.id}-resume`,
          label: `Возобновить зону "${zone.name}"`,
          icon: '▶️',
          category: 'Действие',
          zoneId: zone.id,
          zoneName: zone.name,
          action: 'resume',
          requiresConfirm: false,
          actionFn: () => executeZoneAction(zone.id, 'resume', zone.name)
        })
      } else if (zone.status === 'RUNNING') {
        results.push({
          type: 'action',
          id: `zone-${zone.id}-pause`,
          label: `Приостановить зону "${zone.name}"`,
          icon: '⏸️',
          category: 'Действие',
          zoneId: zone.id,
          zoneName: zone.name,
          action: 'pause',
          requiresConfirm: true,
          actionFn: () => executeZoneAction(zone.id, 'pause', zone.name)
        })
        results.push({
          type: 'action',
          id: `zone-${zone.id}-irrigate`,
          label: `Полить зону "${zone.name}"`,
          icon: '💧',
          category: 'Действие',
          zoneId: zone.id,
          zoneName: zone.name,
          action: 'irrigate',
          requiresConfirm: true,
          actionFn: () => executeZoneAction(zone.id, 'irrigate', zone.name)
        })
        results.push({
          type: 'action',
          id: `zone-${zone.id}-next-phase`,
          label: `Следующая фаза в зоне "${zone.name}"`,
          icon: '⏭️',
          category: 'Действие',
          zoneId: zone.id,
          zoneName: zone.name,
          action: 'next-phase',
          requiresConfirm: true,
          actionFn: () => executeZoneAction(zone.id, 'next-phase', zone.name)
        })
      }
    }
  })

  // Добавляем узлы
  searchResults.value.nodes.forEach(node => {
    const label = node.name || node.uid || `Node #${node.id}`
    if (fuzzyMatch(label, query)) {
      results.push({
        type: 'node',
        id: node.id,
        label,
        icon: '📱',
        category: 'Устройство',
        action: () => router.visit(`/devices/${node.id}`)
      })
    }
  })

  // Добавляем рецепты
  searchResults.value.recipes.forEach(recipe => {
    if (fuzzyMatch(recipe.name, query)) {
      results.push({
        type: 'recipe',
        id: recipe.id,
        label: recipe.name,
        icon: '📋',
        category: 'Рецепт',
        action: () => router.visit(`/recipes/${recipe.id}`)
      })
    }
  })

  return results
})

const run = (item) => {
  if (!item) return
  
  // Если действие требует подтверждения
  if (item.requiresConfirm && item.actionFn) {
    const actionNames = {
      'pause': 'приостановить',
      'irrigate': 'полить',
      'next-phase': 'перейти к следующей фазе',
      'resume': 'возобновить'
    }
    confirmModal.value = {
      open: true,
      title: 'Подтверждение действия',
      message: `Вы уверены, что хотите ${actionNames[item.action] || 'выполнить это действие'} для зоны "${item.zoneName}"?`,
      action: item.actionFn
    }
    return
  }
  
  // Обычное действие
  if (item.actionFn) {
    item.actionFn()
  } else {
    item.action?.()
  }
  close()
}

async function executeZoneAction(zoneId, action, zoneName) {
  try {
    if (action === 'pause') {
      await api.post(`/api/zones/${zoneId}/pause`, {})
    } else if (action === 'resume') {
      await api.post(`/api/zones/${zoneId}/resume`, {})
    } else if (action === 'irrigate') {
      await sendZoneCommand(zoneId, 'FORCE_IRRIGATION', { duration_sec: 10 })
    } else if (action === 'next-phase') {
      await api.post(`/api/zones/${zoneId}/change-phase`, {
        phase_index: null // следующая фаза
      })
    }
    close()
  } catch (err) {
    console.error(`Failed to execute ${action}:`, err)
  }
}

function confirmAction() {
  if (confirmModal.value.action) {
    confirmModal.value.action()
  }
  confirmModal.value.open = false
  close()
}

const close = () => {
  open.value = false
  q.value = ''
  selectedIndex.value = 0
  searchResults.value = { zones: [], nodes: [], recipes: [] }
}

watch(open, (isOpen) => {
  if (isOpen) {
    nextTick(() => {
      inputRef.value?.focus()
    })
  }
})

const onKey = (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value = !open.value
  }
  if (e.key === 'Escape' && open.value) {
    e.preventDefault()
    close()
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

