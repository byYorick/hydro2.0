<template>
  <AppLayout>
    <h1 class="text-lg font-semibold mb-4">Admin · Zones</h1>
    <Card class="mb-4">
      <div class="text-sm font-semibold mb-2">Create Zone</div>
      <form class="grid grid-cols-1 md:grid-cols-4 gap-2" @submit.prevent="onCreate">
        <input v-model="form.name" placeholder="Name" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
        <input v-model="form.description" placeholder="Description" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm" />
        <select v-model="form.status" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
          <option value="RUNNING">RUNNING</option>
          <option value="PAUSED">PAUSED</option>
          <option value="WARNING">WARNING</option>
          <option value="ALARM">ALARM</option>
        </select>
        <select v-model="form.greenhouse_id" class="h-9 rounded-md border border-neutral-700 bg-neutral-900 px-2 text-sm">
          <option :value="null">Выберите теплицу</option>
          <option v-for="gh in greenhouses" :key="gh.id" :value="gh.id">{{ gh.name }}</option>
        </select>
        <div class="md:col-span-4">
          <Button size="sm" type="submit">Create</Button>
        </div>
      </form>
    </Card>

    <Card>
      <div class="text-sm font-semibold mb-2">Zones</div>
      <ul class="text-sm text-neutral-300 space-y-1">
        <li v-for="z in zones" :key="z.id">
          {{ z.name }} — {{ z.status }}
          <span v-if="z.description"> — {{ z.description }}</span>
          <span v-if="z.greenhouse"> — {{ z.greenhouse.name }}</span>
        </li>
      </ul>
    </Card>
  </AppLayout>
</template>

<script setup>
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import { reactive, ref, onMounted } from 'vue'
import axios from 'axios'
import { usePage, router } from '@inertiajs/vue3'

const page = usePage()
const zones = page.props.zones || []
const greenhouses = ref([])
const form = reactive({ name: '', description: '', status: 'RUNNING', greenhouse_id: null })

onMounted(() => {
  axios.get('/api/greenhouses', {
    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
  }).then(res => {
    const data = res.data?.data
    greenhouses.value = (data?.data || (Array.isArray(data) ? data : [])) || []
  }).catch(err => {
    console.error('Failed to load greenhouses:', err)
  })
})

async function onCreate() {
  await axios.post('/api/zones', form, {
    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
  }).then(() => {
    router.reload({ only: ['zones'] })
    form.name = ''
    form.description = ''
    form.greenhouse_id = null
  }).catch(err => {
    console.error('Failed to create zone:', err)
  })
}
</script>

