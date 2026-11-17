import type { ExecutionRun } from '@/composables/zoneScheduleWorkspaceTypes'
import { decisionLabel } from './schedulerLabels'
import { irrigationReasonPresentation } from './irrigationDecisionView'

export function chainStepLabel(step: string): string {
  return ({ SNAPSHOT: 'Снимок данных', DECISION: 'Проверка условий', TASK: 'Создание задачи', DISPATCH: 'Передача команды', RUNNING: 'Выполнение', SETUP_PENDING: 'Ожидание подготовки', COMPLETE: 'Завершение', FAIL: 'Ошибка', SKIP: 'Штатный пропуск' } as Record<string, string>)[step] ?? 'Событие процесса'
}

export function chainStepExplanation(step: string, status: string): string {
  if (status === 'err') return 'На этом этапе записана ошибка. Проверьте причину и связанные события.'
  const explanations: Record<string, string> = {
    SNAPSHOT: 'Сохранены данные, использованные при проверке условий.',
    DECISION: 'Записан результат проверки условий. Разрешение не подтверждает подачу воды.',
    TASK: 'Задача зарегистрирована в системе выполнения.',
    DISPATCH: 'Записан этап передачи команды. Доставку и фактическое выполнение проверяйте по последующим событиям.',
    RUNNING: 'Задача в работе; это не является отдельным подтверждением включения насоса.',
    SETUP_PENDING: 'Перед выполнением нужна подготовка системы.',
    COMPLETE: 'Задача завершена. Отдельно проверьте результат полива и достижения целей.',
    FAIL: 'Выполнение завершилось ошибкой. Устраните причину перед повтором.',
    SKIP: 'Условия не разрешили выполнение. Штатный пропуск сам по себе не является ошибкой.',
  }
  return explanations[step] ?? 'Получено событие процесса. Подробности доступны в технических сведениях.'
}

export function executionDecisionLabel(run: ExecutionRun): string {
  if (!run.decision_outcome) {
    if (!['irrigation_start', 'irrigation', 'irrigation_tick'].includes(run.task_type)) return 'Отдельное решение о поливе не требуется'
    return ['completed', 'failed', 'cancelled'].includes(run.status) ? 'Решение о поливе не сохранено' : 'Ожидает проверки условий'
  }
  const outcome = decisionLabel(run.decision_outcome, run.decision_degraded)
  const reason = run.decision_reason_code ? irrigationReasonPresentation(run.decision_reason_code).explanation : null
  return `${outcome}${reason ? ` · ${reason}` : ''}`
}
