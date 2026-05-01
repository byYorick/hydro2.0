<template>
  <AppLayout>
    <section class="ui-hero p-5 space-y-4 mb-4">
      <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)]">
        documentation
      </p>
      <h1 class="text-2xl font-semibold tracking-tight text-[color:var(--text-primary)]">
        Документация
      </h1>
      <p class="text-sm text-[color:var(--text-muted)]">
        Вложенная библиотека: обзор и РФ → вода/раствор → субстрат → системы → справочники; отдельно — регламент фертигации для клубники на капле.
      </p>

      <div class="flex flex-wrap gap-2 pt-1">
        <button
          type="button"
          class="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors border"
          :class="activeTab === 'library'
            ? 'bg-[color:var(--bg-elevated)] border-[color:var(--accent-green)] text-[color:var(--text-primary)]'
            : 'border-[color:var(--border-muted)] text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]'"
          @click="activeTab = 'library'"
        >
          Библиотека знаний
        </button>
        <button
          type="button"
          class="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors border"
          :class="activeTab === 'fertigation'
            ? 'bg-[color:var(--bg-elevated)] border-[color:var(--accent-green)] text-[color:var(--text-primary)]'
            : 'border-[color:var(--border-muted)] text-[color:var(--text-muted)] hover:text-[color:var(--text-primary)]'"
          @click="activeTab = 'fertigation'"
        >
          Регламент фертигации (клубника)
        </button>
      </div>
    </section>

    <template v-if="activeTab === 'library'">
      <Card class="mb-4 border-amber-500/20 dark:border-amber-400/25">
        <p class="text-xs text-[color:var(--text-muted)] leading-relaxed">
          <span class="font-semibold text-[color:var(--text-primary)]">Дисклеймер:</span>
          материалы — обобщение открытых руководств. Цели EC/pH/полива зависят от сорта, климата в теплице, PAR/VPD и качества воды.
          Российские учебные тексты и статьи могут быть привязаны к конкретной технологии года выпуска — всегда проверяйте измерениями в вашей зоне.
        </p>
      </Card>

      <div class="flex flex-col md:flex-row gap-4 items-start mb-4">
        <!-- Вертикальные вкладки слева -->
        <aside
          class="w-full md:w-56 lg:w-60 shrink-0 md:sticky md:top-4 md:max-h-[calc(100vh-5rem)] md:overflow-y-auto z-10"
        >
          <Card class="p-2">
            <p class="px-2 py-1.5 text-[10px] uppercase tracking-wider text-[color:var(--text-dim)]">
              Разделы библиотеки
            </p>
            <nav
              class="flex flex-col gap-0.5"
              aria-label="Разделы документации"
            >
              <button
                v-for="sec in LIBRARY_SECTION_TABS"
                :key="sec.id"
                type="button"
                class="w-full rounded-lg px-2.5 py-2 text-left transition-colors border border-transparent"
                :class="librarySection === sec.id
                  ? 'bg-[color:var(--bg-elevated)] border-[color:var(--accent-green)] text-[color:var(--text-primary)] shadow-[inset_3px_0_0_var(--accent-green)]'
                  : 'text-[color:var(--text-muted)] hover:bg-[color:var(--bg-elevated)]/60 hover:text-[color:var(--text-primary)]'"
                @click="librarySection = sec.id"
              >
                <span class="block text-xs font-semibold leading-snug">{{ sec.label }}</span>
                <span class="block text-[10px] text-[color:var(--text-dim)] mt-0.5 leading-snug">{{ sec.hint }}</span>
              </button>
            </nav>
          </Card>
        </aside>

        <!-- Контент выбранного раздела -->
        <div class="flex-1 min-w-0 space-y-4">
          <p class="text-[11px] text-[color:var(--text-dim)] leading-relaxed px-0.5">
            {{ currentSectionMeta?.hint }}
          </p>

          <!-- Поиск: не показываем на справочниках (там отдельный фильтр таблицы) -->
          <Card
            v-if="librarySection !== 'references'"
          >
            <label class="block text-[11px] uppercase tracking-wider text-[color:var(--text-dim)] mb-1">Поиск в этом разделе</label>
            <input
              v-model="query"
              type="search"
              placeholder="Например: EC, дренаж, КиберЛенинка…"
              class="w-full rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder:text-[color:var(--text-dim)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent-green)]"
            >
          </Card>

          <!-- Вкладка: Обзор и Россия -->
          <template v-if="librarySection === 'intro'">
        <Card class="mb-4">
          <h2 class="text-sm font-semibold text-[color:var(--text-primary)] mb-3">
            {{ RUSSIAN_SEGMENT_OVERVIEW.title }}
          </h2>
          <div class="space-y-3 text-xs text-[color:var(--text-muted)] leading-relaxed">
            <p
              v-for="(para, pi) in RUSSIAN_SEGMENT_OVERVIEW.paragraphs"
              :key="pi"
            >
              {{ para }}
            </p>
          </div>
        </Card>
        <TopicCardGrid
          v-if="filteredSectionTopics.length > 0"
          :topics="filteredSectionTopics"
        />
        <Card
          v-if="filteredSectionTopics.length === 0"
          class="mb-4"
        >
          <p class="text-sm text-[color:var(--text-muted)]">
            Ничего не найдено в этом разделе.
          </p>
        </Card>
      </template>

      <!-- Вкладки с темами (раствор, субстрат, системы) -->
      <template v-else-if="librarySection !== 'references'">
        <TopicCardGrid
          v-if="filteredSectionTopics.length > 0"
          :topics="filteredSectionTopics"
        />
        <Card
          v-if="filteredSectionTopics.length === 0"
          class="mb-4"
        >
          <p class="text-sm text-[color:var(--text-muted)]">
            Ничего не найдено. Измените поисковый запрос.
          </p>
        </Card>
      </template>

      <!-- Справочники -->
      <template v-else>
        <Card class="mb-4">
          <label class="block text-[11px] uppercase tracking-wider text-[color:var(--text-dim)] mb-1">Фильтр культуры</label>
          <input
            v-model="cropQuery"
            type="search"
            placeholder="Начните вводить название…"
            class="w-full max-w-md rounded-lg border border-[color:var(--border-muted)] bg-[color:var(--bg-elevated)] px-3 py-2 text-sm text-[color:var(--text-primary)] placeholder:text-[color:var(--text-dim)] focus:outline-none focus:ring-1 focus:ring-[color:var(--accent-green)]"
          >
        </Card>

        <Card class="mb-4">
          <h2 class="text-sm font-semibold mb-2 text-[color:var(--text-primary)]">
            Ориентиры EC и pH по культурам (международная таблица)
          </h2>
          <p class="text-xs text-[color:var(--text-muted)] mb-3 leading-relaxed">
            Значения по Oklahoma State University Extension. Для перекрёстной проверки с российскими ориентирами см. карточки раздела «Вода и раствор» и каталог РФ ниже.
          </p>
          <div class="overflow-auto rounded-lg border border-[color:var(--border-muted)]">
            <table class="w-full border-collapse text-xs">
              <thead class="bg-[color:var(--bg-elevated)] text-[color:var(--text-muted)]">
                <tr>
                  <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                    Культура
                  </th>
                  <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                    EC, mS/cm
                  </th>
                  <th class="text-left px-3 py-2 border-b border-[color:var(--border-muted)]">
                    pH
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in filteredCrops"
                  :key="row.cropEn"
                  class="border-b border-[color:var(--border-muted)] last:border-0"
                >
                  <td class="px-3 py-2 text-[color:var(--text-primary)]">
                    {{ row.cropRu }}
                    <span class="text-[color:var(--text-dim)]">({{ row.cropEn }})</span>
                  </td>
                  <td class="px-3 py-2 text-[color:var(--text-muted)]">
                    {{ row.ecRange }}
                  </td>
                  <td class="px-3 py-2 text-[color:var(--text-muted)]">
                    {{ row.phRange }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p
            v-if="filteredCrops.length === 0"
            class="text-sm text-[color:var(--text-muted)] mt-3"
          >
            Нет совпадений по фильтру.
          </p>
          <p class="text-[11px] text-[color:var(--text-dim)] mt-3">
            Первоисточник:
            <a
              :href="CROP_TABLE_SOURCE.url"
              class="text-[color:var(--accent-cyan)] hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >{{ CROP_TABLE_SOURCE.label }}</a>
          </p>
        </Card>

        <Card class="mb-4">
          <h2 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">
            Российские открытые материалы
          </h2>
          <ul class="space-y-3">
            <li
              v-for="(g, gi) in AUTHORITATIVE_RUSSIAN_GUIDES"
              :key="gi"
              class="text-xs text-[color:var(--text-muted)] border-b border-[color:var(--border-muted)] pb-3 last:border-0 last:pb-0"
            >
              <a
                :href="g.url"
                target="_blank"
                rel="noopener noreferrer"
                class="font-medium text-[color:var(--accent-cyan)] hover:underline"
              >{{ g.title }}</a>
              <span class="text-[color:var(--text-dim)]"> — {{ g.organization }}</span>
              <p class="mt-1 leading-relaxed">
                {{ g.note }}
              </p>
            </li>
          </ul>
        </Card>

        <Card>
          <h2 class="text-sm font-semibold mb-3 text-[color:var(--text-primary)]">
            Международные extension-руководства
          </h2>
          <ul class="space-y-3">
            <li
              v-for="(g, gi) in AUTHORITATIVE_EXTERNAL_GUIDES"
              :key="gi"
              class="text-xs text-[color:var(--text-muted)] border-b border-[color:var(--border-muted)] pb-3 last:border-0 last:pb-0"
            >
              <a
                :href="g.url"
                target="_blank"
                rel="noopener noreferrer"
                class="font-medium text-[color:var(--accent-cyan)] hover:underline"
              >{{ g.title }}</a>
              <span class="text-[color:var(--text-dim)]"> — {{ g.organization }}</span>
              <p class="mt-1 leading-relaxed">
                {{ g.note }}
              </p>
            </li>
          </ul>
        </Card>
      </template>
        </div>
      </div>
    </template>

    <template v-else>
      <section class="mb-4">
        <p class="text-[11px] uppercase tracking-[0.28em] text-[color:var(--text-dim)] mb-2">
          fertigation guide
        </p>
        <p class="text-sm text-[color:var(--text-muted)] mb-4">
          Практический регламент для клубники на капле (осмос), схема pH (кислота/щёлочь) + EC A/B/C/D.
        </p>
        <FertigationGuidePanel />
      </section>
    </template>
  </AppLayout>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppLayout from '@/Layouts/AppLayout.vue'
import Card from '@/Components/Card.vue'
import FertigationGuidePanel from '@/Components/Documentation/FertigationGuidePanel.vue'
import TopicCardGrid from '@/Components/Documentation/TopicCardGrid.vue'
import {
  AUTHORITATIVE_EXTERNAL_GUIDES,
  AUTHORITATIVE_RUSSIAN_GUIDES,
  CROP_EC_PH_REFERENCE,
  CROP_TABLE_SOURCE,
  KNOWLEDGE_CATEGORY_LABELS,
  LIBRARY_SECTION_TABS,
  RUSSIAN_SEGMENT_OVERVIEW,
  topicsForLibrarySection,
  type LibrarySectionId,
} from '@/data/documentationKnowledgeLibrary'

const activeTab = ref<'library' | 'fertigation'>('library')
const librarySection = ref<LibrarySectionId>('intro')
const query = ref('')
const cropQuery = ref('')

const currentSectionMeta = computed(() =>
  LIBRARY_SECTION_TABS.find(s => s.id === librarySection.value),
)

watch(librarySection, () => {
  query.value = ''
})

function topicMatchesQuery(topic: ReturnType<typeof topicsForLibrarySection>[number], q: string): boolean {
  if (!q.trim()) {
    return true
  }
  const needle = q.trim().toLowerCase()
  const hay = [
    topic.title,
    topic.summary,
    ...topic.points,
    KNOWLEDGE_CATEGORY_LABELS[topic.category],
    ...topic.sources.map(s => `${s.label} ${s.url}`),
  ].join('\n').toLowerCase()
  return hay.includes(needle)
}

const filteredSectionTopics = computed(() => {
  const base = topicsForLibrarySection(librarySection.value)
  return base.filter(t => topicMatchesQuery(t, query.value))
})

const filteredCrops = computed(() => {
  const q = cropQuery.value.trim().toLowerCase()
  if (!q) {
    return CROP_EC_PH_REFERENCE
  }
  return CROP_EC_PH_REFERENCE.filter(
    r =>
      r.cropRu.toLowerCase().includes(q)
      || r.cropEn.toLowerCase().includes(q),
  )
})
</script>
