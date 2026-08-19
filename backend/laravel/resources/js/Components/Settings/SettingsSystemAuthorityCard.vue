<template>
  <SettingsSectionShell
    title="Системные настройки автоматики"
    description="Калибровки, дефолты автоматики, шаблоны команд и пороги observability — отдельная страница authority."
    icon="📊"
    test-id="settings-system-authority-card"
  >
    <Link href="/system/settings">
      <Button
        size="sm"
        variant="secondary"
        data-testid="settings-open-system-authority"
      >
        Открыть системные настройки →
      </Button>
    </Link>
  </SettingsSectionShell>
</template>

<script setup lang="ts">
import { Link } from '@inertiajs/vue3'
import Button from '@/Components/Button.vue'
import SettingsSectionShell from '@/Components/Settings/SettingsSectionShell.vue'
</script>
