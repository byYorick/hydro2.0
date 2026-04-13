/**
 * Канонический мэппинг типа гидропонной системы → конфигурация баков.
 *
 * Используется как watcher в форме автоматики (Setup/Growth wizards),
 * и как side effect внутри irrigation parser при подстановке system_type
 * из recipe automation targets.
 *
 * Правило (единственный источник истины):
 *   drip → 2 бака, дренаж выключен
 *   nft / substrate_trays → 3 бака
 */

import type { IrrigationSystem, WaterFormState } from '@/composables/zoneAutomationTypes'

export function syncSystemToTankLayout(
  waterForm: WaterFormState,
  systemType: IrrigationSystem,
): void {
  if (systemType === 'drip') {
    waterForm.tanksCount = 2
    waterForm.enableDrainControl = false
    return
  }

  waterForm.tanksCount = 3
}
