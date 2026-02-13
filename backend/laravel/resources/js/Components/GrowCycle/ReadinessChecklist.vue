<template>
  <Card>
    <div class="space-y-4">
      <div>
        <h3 class="text-sm font-semibold mb-2">
          Проверка готовности зоны
        </h3>
        <p class="text-xs text-[color:var(--text-muted)] mb-4">
          Убедитесь, что все обязательные компоненты настроены и готовы к запуску
        </p>
      </div>

      <div
        v-if="loading"
        class="text-sm text-[color:var(--text-muted)]"
      >
        Проверка готовности...
      </div>

      <div
        v-else-if="readiness"
        class="space-y-4"
      >
        <!-- Основные проверки -->
        <div class="space-y-2">
          <div
            v-for="check in checks"
            :key="check.key"
            class="flex items-center gap-3 p-2 rounded"
            :class="check.passed ? 'bg-[color:var(--badge-success-bg)]' : 'bg-[color:var(--badge-danger-bg)]'"
          >
            <span
              :class="[
                'text-lg',
                check.passed ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--accent-red)]'
              ]"
            >
              {{ check.passed ? '✓' : '✗' }}
            </span>
            <div class="flex-1">
              <div class="text-sm font-medium">
                {{ check.label }}
              </div>
              <div
                v-if="check.message"
                class="text-xs text-[color:var(--text-muted)] mt-1"
              >
                {{ check.message }}
              </div>
            </div>
          </div>
        </div>

        <!-- Детальные ошибки -->
        <div
          v-if="errors.length > 0"
          class="mt-4 p-3 rounded border border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]"
        >
          <div class="text-xs font-semibold text-[color:var(--accent-red)] mb-2">
            Обнаружены проблемы:
          </div>
          <ul class="space-y-1">
            <li
              v-for="(error, index) in errors"
              :key="index"
              class="text-xs text-[color:var(--badge-danger-text)]"
            >
              • {{ error }}
            </li>
          </ul>
        </div>

        <!-- Статус готовности -->
        <div
          class="mt-4 p-4 rounded border"
          :class="
            readiness.ready
              ? 'border-[color:var(--badge-success-border)] bg-[color:var(--badge-success-bg)]'
              : 'border-[color:var(--badge-danger-border)] bg-[color:var(--badge-danger-bg)]'
          "
        >
          <div class="flex items-center gap-2">
            <span
              :class="[
                'text-lg',
                readiness.ready ? 'text-[color:var(--accent-green)]' : 'text-[color:var(--accent-red)]'
              ]"
            >
              {{ readiness.ready ? '✓' : '✗' }}
            </span>
            <div>
              <div class="text-sm font-semibold">
                {{ readiness.ready ? 'Зона готова к запуску' : 'Зона не готова к запуску' }}
              </div>
              <div class="text-xs text-[color:var(--text-muted)] mt-1">
                {{ readiness.ready ? 'Все проверки пройдены успешно' : 'Исправьте указанные проблемы перед запуском' }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-else
        class="text-sm text-[color:var(--text-muted)]"
      >
        Нет данных о готовности
      </div>
    </div>
  </Card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Card from '@/Components/Card.vue'

interface ReadinessCheck {
  key: string
  label: string
  passed: boolean
  message?: string
}

interface ReadinessData {
  ready: boolean
  required_assets?: Record<string, boolean>
  optional_assets?: Record<string, boolean>
  nodes?: {
    online: number
    total: number
    all_online: boolean
  }
  checks?: Record<string, boolean>
  errors?: string[]
}

interface Props {
  zoneId: number | null
  readiness?: ReadinessData | null
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  zoneId: null,
  readiness: null,
  loading: false,
})

const errors = computed(() => {
  if (!props.readiness) return []
  
  const errs: string[] = []
  
  // Проверка обязательных активов
  if (props.readiness.required_assets) {
    Object.entries(props.readiness.required_assets).forEach(([asset, present]) => {
      if (!present) {
        const assetLabels: Record<string, string> = {
          main_pump: 'Основная помпа',
          drain: 'Дренаж',
          ph_acid_pump: 'Насос pH кислоты',
          ph_base_pump: 'Насос pH щёлочи',
          ec_npk_pump: 'Насос EC NPK',
          ec_calcium_pump: 'Насос EC Calcium',
          ec_magnesium_pump: 'Насос EC Magnesium',
          ec_micro_pump: 'Насос EC Micro',
          tank_clean: 'Бак чистой воды',
          tank_nutrient: 'Бак раствора',
        }
        errs.push(`Отсутствует обязательное оборудование: ${assetLabels[asset] || asset}`)
      }
    })
  }
  
  // Проверка нод
  if (props.readiness.nodes) {
    if (props.readiness.nodes.total === 0) {
      errs.push('Нет привязанных нод в зоне')
    } else if (props.readiness.nodes.online === 0) {
      errs.push('Нет онлайн нод в зоне')
    } else if (!props.readiness.nodes.all_online) {
      errs.push(`Только ${props.readiness.nodes.online} из ${props.readiness.nodes.total} нод онлайн`)
    }
  }
  
  // Дополнительные ошибки из API
  if (props.readiness.errors) {
    errs.push(...props.readiness.errors)
  }
  
  return errs
})

const checks = computed((): ReadinessCheck[] => {
  if (!props.readiness) return []
  
  const checksList: ReadinessCheck[] = []
  
  // Проверка обязательных активов
  if (props.readiness.required_assets) {
    Object.entries(props.readiness.required_assets).forEach(([asset, present]) => {
      const assetLabels: Record<string, string> = {
        main_pump: 'Основная помпа',
        drain: 'Дренаж',
        ph_acid_pump: 'Насос pH кислоты',
        ph_base_pump: 'Насос pH щёлочи',
        ec_npk_pump: 'Насос EC NPK',
        ec_calcium_pump: 'Насос EC Calcium',
        ec_magnesium_pump: 'Насос EC Magnesium',
        ec_micro_pump: 'Насос EC Micro',
        tank_clean: 'Бак чистой воды',
        tank_nutrient: 'Бак раствора',
      }
      checksList.push({
        key: `asset_${asset}`,
        label: assetLabels[asset] || asset,
        passed: present,
        message: present ? undefined : 'Не настроено',
      })
    })
  }
  
  // Проверка нод
  if (props.readiness.nodes) {
    checksList.push({
      key: 'online_nodes',
      label: 'Онлайн ноды',
      passed: props.readiness.nodes.online > 0,
      message: props.readiness.nodes.online > 0
        ? `${props.readiness.nodes.online} из ${props.readiness.nodes.total} онлайн`
        : 'Нет онлайн нод',
    })
  }
  
  // Дополнительные проверки
  if (props.readiness.checks) {
    Object.entries(props.readiness.checks).forEach(([key, passed]) => {
      const checkLabels: Record<string, string> = {
        main_pump: 'Основная помпа привязана',
        drain: 'Дренаж привязан',
        ph_acid_pump: 'Насос pH кислоты привязан',
        ph_base_pump: 'Насос pH щёлочи привязан',
        ec_npk_pump: 'Насос EC NPK привязан',
        ec_calcium_pump: 'Насос EC Calcium привязан',
        ec_magnesium_pump: 'Насос EC Magnesium привязан',
        ec_micro_pump: 'Насос EC Micro привязан',
        online_nodes: 'Есть онлайн ноды',
      }
      
      if (!checksList.find(c => c.key === key || c.key === `asset_${key}`)) {
        checksList.push({
          key,
          label: checkLabels[key] || key,
          passed,
        })
      }
    })
  }
  
  return checksList
})
</script>
