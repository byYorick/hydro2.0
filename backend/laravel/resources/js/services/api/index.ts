/**
 * Единая точка входа для frontend API-слоя.
 *
 * Использование:
 *   import { api } from '@/services/api'
 *   const zone = await api.zones.getById(447)
 *
 * Правила:
 * 1. Все HTTP-запросы к backend ДОЛЖНЫ идти через `api.<domain>.<method>()`.
 * 2. Прямой импорт `@/utils/apiClient` вне `services/api/` запрещён
 *    (проверяется lint-правилом `no-restricted-imports`).
 * 3. Новые эндпоинты добавляются в соответствующий domain-модуль
 *    (`services/api/zones.ts`, `services/api/recipes.ts`, ...) — никаких
 *    inline-запросов в composables.
 */
import { aiApi } from './ai'
import { alertsApi } from './alerts'
import { automationBundlesApi } from './automationBundles'
import { automationConfigsApi } from './automationConfigs'
import { automationPresetsApi } from './automationPresets'
import { commandsApi } from './commands'
import { greenhousesApi } from './greenhouses'
import { growCyclesApi } from './growCycles'
import { infrastructureApi } from './infrastructure'
import { logsApi } from './logs'
import { nodesApi } from './nodes'
import { nutrientProductsApi } from './nutrientProducts'
import { plantTaxonomiesApi } from './plantTaxonomies'
import { plantsApi } from './plants'
import { recipesApi } from './recipes'
import { settingsApi } from './settings'
import { setupWizardApi } from './setupWizard'
import { simulationsApi } from './simulations'
import { systemApi } from './system'
import { telemetryApi } from './telemetry'
import { usersApi } from './users'
import { zonesApi } from './zones'

export type { ToastHandler } from './_client'

export const api = {
  ai: aiApi,
  alerts: alertsApi,
  automationBundles: automationBundlesApi,
  automationConfigs: automationConfigsApi,
  automationPresets: automationPresetsApi,
  commands: commandsApi,
  greenhouses: greenhousesApi,
  growCycles: growCyclesApi,
  infrastructure: infrastructureApi,
  logs: logsApi,
  nodes: nodesApi,
  nutrientProducts: nutrientProductsApi,
  plantTaxonomies: plantTaxonomiesApi,
  plants: plantsApi,
  recipes: recipesApi,
  settings: settingsApi,
  setupWizard: setupWizardApi,
  simulations: simulationsApi,
  system: systemApi,
  telemetry: telemetryApi,
  users: usersApi,
  zones: zonesApi,
}

export type Api = typeof api
