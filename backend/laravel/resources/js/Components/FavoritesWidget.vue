<template>
  <Card v-if="hasFavorites" class="mb-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold flex items-center gap-2">
        <svg class="w-4 h-4 text-[color:var(--accent-amber)]" fill="currentColor" viewBox="0 0 24 24">
          <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
        </svg>
        Избранное
      </h3>
      <button
        v-if="favoriteZonesCount > 0 || favoriteDevicesCount > 0"
        @click="showClearModal = true"
        class="text-xs text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)] transition-colors"
        title="Очистить все избранное"
      >
        Очистить
      </button>
    </div>

    <!-- Избранные зоны -->
    <div v-if="favoriteZonesCount > 0" class="mb-3">
      <div class="text-xs text-[color:var(--text-dim)] mb-2">Зоны ({{ favoriteZonesCount }})</div>
      <div class="flex flex-wrap gap-2">
        <Link
          v-for="zoneId in favoriteZones"
          :key="zoneId"
          :href="`/zones/${zoneId}`"
          class="px-2 py-1 rounded border text-xs transition-colors hover:border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] border-[color:var(--border-muted)]"
        >
          {{ getZoneName(zoneId) }}
          <button
            @click.stop="removeZone(zoneId)"
            class="ml-1.5 text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)]"
            title="Удалить из избранного"
          >
            ×
          </button>
        </Link>
      </div>
    </div>

    <!-- Избранные устройства -->
    <div v-if="favoriteDevicesCount > 0">
      <div class="text-xs text-[color:var(--text-dim)] mb-2">Устройства ({{ favoriteDevicesCount }})</div>
      <div class="flex flex-wrap gap-2">
        <Link
          v-for="deviceId in favoriteDevices"
          :key="deviceId"
          :href="`/devices/${deviceId}`"
          class="px-2 py-1 rounded border text-xs transition-colors hover:border-[color:var(--border-strong)] bg-[color:var(--bg-elevated)] border-[color:var(--border-muted)]"
        >
          {{ getDeviceName(deviceId) }}
          <button
            @click.stop="removeDevice(deviceId)"
            class="ml-1.5 text-[color:var(--text-dim)] hover:text-[color:var(--text-primary)]"
            title="Удалить из избранного"
          >
            ×
          </button>
        </Link>
      </div>
    </div>

    <!-- Пустое состояние -->
    <div v-if="!hasFavorites" class="text-xs text-[color:var(--text-dim)] text-center py-4">
      Нет избранных элементов
      <div class="text-xs text-[color:var(--text-dim)] mt-1">
        Нажмите на звездочку рядом с зоной или устройством, чтобы добавить в избранное
      </div>
    </div>

    <ConfirmModal
      :open="showClearModal"
      title="Очистить избранное"
      message="Удалить все избранные зоны и устройства?"
      confirm-text="Очистить"
      confirm-variant="danger"
      @close="showClearModal = false"
      @confirm="confirmClear"
    />
  </Card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import Card from '@/Components/Card.vue'
import ConfirmModal from '@/Components/ConfirmModal.vue'
import { useFavorites } from '@/composables/useFavorites'
import type { Zone, Device } from '@/types'

const page = usePage()
const {
  favoriteZones,
  favoriteDevices,
  favoriteZonesCount,
  favoriteDevicesCount,
  removeZoneFromFavorites,
  removeDeviceFromFavorites,
  clearAllFavorites,
} = useFavorites()

const hasFavorites = computed(() => favoriteZonesCount.value > 0 || favoriteDevicesCount.value > 0)
const showClearModal = ref(false)

function getZoneName(zoneId: number): string {
  const zones = (page.props as any).zones as Zone[] | undefined
  const zone = zones?.find(z => z.id === zoneId)
  return zone?.name || `Зона ${zoneId}`
}

function getDeviceName(deviceId: number): string {
  const devices = (page.props as any).devices as Device[] | undefined
  const device = devices?.find(d => d.id === deviceId)
  return device?.uid || device?.name || `Устройство ${deviceId}`
}

function removeZone(zoneId: number): void {
  removeZoneFromFavorites(zoneId)
}

function removeDevice(deviceId: number): void {
  removeDeviceFromFavorites(deviceId)
}

function confirmClear(): void {
  clearAllFavorites()
  showClearModal.value = false
}
</script>
