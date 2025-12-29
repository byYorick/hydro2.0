<template>
  <AppLayout title="Аналитика">
    <div class="space-y-4">
      <PageHeader
        title="Аналитика"
        subtitle="Графики, отчеты и сравнения по выращиванию."
        eyebrow="данные и отчеты"
      />

      <section class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-6">
        <EmptyState
          title="Аналитика в разработке"
          description="Сейчас доступны только ключевые метрики в разделах зон и циклов."
          container-class="py-0"
        />
      </section>

      <section class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">Графики урожайности</div>
          <SkeletonBlock :lines="4" line-height="0.7rem" />
        </div>
        <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">Отчеты по циклам</div>
          <SkeletonBlock :lines="4" line-height="0.7rem" />
        </div>
        <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">Эффективность рецептов</div>
          <SkeletonBlock :lines="4" line-height="0.7rem" />
        </div>
        <div class="surface-card border border-[color:var(--border-muted)] rounded-2xl p-4">
          <div class="text-xs uppercase tracking-[0.12em] text-[color:var(--text-dim)] mb-3">Оптимизации</div>
          <SkeletonBlock :lines="4" line-height="0.7rem" />
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup lang="ts">
import AppLayout from '@/Layouts/AppLayout.vue'
import EmptyState from '@/Components/EmptyState.vue'
import PageHeader from '@/Components/PageHeader.vue'
import SkeletonBlock from '@/Components/SkeletonBlock.vue'
</script>
