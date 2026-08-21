<template>
  <SettingsSectionShell
    title="Мой профиль"
    description="Основные данные вашей учётной записи. Имя и email меняет администратор."
    icon="👤"
    test-id="settings-section-profile"
  >
    <div class="space-y-4">
      <div class="settings-rows settings-rows--split">
        <SettingsFieldRow
          label="Имя"
          test-id="settings-profile-name"
        >
          <span class="settings-row__readonly">{{ name || '—' }}</span>
        </SettingsFieldRow>
        <SettingsFieldRow
          label="Email"
          test-id="settings-profile-email"
        >
          <span class="settings-row__readonly">{{ email || '—' }}</span>
        </SettingsFieldRow>
        <SettingsFieldRow
          label="Роль"
          test-id="settings-profile-role"
        >
          <Badge :variant="roleBadgeVariant">
            {{ roleLabel }}
          </Badge>
        </SettingsFieldRow>
        <SettingsThemeToggle />
      </div>

      <div class="max-w-md">
        <UpdatePasswordForm />
      </div>
    </div>
  </SettingsSectionShell>
</template>

<script setup lang="ts">
import Badge from '@/Components/Badge.vue'
import SettingsSectionShell from '@/Components/Settings/SettingsSectionShell.vue'
import SettingsFieldRow from '@/Components/Settings/SettingsFieldRow.vue'
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
