import type { AutomationControlMode } from '@/types/Automation'

/** Матрица переходов — зеркало ZoneAutomationControlModeController::isTransitionAllowedForRole. */
export function isControlModeTransitionAllowed(
  role: string,
  fromMode: AutomationControlMode,
  toMode: AutomationControlMode,
): boolean {
  if (fromMode === toMode) {
    return true
  }

  const normalizedRole = String(role ?? '').trim().toLowerCase()
  if (['agronomist', 'engineer', 'admin'].includes(normalizedRole)) {
    return true
  }

  if (normalizedRole === 'operator') {
    return (fromMode === 'auto' || fromMode === 'semi') && toMode === 'manual'
  }

  return false
}

export const CONTROL_MODE_LABELS: Record<AutomationControlMode, string> = {
  auto: 'Авто',
  semi: 'Полуавто',
  manual: 'Ручной',
}

export function controlModeDisabledReason(
  role: string,
  fromMode: AutomationControlMode,
  toMode: AutomationControlMode,
): string | null {
  if (isControlModeTransitionAllowed(role, fromMode, toMode)) {
    return null
  }

  const normalizedRole = String(role ?? '').trim().toLowerCase()
  if (normalizedRole === 'viewer') {
    return 'Режим управления доступен только агроному, инженеру или оператору (аварийный manual).'
  }
  if (normalizedRole === 'operator') {
    return 'Оператор может только перейти в manual из auto/semi (аварийная остановка).'
  }

  return 'Переход в этот режим запрещён для вашей роли.'
}
