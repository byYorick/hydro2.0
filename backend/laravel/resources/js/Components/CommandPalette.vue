<template>
  <div>
    <div v-if="open" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-black/70" @click="close"></div>
      <div class="relative mx-auto mt-24 w-full max-w-xl rounded-xl border border-neutral-800 bg-neutral-925 p-3">
        <input v-model="q" placeholder="Команда или поиск..." class="h-10 w-full rounded-md border border-neutral-800 bg-neutral-900 px-3 text-sm" />
        <div class="mt-2 max-h-72 overflow-y-auto">
          <div v-for="(item, i) in results" :key="i"
               class="px-3 py-2 text-sm hover:bg-neutral-850 cursor-pointer rounded-md"
               @click="run(item)">
            {{ item.label }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { router } from '@inertiajs/vue3'

const open = ref(false)
const q = ref('')

const commands = [
  { label: 'Открыть Zones', action: () => router.visit('/zones') },
  { label: 'Открыть Devices', action: () => router.visit('/devices') },
  { label: 'Открыть Recipes', action: () => router.visit('/recipes') },
  { label: 'Открыть Alerts', action: () => router.visit('/alerts') },
]

const results = computed(() => {
  const x = q.value.toLowerCase()
  return !x ? commands : commands.filter(c => c.label.toLowerCase().includes(x))
})

const run = (item) => {
  item.action?.()
  close()
}
const close = () => {
  open.value = false
  q.value = ''
}

const onKey = (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    open.value = true
  }
  if (e.key === 'Escape' && open.value) {
    e.preventDefault()
    close()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

