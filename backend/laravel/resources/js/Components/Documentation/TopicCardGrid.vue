<template>
  <div class="grid gap-4 mb-4 lg:grid-cols-2">
    <Card
      v-for="topic in topics"
      :key="topic.id"
      class="flex flex-col"
    >
      <div class="flex items-start justify-between gap-2 mb-2">
        <h2 class="text-sm font-semibold text-[color:var(--text-primary)] leading-snug">
          {{ topic.title }}
        </h2>
        <span class="shrink-0 rounded-md bg-[color:var(--bg-elevated)] px-2 py-0.5 text-[10px] uppercase tracking-wide text-[color:var(--text-dim)]">
          {{ KNOWLEDGE_CATEGORY_LABELS[topic.category] }}
        </span>
      </div>
      <p class="text-xs text-[color:var(--text-muted)] mb-3 leading-relaxed">
        {{ topic.summary }}
      </p>
      <ul class="list-disc pl-4 text-xs text-[color:var(--text-muted)] space-y-1.5 mb-4 flex-1">
        <li
          v-for="(pt, idx) in topic.points"
          :key="idx"
        >
          {{ pt }}
        </li>
      </ul>
      <div class="pt-3 border-t border-[color:var(--border-muted)] space-y-1.5">
        <p class="text-[10px] uppercase tracking-wider text-[color:var(--text-dim)]">
          Источники
        </p>
        <div class="flex flex-col gap-1">
          <a
            v-for="(src, sidx) in topic.sources"
            :key="sidx"
            :href="src.url"
            target="_blank"
            rel="noopener noreferrer"
            class="text-xs text-[color:var(--accent-cyan)] hover:underline break-all"
          >
            {{ src.label }}
          </a>
        </div>
      </div>
    </Card>
  </div>
</template>

<script setup lang="ts">
import Card from '@/Components/Card.vue'
import { KNOWLEDGE_CATEGORY_LABELS, type KnowledgeTopic } from '@/data/documentationKnowledgeLibrary'

defineProps<{ topics: KnowledgeTopic[] }>()
</script>
