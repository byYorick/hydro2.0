import { workflowStageLabel } from '@/utils/schedulerLabels'
import { stageDiagnosticLabel } from '@/utils/automationObservability'

const labels: Record<string, string> = {
  irrigation_run: 'Выполнение полива',
  corr_check: 'Проверка условий коррекции', corr_dose_ph: 'Дозирование pH', corr_dose_ec: 'Дозирование EC',
  corr_wait: 'Ожидание смешивания', corr_verify: 'Проверка результата коррекции',
  recirc_ca: 'Добавление кальция', recirc_calcium: 'Добавление кальция', recirc_mg: 'Добавление магния',
  recirc_magnesium: 'Добавление магния', recirc_npk: 'Добавление NPK', recirc_micro: 'Добавление микроэлементов',
  recirc_ph_0: 'Проверка pH после кальция', recirc_ph_1: 'Проверка pH после магния', recirc_ph_2: 'Проверка pH после NPK', recirc_ph_3: 'Итоговая проверка pH',
}
export function processStageLabel(value: string | null | undefined): string {
  if (!value) return '—'
  const translated = stageDiagnosticLabel(value)
  return labels[value.toLowerCase()] ?? (translated !== value || /[А-Яа-яЁё]/.test(value) ? translated : workflowStageLabel(value) ?? 'Этап не распознан')
}
export function processComponentLabel(value: string): string {
  return ({ calcium: 'Кальций', ca: 'Кальций', magnesium: 'Магний', mg: 'Магний', npk: 'NPK', micro: 'Микроэлементы', ph: 'pH', ph_up: 'Повышение pH', ph_down: 'Понижение pH', T_ca: 'После кальция', T_ca_mg: 'После магния', T_ca_mg_npk: 'После NPK', T_full: 'Итоговая EC' } as Record<string, string>)[value] ?? value
}
