<template>
  <AppLayout>
    <section class="ui-hero p-5 space-y-4 mb-4">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
            агрохимия
          </p>
          <h1 class="text-2xl font-semibold tracking-tight mt-1 text-[color:var(--text-primary)]">
            Удобрения
          </h1>
          <p class="text-sm text-[color:var(--text-muted)]">
            Справочник продуктов для 4-насосной EC-схемы: NPK, кальций, магний и микроэлементы.
          </p>
        </div>
        <Link href="/nutrients/create">
          <Button
            size="sm"
            variant="primary"
          >
            Новое удобрение
          </Button>
        </Link>
      </div>

      <div class="ui-kpi-grid grid-cols-2 xl:grid-cols-5">
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            Всего продуктов
          </div>
          <div class="ui-kpi-value">
            {{ totalProducts }}
          </div>
          <div class="ui-kpi-hint">
            В каталоге удобрений
          </div>
        </div>
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            NPK
          </div>
          <div class="ui-kpi-value text-[color:var(--accent-cyan)]">
            {{ npkCount }}
          </div>
          <div class="ui-kpi-hint">
            Комплексные смеси
          </div>
        </div>
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            Кальций
          </div>
          <div class="ui-kpi-value text-[color:var(--accent-green)]">
            {{ calciumCount }}
          </div>
          <div class="ui-kpi-hint">
            Кальциевая линия
          </div>
        </div>
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            Магний
          </div>
          <div class="ui-kpi-value text-[color:var(--accent-orange)]">
            {{ magnesiumCount }}
          </div>
          <div class="ui-kpi-hint">
            MgSO4 линия
          </div>
        </div>
        <div class="ui-kpi-card">
          <div class="ui-kpi-label">
            Микро
          </div>
          <div class="ui-kpi-value">
            {{ microCount }}
          </div>
          <div class="ui-kpi-hint">
            Микроэлементы и хелаты
          </div>
        </div>
      </div>
    </section>

    <Card class="mb-3">
      <div class="text-sm font-semibold mb-1">
        Рекомендованная схема дозирования
      </div>
      <div class="text-xs text-[color:var(--text-muted)] space-y-1">
        <p>Насос 1: комплекс NPK, насос 2: кальций отдельно, насос 3: микроэлементы.</p>
        <p>Для предотвращения осадка добавляйте дозы последовательно с паузой (`nutrient_dose_delay_sec`) и контролем EC (`nutrient_ec_stop_tolerance`).</p>
      </div>
    </Card>

    <div class="mb-3 flex flex-col sm:flex-row gap-2 sm:items-center">
      <input
        v-model="query"
        type="text"
        class="input-field sm:w-64"
        placeholder="Поиск по производителю/названию"
      />
      <select
        v-model="componentFilter"
        class="input-select sm:w-52"
      >
        <option value="all">
          Все компоненты
        </option>
        <option value="npk">
          NPK
        </option>
        <option value="calcium">
          Кальций
        </option>
        <option value="magnesium">
          Магний
        </option>
        <option value="micro">
          Микроэлементы
        </option>
      </select>
    </div>

    <div class="rounded-xl border border-[color:var(--border-muted)] overflow-hidden max-h-[720px] flex flex-col">
      <div class="overflow-auto flex-1">
        <table class="w-full border-collapse">
          <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)] text-sm sticky top-0 z-10">
            <tr>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Производитель
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Продукт
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Компонент
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Состав
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Стадии
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Источник
              </th>
              <th class="text-left px-3 py-2 font-semibold border-b border-[color:var(--border-muted)]">
                Действия
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(product, index) in paginatedProducts"
              :key="product.id"
              :class="index % 2 === 0 ? 'bg-[color:var(--bg-surface-strong)]' : 'bg-[color:var(--bg-surface)]'"
              class="text-sm border-b border-[color:var(--border-muted)] hover:bg-[color:var(--bg-elevated)] transition-colors"
            >
              <td class="px-3 py-2">
                {{ product.manufacturer }}
              </td>
              <td class="px-3 py-2 text-[color:var(--accent-cyan)]">
                {{ product.name }}
              </td>
              <td class="px-3 py-2">
                <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs bg-[color:var(--badge-info-bg)] text-[color:var(--badge-info-text)] border border-[color:var(--badge-info-border)]">
                  {{ componentLabel(product.component) }}
                </span>
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                {{ product.composition || '—' }}
              </td>
              <td class="px-3 py-2 text-xs text-[color:var(--text-muted)]">
                {{ product.recommended_stage || '—' }}
              </td>
              <td class="px-3 py-2 text-xs">
                <a
                  v-if="sourceUrl(product)"
                  :href="sourceUrl(product)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-[color:var(--accent-cyan)] hover:underline"
                >
                  ссылка
                </a>
                <span
                  v-else
                  class="text-[color:var(--text-muted)]"
                >—</span>
              </td>
              <td class="px-3 py-2">
                <Link :href="`/nutrients/${product.id}/edit`">
                  <Button
                    size="sm"
                    variant="secondary"
                  >
                    Редактировать
                  </Button>
                </Link>
              </td>
            </tr>
            <tr v-if="paginatedProducts.length === 0">
              <td
                colspan="7"
                class="px-3 py-6 text-sm text-[color:var(--text-dim)] text-center"
              >
                {{ filteredProducts.length === 0 && nutrients.length > 0 ? 'Нет совпадений по фильтру' : 'Каталог удобрений пуст' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <Pagination
        v-model:current-page="currentPage"
        v-model:per-page="perPage"
        :total="filteredProducts.length"
      />
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Link, usePage } from '@inertiajs/vue3'
import AppLayout from '@/Layouts/AppLayout.vue'
import Button from '@/Components/Button.vue'
import Card from '@/Components/Card.vue'
import Pagination from '@/Components/Pagination.vue'
import type { NutrientProduct } from '@/types'

interface PageProps {
  nutrients?: NutrientProduct[]
  [key: string]: any
}

const page = usePage<PageProps>()
const nutrients = computed(() => (page.props.nutrients || []) as NutrientProduct[])

const query = ref('')
const componentFilter = ref<'all' | 'npk' | 'calcium' | 'magnesium' | 'micro'>('all')
const currentPage = ref(1)
const perPage = ref(25)

const totalProducts = computed(() => nutrients.value.length)
const npkCount = computed(() => nutrients.value.filter((item) => item.component === 'npk').length)
const calciumCount = computed(() => nutrients.value.filter((item) => item.component === 'calcium').length)
const magnesiumCount = computed(() => nutrients.value.filter((item) => item.component === 'magnesium').length)
const microCount = computed(() => nutrients.value.filter((item) => item.component === 'micro').length)

const filteredProducts = computed(() => {
  const q = query.value.toLowerCase().trim()

  return nutrients.value.filter((item) => {
    const componentOk = componentFilter.value === 'all' || item.component === componentFilter.value
    if (!componentOk) {
      return false
    }

    if (!q) {
      return true
    }

    const haystack = [item.manufacturer, item.name, item.composition || '', item.recommended_stage || '']
      .join(' ')
      .toLowerCase()

    return haystack.includes(q)
  })
})

function clampCurrentPage(total: number): number {
  const maxPage = Math.ceil(total / perPage.value) || 1
  const validPage = Math.min(currentPage.value, maxPage)
  if (validPage !== currentPage.value) {
    currentPage.value = validPage
  }
  return validPage
}

watch([filteredProducts, perPage], () => {
  if (filteredProducts.value.length > 0) {
    clampCurrentPage(filteredProducts.value.length)
  } else {
    currentPage.value = 1
  }
})

watch([query, componentFilter], () => {
  currentPage.value = 1
})

const paginatedProducts = computed(() => {
  const total = filteredProducts.value.length
  if (total === 0) {
    return []
  }

  const validPage = clampCurrentPage(total)
  const start = (validPage - 1) * perPage.value
  const end = start + perPage.value

  return filteredProducts.value.slice(start, end)
})

function componentLabel(component: string): string {
  if (component === 'npk') return 'NPK'
  if (component === 'calcium') return 'Кальций'
  if (component === 'magnesium') return 'Магний'
  if (component === 'micro') return 'Микроэлементы'
  return component
}

function sourceUrl(product: NutrientProduct): string | null {
  const url = product.metadata?.source_url
  return typeof url === 'string' && url.length > 0 ? url : null
}
</script>
