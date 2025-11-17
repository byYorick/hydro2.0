<template>
  <AppLayout>
    <div class="flex items-center justify-between mb-3">
      <div>
        <div class="text-lg font-semibold">{{ device.uid || device.name || device.id }}</div>
        <div class="text-xs text-neutral-400">
          <span v-if="device.zone">
            <Link :href="`/zones/${device.zone.id}`" class="text-sky-400 hover:underline">Zone: {{ device.zone.name }}</Link>
          </span>
          <span v-else>Zone: -</span>
          · Type: {{ device.type || '-' }}
          <span v-if="device.fw_version"> · FW: {{ device.fw_version }}</span>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <Badge :variant="device.status === 'online' ? 'success' : device.status === 'offline' ? 'danger' : 'neutral'">
          {{ device.status?.toUpperCase() || 'UNKNOWN' }}
        </Badge>
        <Button size="sm" variant="secondary" @click="onRestart">Restart</Button>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-3">
      <Card class="xl:col-span-2">
        <div class="text-sm font-semibold mb-2">Channels</div>
        <DeviceChannelsTable :channels="channels" @test="onTestChannel" />
      </Card>
      <Card>
        <div class="text-sm font-semibold mb-2">NodeConfig</div>
        <pre class="text-xs text-neutral-300 overflow-auto">{{ nodeConfig }}</pre>
      </Card>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Badge from '@/Components/Badge.vue'
import Button from '@/Components/Button.vue'
import DeviceChannelsTable from '@/Pages/Devices/DeviceChannelsTable.vue'
import axios from 'axios'

const page = usePage()
const device = computed(() => page.props.device || {})
const channels = computed(() => device.value.channels || [])
const nodeConfig = computed(() => {
  const config = {
    id: device.value.uid || device.value.id,
    name: device.value.name,
    type: device.value.type,
    status: device.value.status,
    fw_version: device.value.fw_version,
    config: device.value.config,
    channels: channels.value.map(c => ({
      channel: c.channel,
      type: c.type,
      metric: c.metric,
      unit: c.unit,
    })),
  }
  return JSON.stringify(config, null, 2)
})

const onRestart = () => {
  axios.post(`/api/nodes/${device.value.id}/commands`, {
    type: 'restart',
  }, {
    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
  }).catch(err => {
    console.error('Failed to restart device:', err)
  })
}

const onTestChannel = (channelName) => {
  axios.post(`/api/nodes/${device.value.id}/commands`, {
    type: 'test_channel',
    channel: channelName,
    params: { mode: 'pulse', seconds: 2 },
  }, {
    headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
  }).catch(err => {
    console.error('Failed to test channel:', err)
  })
}
</script>

