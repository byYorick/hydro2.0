<template>
  <AppLayout>
    <template #default>
      <div class="space-y-6">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 class="text-lg font-semibold">Теплицы</h1>
            <p class="text-sm text-neutral-400 max-w-2xl">
              Управление всеми теплицами системы
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button size="sm" variant="primary" @click="openCreateModal">
              Новая теплица
            </Button>
          </div>
        </div>

        <div v-if="greenhouses.length === 0" class="text-center py-12">
          <div class="text-neutral-400 mb-4">Нет теплиц</div>
          <Button size="sm" variant="primary" @click="openCreateModal">
            Создать первую теплицу
          </Button>
        </div>

        <div v-else class="grid gap-4 grid-cols-1 md:grid-cols-2">
          <Card
            v-for="greenhouse in greenhouses"
            :key="greenhouse.id"
            class="hover:shadow-2xl transition-all duration-200 cursor-pointer"
            @click="router.visit(`/greenhouses/${greenhouse.id}`)"
          >
            <div class="flex justify-between gap-4 items-start">
              <div class="flex-1 min-w-0">
                <div class="text-xs uppercase text-neutral-500 tracking-[0.2em]">
                  {{ greenhouse.type || 'Теплица' }}
                </div>
                <h3 class="text-lg font-semibold text-neutral-100 truncate">
                  {{ greenhouse.name }}
                </h3>
                <p v-if="greenhouse.description" class="text-xs text-neutral-500 mt-1 line-clamp-2">
                  {{ greenhouse.description }}
                </p>
                <div v-if="greenhouse.uid" class="text-xs text-neutral-500 mt-1">
                  UID: <span class="text-neutral-400">{{ greenhouse.uid }}</span>
                </div>
              </div>
              <div class="text-right text-xs text-neutral-400 flex-shrink-0">
                <div>Зон: <span class="font-semibold text-neutral-100">{{ greenhouse.zones_count || 0 }}</span></div>
                <div class="mt-1">Активных: <span class="font-semibold text-emerald-300">{{ greenhouse.zones_running || 0 }}</span></div>
              </div>
            </div>

            <div class="mt-4 flex gap-2">
              <Link :href="`/greenhouses/${greenhouse.id}`" class="flex-1">
                <Button size="sm" variant="outline" class="w-full">Открыть</Button>
              </Link>
            </div>
          </Card>
        </div>

        <!-- Создание теплицы -->
        <GreenhouseCreateModal
          :show="showCreateModal"
          @close="closeCreateModal"
          @created="onGreenhouseCreated"
        />
      </div>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { Link, router } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import Button from '@/Components/Button.vue'
import GreenhouseCreateModal from '@/Components/GreenhouseCreateModal.vue'
import { useSimpleModal } from '@/composables/useModal'

interface Greenhouse {
  id: number
  uid: string
  name: string
  type?: string
  description?: string
  timezone?: string
  created_at: string
  zones_count?: number
  zones_running?: number
}

interface Props {
  greenhouses: Greenhouse[]
}

const props = defineProps<Props>()

const { isOpen: showCreateModal, open: openCreateModal, close: closeCreateModal } = useSimpleModal()

function onGreenhouseCreated(greenhouse: Greenhouse): void {
  // Обновляем страницу для отображения новой теплицы
  router.reload({ only: ['greenhouses'] })
}
</script>

