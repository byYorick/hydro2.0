<template>
  <AppLayout>
    <template #default>
      <div class="space-y-6">
        <section class="ui-hero p-5 space-y-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
                инфраструктура
              </p>
              <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)] mt-1">
                Теплицы
              </h1>
              <p class="text-sm text-[color:var(--text-muted)] max-w-2xl">
                Управление теплицами, зонами и готовностью площадок к запуску циклов.
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <Button
                v-if="canConfigure"
                size="sm"
                variant="primary"
                @click="openCreateModal"
              >
                Новая теплица
              </Button>
            </div>
          </div>
          <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-4">
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Теплиц
              </div>
              <div class="ui-kpi-value">
                {{ totalGreenhouses }}
              </div>
              <div class="ui-kpi-hint">
                Всего в системе
              </div>
            </div>
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Зон
              </div>
              <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
                {{ totalZones }}
              </div>
              <div class="ui-kpi-hint">
                Подключено к теплицам
              </div>
            </div>
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Активных зон
              </div>
              <div class="ui-kpi-value text-[color:var(--accent-green)]">
                {{ totalRunningZones }}
              </div>
              <div class="ui-kpi-hint">
                Зоны в статусе RUNNING
              </div>
            </div>
            <div class="ui-kpi-card">
              <div class="ui-kpi-label">
                Средняя плотность
              </div>
              <div class="ui-kpi-value">
                {{ averageZonesPerGreenhouse }}
              </div>
              <div class="ui-kpi-hint">
                Зон на одну теплицу
              </div>
            </div>
          </div>
        </section>

        <div
          v-if="greenhouses.length === 0"
          class="text-center py-12"
        >
          <div class="text-[color:var(--text-muted)] mb-4">
            Нет теплиц
          </div>
          <Button
            v-if="canConfigure"
            size="sm"
            variant="primary"
            @click="openCreateModal"
          >
            Создать первую теплицу
          </Button>
        </div>

        <div
          v-else
          class="grid gap-4 grid-cols-1 md:grid-cols-2"
        >
          <Card
            v-for="greenhouse in greenhouses"
            :key="greenhouse.id"
            class="surface-card-hover hover:border-[color:var(--border-strong)] transition-all duration-200 cursor-pointer"
            @click="router.visit(`/greenhouses/${greenhouse.id}`)"
          >
            <div class="flex justify-between gap-4 items-start">
              <div class="flex-1 min-w-0">
                <div class="text-xs uppercase text-[color:var(--text-dim)] tracking-[0.2em]">
                  {{ greenhouse.type || 'Теплица' }}
                </div>
                <h3 class="text-lg font-semibold text-[color:var(--text-primary)] truncate">
                  {{ greenhouse.name }}
                </h3>
                <p
                  v-if="greenhouse.description"
                  class="text-xs text-[color:var(--text-dim)] mt-1 line-clamp-2"
                >
                  {{ greenhouse.description }}
                </p>
                <div
                  v-if="greenhouse.uid"
                  class="text-xs text-[color:var(--text-dim)] mt-1"
                >
                  UID: <span class="text-[color:var(--text-muted)]">{{ greenhouse.uid }}</span>
                </div>
              </div>
              <div class="text-right text-xs text-[color:var(--text-muted)] flex-shrink-0">
                <div>Зон: <span class="font-semibold text-[color:var(--text-primary)]">{{ greenhouse.zones_count || 0 }}</span></div>
                <div class="mt-1">
                  Активных: <span class="font-semibold text-[color:var(--accent-green)]">{{ greenhouse.zones_running || 0 }}</span>
                </div>
              </div>
            </div>

            <div class="mt-4 flex gap-2">
              <Link
                :href="`/greenhouses/${greenhouse.id}`"
                class="flex-1"
              >
                <Button
                  size="sm"
                  variant="outline"
                  class="w-full"
                >
                  Открыть
                </Button>
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
import { computed } from 'vue'
import { Link, router, usePage } from '@inertiajs/vue3'
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

const page = usePage<{ auth?: { user?: { role?: string } } }>()
const role = computed(() => page.props.auth?.user?.role ?? 'viewer')
const canConfigure = computed(() => role.value === 'agronomist' || role.value === 'admin')
const totalGreenhouses = computed(() => props.greenhouses.length)
const totalZones = computed(() => props.greenhouses.reduce((sum, greenhouse) => sum + (greenhouse.zones_count || 0), 0))
const totalRunningZones = computed(() => props.greenhouses.reduce((sum, greenhouse) => sum + (greenhouse.zones_running || 0), 0))
const averageZonesPerGreenhouse = computed(() => {
  if (totalGreenhouses.value === 0) return '0.0'
  return (totalZones.value / totalGreenhouses.value).toFixed(1)
})

const { isOpen: showCreateModal, open: openCreateModal, close: closeCreateModal } = useSimpleModal()

function onGreenhouseCreated(_greenhouse: Greenhouse): void {
  // Обновляем страницу для отображения новой теплицы
  router.reload({ only: ['greenhouses'] })
}
</script>
