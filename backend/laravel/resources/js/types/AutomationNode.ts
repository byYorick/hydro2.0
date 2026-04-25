/**
 * Упрощённая проекция ESP32-узла для UI автоматизации (wizard, profile sections).
 * Используется при выборе узлов в bindings (irrigation / pH / EC / climate / lighting).
 *
 * Импортировать через: import type { AutomationNode } from '@/types/AutomationNode'
 *
 * Поля совпадают с DTO, отдаваемым на фронт: Greenhouse → Zone → Node + список каналов
 * с их binding_role (см. backend/laravel/app/Http/Resources/NodeResource.php).
 */
export interface AutomationNode {
  id: number
  uid?: string
  name?: string
  type?: string
  zone_id?: number | null
  pending_zone_id?: number | null
  lifecycle_state?: string | null
  channels?: Array<{
    channel?: string
    type?: string
    metric?: string | null
    unit?: string | null
    binding_role?: string | null
  }>
}
