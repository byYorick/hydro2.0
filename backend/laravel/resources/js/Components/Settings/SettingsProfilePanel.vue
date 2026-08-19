<template>
  <SettingsSectionShell
    title="Мой профиль"
    description="Основные данные вашей учётной записи. Редактирование имени и email — через администратора."
    icon="👤"
    test-id="settings-section-profile"
  >
    <div class="space-y-6">
      <dl class="grid gap-3 sm:grid-cols-2">
        <div class="settings-field-card">
          <dt class="settings-field-card__label">
            Имя
          </dt>
          <dd class="mt-2 text-sm font-medium text-[color:var(--text-primary)]">
            {{ name }}
          </dd>
        </div>
        <div class="settings-field-card">
          <dt class="settings-field-card__label">
            Email
          </dt>
          <dd class="mt-2 text-sm font-medium text-[color:var(--text-primary)] break-all">
            {{ email }}
          </dd>
        </div>
        <div class="settings-field-card sm:col-span-2">
          <dt class="settings-field-card__label">
            Роль в системе
          </dt>
          <dd class="mt-2">
            <Badge :variant="roleBadgeVariant">
              {{ roleLabel }}
            </Badge>
          </dd>
        </div>
      </dl>

      <SettingsThemeToggle />

      <UpdatePasswordForm class="max-w-xl" />
    </div>
  </SettingsSectionShell>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import SettingsSectionShell from '@/Components/Settings/SettingsSectionShell.vue'
import SettingsThemeToggle from '@/Components/Settings/SettingsThemeToggle.vue'
import UpdatePasswordForm from '@/Pages/Profile/Partials/UpdatePasswordForm.vue'

withDefaults(defineProps<{
  name?: string
  email?: string
  roleLabel?: string
  roleBadgeVariant?: 'danger' | 'warning' | 'info' | 'success' | 'neutral'
}>(), {
  name: '',
  email: '',
  roleLabel: '',
  roleBadgeVariant: 'info',
})
</script>
