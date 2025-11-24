<template>
  <nav class="space-y-1">
    <!-- Общие пункты для всех -->
    <NavLink href="/" label="Панель управления" />
    
    <!-- Навигация для агронома -->
    <template v-if="isAgronomist">
      <NavLink href="/zones" label="Зоны" />
      <NavLink href="/recipes" label="Рецепты" />
      <NavLink href="/analytics" label="Аналитика" />
    </template>
    
    <!-- Навигация для админа -->
    <template v-if="isAdmin">
      <NavLink href="/zones" label="Зоны" />
      <NavLink href="/devices" label="Устройства" />
      <NavLink href="/recipes" label="Рецепты" />
      <NavLink href="/users" label="Пользователи" />
      <NavLink href="/audit" label="Аудит" />
    </template>
    
    <!-- Навигация для инженера -->
    <template v-if="isEngineer">
      <NavLink href="/zones" label="Зоны" />
      <NavLink href="/devices" label="Устройства" />
      <NavLink href="/system" label="Система" />
      <NavLink href="/logs" label="Логи" />
    </template>
    
    <!-- Навигация для оператора -->
    <template v-if="isOperator">
      <NavLink href="/zones" label="Зоны" />
      <NavLink href="/devices" label="Устройства" />
      <NavLink href="/recipes" label="Рецепты" />
      <NavLink href="/logs" label="Логи" />
    </template>
    
    <!-- Навигация для наблюдателя -->
    <template v-if="isViewer">
      <NavLink href="/zones" label="Зоны" />
      <NavLink href="/devices" label="Устройства" />
      <NavLink href="/recipes" label="Рецепты" />
    </template>
    
    <!-- Общие для всех -->
    <NavLink href="/alerts" label="Алерты" />
    <NavLink v-if="!isViewer" href="/settings" label="Настройки" />
  </nav>
</template>

<script setup lang="ts">
import { useRole } from '@/composables/useRole'
import NavLink from '@/Components/NavLink.vue'

const {
  isAgronomist,
  isAdmin,
  isEngineer,
  isOperator,
  isViewer,
} = useRole()
</script>

